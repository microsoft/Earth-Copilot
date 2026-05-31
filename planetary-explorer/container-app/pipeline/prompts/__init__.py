"""
Pipeline prompt modules.

System prompts for each LLM-driven component live in their own files so that
prompt edits show up cleanly in code review (separate from control-flow
changes), can be diffed across versions, and can be edited without touching
the orchestration code that uses them.
"""

from .action_router_prompt import ACTION_ROUTER_SYSTEM_PROMPT

__all__ = [
    "ACTION_ROUTER_SYSTEM_PROMPT",
]
