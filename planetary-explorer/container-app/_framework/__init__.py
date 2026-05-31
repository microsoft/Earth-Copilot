"""Reusable MAF agent scaffolding.

This package codifies the patterns the existing PE agents have
rediscovered the hard way:

* AOAI vs Foundry endpoint discrimination — :class:`LlmClient`
* gpt-5 parameter sanitisation — :class:`LlmClient.chat`
* On-behalf-of token plumbing — :class:`OBOContextMixin`
* Fan-out/fan-in without deadlock — :class:`FanOutExecutor`

New agents should subclass / compose these primitives instead of
copy-pasting the same plumbing into yet another module. See
``agents/_templates/simple_qa/`` for a minimal worked example.

This package is **additive**: nothing in the existing agent tree
imports from here yet. Migration is one agent at a time.
"""

from .executors import CriticExecutor, CriticVerdict, PlannerExecutor, PlanResult
from .fan_out import FanOutExecutor, FanOutResult
from .llm_client import LlmClient, LlmEndpointKind
from .obo import OBOContextMixin, extract_user_assertion
from .sse_trace import merge_with_trace

__all__ = [
    "CriticExecutor",
    "CriticVerdict",
    "FanOutExecutor",
    "FanOutResult",
    "LlmClient",
    "LlmEndpointKind",
    "OBOContextMixin",
    "PlannerExecutor",
    "PlanResult",
    "extract_user_assertion",
    "merge_with_trace",
]
