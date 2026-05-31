"""Reference template — fan-out planner agent.

Showcases the second canonical pattern after :mod:`simple_qa`:

* :class:`_framework.PlannerExecutor` to build a typed plan and fan out
  steps with deadlock-safe concurrency.
* :class:`_framework.LlmClient` for plan synthesis (with gpt-5 param
  sanitisation built in).
* Optional :class:`mcp_runtime.TracedMcpClient` per step so every tool
  call surfaces in the per-turn trace.

Copy this directory and rename with ``scripts/new_agent.py NAME
--template fan_out_planner``.
"""
from .agent import FanOutPlannerAgent

__all__ = ["FanOutPlannerAgent"]
