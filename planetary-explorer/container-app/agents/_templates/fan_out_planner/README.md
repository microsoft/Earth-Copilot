# fan_out_planner template

A reference agent that takes a user question, asks the LLM to decompose
it into N independent steps, and runs them concurrently using the
framework's deadlock-safe fan-out executor.

## Copy & rename

```powershell
python scripts/new_agent.py weather_research --template fan_out_planner
```

That produces `container-app/agents/weather_research/` with the class
renamed to `WeatherResearchAgent` and all package references rewritten.

## What you get for free

- Plan synthesis with `response_format={"type": "json_object"}`.
- gpt-5 family sampling-param sanitisation (built into `LlmClient`).
- Concurrent step execution capped by `max_concurrency`, per-step
  timeout, per-step error capture (no one failure kills the batch).
- Optional MPC Pro MCP tool calls per step — every call surfaces as
  `tool_call` / `tool_result` SSE events for the trace drawer.
- OBO assertion plumbing if you need Fabric / AI Search inside a step.

## What to customise

Override `run_step()` to plug in your real per-step logic. The default
implementation dispatches `kind == "mcp_tool"` to MPC Pro and echoes
everything else so the template runs end-to-end without external deps.
