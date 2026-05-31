"""FanOutPlannerAgent — plan -> fan-out -> collect template.

Demonstrates the canonical MAF-style pattern for "given an input,
decompose into N independent sub-tasks, run them concurrently, and
return a typed envelope".

The scaffolder rewrites the class name (``FanOutPlannerAgent`` →
``<Name>Agent``) and the snake_case package references when you run
``python scripts/new_agent.py <name> --template fan_out_planner``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from _framework import LlmClient, OBOContextMixin, PlannerExecutor, PlanResult
from mcp_runtime import TracedMcpClient

logger = logging.getLogger(__name__)


@dataclass
class FanOutPlan:
    rationale: str
    steps: list[dict[str, Any]]


class FanOutPlannerAgent(OBOContextMixin, PlannerExecutor[str, FanOutPlan, dict[str, Any], dict[str, Any]]):
    """Plan a user question into independent steps, run them in parallel."""

    SYSTEM = (
        "You are a planning agent. Given a user question, produce a JSON plan "
        "with a short rationale and a list of independent steps. Each step is "
        "an object with a 'kind' (string) and 'args' (object). Prefer 3-6 "
        "steps. Respond ONLY with JSON: {rationale: string, steps: [...]}"
    )

    def __init__(
        self,
        *,
        user_assertion: str | None = None,
        llm: LlmClient | None = None,
        mcp: TracedMcpClient | None = None,
        timeout_sec: float = 30.0,
        max_concurrency: int = 4,
    ) -> None:
        OBOContextMixin.__init__(self, user_assertion=user_assertion)
        PlannerExecutor.__init__(
            self,
            llm=llm or LlmClient.from_env(),
            timeout_sec=timeout_sec,
            max_concurrency=max_concurrency,
        )
        self.mcp = mcp or TracedMcpClient.from_mpc_public()

    async def build_plan(self, payload: str) -> FanOutPlan:
        import json

        rsp = await self.llm.chat(
            [
                {"role": "system", "content": self.SYSTEM},
                {"role": "user", "content": payload},
            ],
            response_format={"type": "json_object"},
        )
        raw = rsp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return FanOutPlan(
            rationale=str(data.get("rationale") or ""),
            steps=list(data.get("steps") or []),
        )

    def plan_steps(self, plan: FanOutPlan) -> Sequence[dict[str, Any]]:
        return plan.steps

    async def run_step(self, step: dict[str, Any]) -> dict[str, Any]:
        """Default executor: dispatch by ``kind``.

        * ``mcp_tool`` — call ``args.tool`` on MPC Pro via the traced
          client (skipped if MCP isn't configured).
        * anything else — echoed back as ``{"echo": step}`` so the
          template stays runnable end-to-end without external deps.

        Override this method in your real agent to plug in business
        logic, tool calls, etc.
        """
        kind = step.get("kind")
        args = step.get("args") or {}
        if kind == "mcp_tool" and self.mcp is not None:
            tool = args.get("tool")
            tool_args = args.get("tool_args") or {}
            if not tool:
                return {"error": "mcp_tool step missing 'tool'"}
            result = await self.mcp.call(tool, tool_args)
            return {"tool": tool, "result": result}
        return {"echo": step}

    async def answer(self, question: str) -> PlanResult[FanOutPlan, dict[str, Any]]:
        return await self.run(question)
