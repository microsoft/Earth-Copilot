"""
Drop-in shim for the subset of Semantic Kernel that semantic_translator.py uses.

Wave 5 retires the `semantic-kernel` package dependency. Importing this
module installs the shim under the legacy `semantic_kernel.*` import paths
via `sys.modules`, so the existing `from semantic_kernel...` lines in
semantic_translator.py resolve to these classes without code changes.

Backed by `AsyncAzureOpenAI` directly. No Pydantic validation, no kernel
runtime, no plugin/function-calling abstractions.

What is supported
-----------------
- `Kernel` with `add_service`, `add_function` (no-op for plugin registration),
  `get_service`, `invoke_prompt`, `invoke`.
- `AzureChatCompletion` (api-key or AAD token-provider auth).
- `AzureChatPromptExecutionSettings` (service_id, temperature, max_tokens /
  max_completion_tokens, top_p, function_choice_behavior — the last is
  accepted but ignored by the shim).
- `KernelArguments` (template vars + `settings=`).
- `ChatHistory` (`add_user_message`, `add_system_message`,
  `add_assistant_message`).
- `KernelFunction.from_prompt` + `PromptTemplateConfig` + `InputVariable`.
- `FunctionChoiceBehavior.Auto(...)` returns a sentinel.
- `kernel_function(name=, description=)` decorator (passthrough — the only
  caller is the geocoding plugin registration, which is a no-op).
- `get_chat_message_content(chat_history=, settings=, kernel=)` on the
  service object returned by `Kernel.get_service(...)`.

What is NOT supported
---------------------
- Function calling / tool execution. The geocoding plugin path falls
  through to its non-tool prompt; deterministic LOCATION_NAMES matching
  upstream in `RouterAgent` covers the common cases.
- Streaming, embeddings, memory connectors, planners.
- Pydantic validation of settings — fields are stored as plain attributes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import types
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__version__ = "0.0.0-shim"


# ============================================================================
# Result wrapper - duck-types Semantic Kernel's FunctionResult /
# ChatMessageContent enough for `_extract_clean_content_from_sk_result`.
# ============================================================================

class _ShimResult:
    """Result object exposing `.value` (str), `.content` (str), and __str__."""

    __slots__ = ("value", "content")

    def __init__(self, content: str) -> None:
        self.value: str = content
        self.content: str = content

    def __str__(self) -> str:  # used by callers that do str(result)
        return self.value

    def __repr__(self) -> str:  # nicer logs
        return f"_ShimResult({self.value!r})"


# ============================================================================
# Settings / arguments
# ============================================================================

class AzureChatPromptExecutionSettings:
    """Bag of fields. Mirrors the SK class; only the fields we use exist."""

    def __init__(
        self,
        service_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_completion_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        function_choice_behavior: Any = None,
        **_extra: Any,
    ) -> None:
        self.service_id = service_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_completion_tokens = max_completion_tokens
        self.top_p = top_p
        self.function_choice_behavior = function_choice_behavior


class KernelArguments(dict):
    """Dict-like mapping of template variables, with a ``settings`` attribute."""

    def __init__(self, settings: Any = None, **template_vars: Any) -> None:
        super().__init__(**template_vars)
        self.settings: Optional[AzureChatPromptExecutionSettings] = settings


# ============================================================================
# Function-choice sentinel (we don't drive tool calls in the shim)
# ============================================================================

class _FunctionChoiceBehaviorAuto:
    def __init__(self, auto_invoke: bool = True, filters: Optional[Dict[str, Any]] = None) -> None:
        self.auto_invoke = auto_invoke
        self.filters = filters or {}


class FunctionChoiceBehavior:
    @staticmethod
    def Auto(auto_invoke: bool = True, filters: Optional[Dict[str, Any]] = None) -> _FunctionChoiceBehaviorAuto:
        return _FunctionChoiceBehaviorAuto(auto_invoke=auto_invoke, filters=filters)


# ============================================================================
# Chat history
# ============================================================================

class _Message:
    __slots__ = ("role", "content")

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class ChatHistory:
    def __init__(self) -> None:
        self.messages: List[_Message] = []

    def add_system_message(self, content: str) -> None:
        self.messages.append(_Message("system", content))

    def add_user_message(self, content: str) -> None:
        self.messages.append(_Message("user", content))

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(_Message("assistant", content))


# ============================================================================
# Chat-completion service
# ============================================================================

class ChatCompletionClientBase:
    """Sentinel type used in ``Kernel.get_service(type=ChatCompletionClientBase)``."""


def _build_kwargs(settings: Optional[AzureChatPromptExecutionSettings]) -> Dict[str, Any]:
    """Translate execution settings into AOAI kwargs.

    GPT-5 deployments only accept ``max_completion_tokens``; legacy
    deployments accept ``max_tokens``. We forward whichever is set.
    """
    out: Dict[str, Any] = {}
    if settings is None:
        return out
    if settings.temperature is not None:
        out["temperature"] = settings.temperature
    if settings.top_p is not None:
        out["top_p"] = settings.top_p
    # Prefer max_completion_tokens (GPT-5 / new responses API),
    # fall back to max_tokens (legacy).
    if settings.max_completion_tokens is not None:
        out["max_completion_tokens"] = settings.max_completion_tokens
    elif settings.max_tokens is not None:
        out["max_tokens"] = settings.max_tokens
    return out


class AzureChatCompletion:
    """Holds a deployment + an AsyncAzureOpenAI client keyed by ``service_id``."""

    def __init__(
        self,
        deployment_name: str,
        api_key: Optional[str] = None,
        ad_token_provider: Optional[Callable[[], str]] = None,
        endpoint: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: str = "2024-10-21",
        service_id: Optional[str] = None,
        **_extra: Any,
    ) -> None:
        if not deployment_name:
            raise ValueError("AzureChatCompletion requires deployment_name")
        if api_key is None and ad_token_provider is None:
            raise ValueError(
                "AzureChatCompletion requires either api_key or ad_token_provider"
            )

        self.deployment_name = deployment_name
        self.service_id = service_id or "chat-completion"
        self.api_version = api_version
        self.api_key = api_key
        self.ad_token_provider = ad_token_provider

        # SK callers usually pass base_url=".../openai". AsyncAzureOpenAI
        # wants azure_endpoint (no /openai suffix).
        endpoint_root = endpoint or base_url or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        if endpoint_root.endswith("/openai"):
            endpoint_root = endpoint_root[: -len("/openai")]
        self.azure_endpoint = endpoint_root.rstrip("/")

        # Lazy client (AsyncAzureOpenAI is cheap to build but we delay until first call).
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from openai import AsyncAzureOpenAI

        if self.api_key:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )
        else:
            assert self.ad_token_provider is not None
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                azure_ad_token_provider=self.ad_token_provider,
                api_version=self.api_version,
            )
        return self._client

    async def _chat(
        self,
        messages: List[Dict[str, str]],
        settings: Optional[AzureChatPromptExecutionSettings],
    ) -> str:
        client = self._get_client()
        kwargs = _build_kwargs(settings)
        resp = await client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    # SK callers do: `chat_completion.get_chat_message_content(chat_history=, settings=, kernel=)`
    async def get_chat_message_content(
        self,
        chat_history: ChatHistory,
        settings: Optional[AzureChatPromptExecutionSettings] = None,
        kernel: Any = None,
        **_extra: Any,
    ) -> _ShimResult:
        messages = [{"role": m.role, "content": m.content} for m in chat_history.messages]
        content = await self._chat(messages, settings)
        return _ShimResult(content)


# ============================================================================
# Prompt templates / functions
# ============================================================================

class InputVariable:
    def __init__(self, name: str, description: str = "", **_extra: Any) -> None:
        self.name = name
        self.description = description


class PromptTemplateConfig:
    def __init__(
        self,
        template: str,
        name: str = "",
        description: str = "",
        template_format: str = "semantic-kernel",
        input_variables: Optional[List[InputVariable]] = None,
        **_extra: Any,
    ) -> None:
        self.template = template
        self.name = name
        self.description = description
        self.template_format = template_format
        self.input_variables = list(input_variables or [])


# Substitute {{$var}} or {{ $var }} with KernelArguments[var].
_TEMPLATE_PATTERN = re.compile(r"\{\{\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _render_template(template: str, args: Optional[KernelArguments]) -> str:
    if not args:
        return template

    def repl(match: re.Match) -> str:
        var_name = match.group(1)
        value = args.get(var_name)
        return "" if value is None else str(value)

    return _TEMPLATE_PATTERN.sub(repl, template)


class KernelFunction:
    """Stores a prompt template that can be invoked with a Kernel."""

    def __init__(
        self,
        prompt_template_config: PromptTemplateConfig,
        function_name: str = "",
        plugin_name: str = "",
    ) -> None:
        self.prompt_template_config = prompt_template_config
        self.function_name = function_name
        self.plugin_name = plugin_name

    @classmethod
    def from_prompt(
        cls,
        prompt_template_config: PromptTemplateConfig,
        function_name: str = "",
        plugin_name: str = "",
        **_extra: Any,
    ) -> "KernelFunction":
        return cls(prompt_template_config, function_name=function_name, plugin_name=plugin_name)


# kernel_function decorator (passthrough — used only by the geocoding plugin
# registration path which is a no-op in the shim).
def kernel_function(*_dargs: Any, **_dkwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        return fn
    if len(_dargs) == 1 and callable(_dargs[0]) and not _dkwargs:
        # Bare @kernel_function usage
        return _dargs[0]  # type: ignore[return-value]
    return _wrap


# ============================================================================
# Kernel
# ============================================================================

class Kernel:
    def __init__(self) -> None:
        self._services: Dict[str, AzureChatCompletion] = {}
        self._default_service: Optional[AzureChatCompletion] = None
        self._functions: Dict[str, Callable[..., Any]] = {}
        self.plugins: Dict[str, Dict[str, Callable[..., Any]]] = {}

    # -- services ------------------------------------------------------------

    def add_service(self, service: AzureChatCompletion) -> None:
        self._services[service.service_id] = service
        if self._default_service is None:
            self._default_service = service

    def get_service(
        self,
        service_id: Optional[str] = None,
        type: Optional[type] = None,  # noqa: A002 - SK uses this name
        **_extra: Any,
    ) -> AzureChatCompletion:
        if isinstance(service_id, str) and service_id in self._services:
            return self._services[service_id]
        if self._default_service is None:
            raise RuntimeError("Kernel has no chat-completion service configured")
        return self._default_service

    # -- functions / plugins -------------------------------------------------

    def add_function(self, plugin_name: str, function: Callable[..., Any]) -> None:
        # SK supports both @kernel_function-decorated callables and KernelFunction.
        # The shim only needs to remember the name so that nothing crashes;
        # function calling itself is not driven by the shim.
        name = getattr(function, "__name__", getattr(function, "function_name", "fn"))
        self._functions[f"{plugin_name}.{name}"] = function
        self.plugins.setdefault(plugin_name, {})[name] = function

    def add_plugin(self, plugin: Any, plugin_name: str) -> None:
        # Mirrors SK's add_plugin signature; iterates @kernel_function methods.
        for attr in dir(plugin):
            fn = getattr(plugin, attr)
            if callable(fn) and not attr.startswith("_"):
                self.add_function(plugin_name, fn)

    # -- invocation ----------------------------------------------------------

    async def invoke_prompt(
        self,
        prompt: str,
        function_name: str = "",
        plugin_name: str = "",
        arguments: Optional[KernelArguments] = None,
        prompt_template_config: Optional[PromptTemplateConfig] = None,
        **_extra: Any,
    ) -> _ShimResult:
        rendered = _render_template(prompt, arguments)
        settings = arguments.settings if arguments is not None else None
        service = self.get_service(settings.service_id if settings else None)
        content = await service._chat(
            messages=[{"role": "user", "content": rendered}],
            settings=settings,
        )
        return _ShimResult(content)

    async def invoke(
        self,
        function: KernelFunction,
        arguments: Optional[KernelArguments] = None,
        **_extra: Any,
    ) -> _ShimResult:
        if not isinstance(function, KernelFunction):
            raise TypeError(f"Kernel.invoke shim only supports KernelFunction (got {type(function)!r})")
        return await self.invoke_prompt(
            prompt=function.prompt_template_config.template,
            function_name=function.function_name,
            plugin_name=function.plugin_name,
            arguments=arguments,
            prompt_template_config=function.prompt_template_config,
        )


# ============================================================================
# sys.modules registration so legacy `from semantic_kernel...` imports work
# ============================================================================

def _install() -> None:
    """Wire shim classes into the legacy `semantic_kernel.*` import paths."""

    def _mod(name: str) -> types.ModuleType:
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            sys.modules[name] = m
        return m

    # Top-level package
    sk = _mod("semantic_kernel")
    sk.__version__ = __version__
    sk.Kernel = Kernel  # type: ignore[attr-defined]

    # contents
    sk_contents = _mod("semantic_kernel.contents")
    sk_contents.ChatHistory = ChatHistory  # type: ignore[attr-defined]
    sk_contents_ch = _mod("semantic_kernel.contents.chat_history")
    sk_contents_ch.ChatHistory = ChatHistory  # type: ignore[attr-defined]

    # functions
    sk_functions = _mod("semantic_kernel.functions")
    sk_functions.kernel_function = kernel_function  # type: ignore[attr-defined]
    sk_functions.KernelArguments = KernelArguments  # type: ignore[attr-defined]
    sk_functions.KernelFunction = KernelFunction  # type: ignore[attr-defined]
    _mod("semantic_kernel.functions.kernel_arguments").KernelArguments = KernelArguments  # type: ignore[attr-defined]
    _mod("semantic_kernel.functions.kernel_function").KernelFunction = KernelFunction  # type: ignore[attr-defined]

    # connectors
    _mod("semantic_kernel.connectors")
    sk_ai = _mod("semantic_kernel.connectors.ai")
    sk_ai.FunctionChoiceBehavior = FunctionChoiceBehavior  # type: ignore[attr-defined]
    _mod("semantic_kernel.connectors.ai.function_choice_behavior").FunctionChoiceBehavior = FunctionChoiceBehavior  # type: ignore[attr-defined]
    _mod(
        "semantic_kernel.connectors.ai.chat_completion_client_base"
    ).ChatCompletionClientBase = ChatCompletionClientBase  # type: ignore[attr-defined]

    sk_open_ai = _mod("semantic_kernel.connectors.ai.open_ai")
    sk_open_ai.AzureChatCompletion = AzureChatCompletion  # type: ignore[attr-defined]
    sk_open_ai.AzureChatPromptExecutionSettings = AzureChatPromptExecutionSettings  # type: ignore[attr-defined]

    _mod("semantic_kernel.connectors.ai.open_ai.prompt_execution_settings")
    aoai_settings_mod = _mod(
        "semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings"
    )
    aoai_settings_mod.AzureChatPromptExecutionSettings = AzureChatPromptExecutionSettings  # type: ignore[attr-defined]

    # prompt_template
    _mod("semantic_kernel.prompt_template")
    _mod("semantic_kernel.prompt_template.prompt_template_config").PromptTemplateConfig = PromptTemplateConfig  # type: ignore[attr-defined]
    _mod("semantic_kernel.prompt_template.input_variable").InputVariable = InputVariable  # type: ignore[attr-defined]


_install()
logger.info("[sk_shim] Semantic Kernel shim installed (no semantic-kernel package required)")


__all__ = [
    "Kernel",
    "ChatHistory",
    "KernelArguments",
    "KernelFunction",
    "AzureChatCompletion",
    "AzureChatPromptExecutionSettings",
    "FunctionChoiceBehavior",
    "ChatCompletionClientBase",
    "PromptTemplateConfig",
    "InputVariable",
    "kernel_function",
]
