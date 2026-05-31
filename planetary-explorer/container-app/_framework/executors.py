"""Reusable planner / critic executor base classes.

These are MAF-friendly building blocks — they don't import the
``agent_framework`` package themselves so they remain unit-testable
without the heavy MAF runtime, but their interfaces line up with the
``Executor`` protocol that ``agents/resilience/planner.py`` and
``agents/site_intel/workflow.py`` already implement.

The intent is that a new agent can subclass :class:`PlannerExecutor` and
override :meth:`build_plan`, or subclass :class:`CriticExecutor` and
override :meth:`evaluate`, getting the deadlock-safe fan-out plumbing
(:class:`_framework.FanOutExecutor`) and LLM-resolution
(:class:`_framework.LlmClient`) for free.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Sequence, TypeVar

from .fan_out import FanOutExecutor, FanOutResult
from .llm_client import LlmClient

logger = logging.getLogger(__name__)

TInput = TypeVar("TInput")
TPlan = TypeVar("TPlan")
TStep = TypeVar("TStep")
TStepOut = TypeVar("TStepOut")
TVerdict = TypeVar("TVerdict")


@dataclass
class PlanResult(Generic[TPlan, TStepOut]):
    plan: TPlan
    step_results: list[FanOutResult]
    started_at: float
    finished_at: float
    latency_ms: int
    extras: dict[str, Any] = field(default_factory=dict)


class PlannerExecutor(Generic[TInput, TPlan, TStep, TStepOut]):
    """Plan -> fan-out -> collect skeleton.

    Subclasses implement:

    * :meth:`build_plan` — turn an input into a typed plan describing
      independent steps.
    * :meth:`plan_steps` — extract the iterable of steps from the plan.
    * :meth:`run_step`  — execute one step (called concurrently).

    The base class wires the LLM client, the fan-out executor, and a
    consistent :class:`PlanResult` envelope.
    """

    def __init__(
        self,
        *,
        llm: LlmClient | None = None,
        timeout_sec: float = 30.0,
        max_concurrency: int = 8,
    ) -> None:
        self.llm = llm or LlmClient.from_env()
        self.timeout_sec = timeout_sec
        self.max_concurrency = max_concurrency

    async def build_plan(self, payload: TInput) -> TPlan:  # pragma: no cover - abstract
        raise NotImplementedError

    def plan_steps(self, plan: TPlan) -> Sequence[TStep]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def run_step(self, step: TStep) -> TStepOut:  # pragma: no cover - abstract
        raise NotImplementedError

    async def run(self, payload: TInput) -> PlanResult[TPlan, TStepOut]:
        started = time.time()
        plan = await self.build_plan(payload)
        steps = list(self.plan_steps(plan))
        results = await FanOutExecutor.run(
            steps,
            self.run_step,
            timeout_sec=self.timeout_sec,
            max_concurrency=self.max_concurrency,
        )
        finished = time.time()
        return PlanResult(
            plan=plan,
            step_results=results,
            started_at=started,
            finished_at=finished,
            latency_ms=int((finished - started) * 1000),
        )


@dataclass
class CriticVerdict:
    ok: bool
    score: float | None = None
    rationale: str | None = None
    suggestions: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)


class CriticExecutor(Generic[TInput]):
    """LLM-as-judge skeleton.

    Subclasses provide :meth:`prompt` returning a chat-completion
    ``messages`` list; the base class drives the LLM, parses the JSON
    verdict, and returns a typed :class:`CriticVerdict`.

    The default :meth:`evaluate` retries on parse failure once with a
    stricter "respond ONLY with JSON" reminder.
    """

    def __init__(
        self,
        *,
        llm: LlmClient | None = None,
        max_retries: int = 1,
        response_format_json: bool = True,
    ) -> None:
        self.llm = llm or LlmClient.from_env()
        self.max_retries = max_retries
        self.response_format_json = response_format_json

    async def prompt(self, payload: TInput) -> list[dict[str, Any]]:  # pragma: no cover - abstract
        raise NotImplementedError

    async def parse(self, raw: str) -> CriticVerdict:
        """Parse an LLM response into a :class:`CriticVerdict`. Default
        implementation expects a JSON object with ``ok`` /
        ``score`` / ``rationale`` / ``suggestions``."""
        import json

        data = json.loads(raw)
        return CriticVerdict(
            ok=bool(data.get("ok", False)),
            score=data.get("score"),
            rationale=data.get("rationale"),
            suggestions=list(data.get("suggestions") or []),
            extras={k: v for k, v in data.items() if k not in {"ok", "score", "rationale", "suggestions"}},
        )

    async def evaluate(self, payload: TInput) -> CriticVerdict:
        messages = await self.prompt(payload)
        kwargs: dict[str, Any] = {}
        if self.response_format_json:
            kwargs["response_format"] = {"type": "json_object"}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                rsp = await self.llm.chat(messages, **kwargs)
                raw = rsp.choices[0].message.content or ""
                return await self.parse(raw)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("critic parse attempt %d failed: %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    messages = list(messages) + [
                        {"role": "user", "content": "Respond ONLY with a valid JSON object matching the schema."}
                    ]
        return CriticVerdict(
            ok=False,
            rationale=f"critic_unparseable: {last_error}",
        )
