# MAF patterns — gotchas and the canonical fixes

Hard-won lessons from building the Planetary Explorer agents on the
Microsoft Agent Framework. These used to live in commit messages, PR
review threads, and a couple of memory notes. They live here now.

If you're building a new agent, read this once and import from
`_framework/` / `connectors/` accordingly — most of these traps are
already solved upstream.

---

## 1. Fan-in deadlock

**Symptom.** A workflow that runs N parallel branches hangs forever or
times out. Logs show the upstream `await asyncio.gather(...)` never
returning even though every branch completed.

**Cause.** Branches were created lazily inside `gather` (`gather(*[task
for ...])`) **and** at least one branch awaits a value produced by
another branch through a shared async primitive. The event loop never
schedules the producer because the consumer is holding it.

**Fix.** Always create tasks *before* you await the aggregate:

```python
tasks = [asyncio.create_task(worker(x)) for x in items]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

`_framework.FanOutExecutor.run` does this for you — use it.

---

## 2. gpt-5 / o1 / o3 reject sampling params

**Symptom.** Calling `chat.completions.create(..., temperature=0.2)`
against a gpt-5 family deployment returns
`400 Unsupported value: 'temperature' does not support 0.2`.

**Cause.** The reasoning-model family rejects `temperature`, `top_p`,
`frequency_penalty`, `presence_penalty`.

**Fix.** `_framework.LlmClient.chat` strips these params automatically
when the deployment name contains `gpt-5`, `o1`, or `o3`. Just call
it — don't reinvent the strip rule per agent.

---

## 3. AOAI vs Foundry endpoint confusion

**Symptom.** New agent passes through code review, then 404s in
production because somebody set `AZURE_AI_PROJECT_ENDPOINT` but no
`AZURE_OPENAI_ENDPOINT`, or vice-versa.

**Cause.** Two different Azure surfaces speak the same Chat Completions
API. The endpoints, auth scopes, and deployment-naming conventions
differ; every agent re-implementing the resolution rule means every
agent has a different bug.

**Fix.** `_framework.LlmClient.from_env()` resolves
`AZURE_OPENAI_ENDPOINT` first, falls back to
`AZURE_AI_PROJECT_ENDPOINT`, and picks the right auth scope. New agents
should never reach for `AsyncAzureOpenAI()` directly.

---

## 4. OBO scope mistakes

**Symptom.** Fabric query returns `AADSTS65001: The user or
administrator has not consented to use the application` even though the
user just signed in.

**Cause.** Two distinct issues are usually conflated:

1. The Container App needs the user assertion forwarded
   (`X-MS-TOKEN-AAD-ACCESS-TOKEN` or `Authorization: Bearer`).
2. The OBO exchange must request the right downstream scope, e.g.
   `https://api.fabric.microsoft.com/.default` for Fabric.

**Fix.** `_framework.OBOContextMixin.fabric_token(scope=...)` does the
extraction and the exchange. If the user assertion is missing it falls
back to the app-only token via `acquire_app_token`. Use the mixin —
don't roll your own.

---

## 5. MCP folder name shadowing the SDK

**Symptom.** `from mcp import ClientSession` fails with
`ImportError: cannot import name 'ClientSession' from 'mcp'`.

**Cause.** You created a local package called `mcp/` inside
`container-app/`. Python resolves the local package first and shadows
the installed `mcp` SDK.

**Fix.** The PE-internal package is named `mcp_runtime/`. Don't
rename it back.

---

## 6. Streaming routes with silent tool calls

**Symptom.** Demo audience sees "thinking…" for 20s, then a final
answer appears. They can't tell whether the agent actually used MPC Pro,
Fabric, or just hallucinated.

**Cause.** SSE routes only emitted lifecycle events from the workflow,
not the per-tool calls underneath.

**Fix.** Two-part:

1. Use `mcp_runtime.TracedMcpClient` (not raw `MpcMcpClient`) for every
   MCP call. It classifies the tier (read / write / destructive) and
   emits to a process-local trace bus.
2. Wrap your SSE generator with `_framework.merge_with_trace(...)`. It
   interleaves `tool_call` / `tool_result` events with your existing
   workflow events. The UI's trace drawer renders them in-line.

Both site-audit and resilience streams are already wired up — use them
as a reference.

---

## 7. Don't `await` the source iterator before spawning fan-out

**Symptom.** `merge_with_trace` shows tool events arriving only after
the whole workflow finishes — defeating the point.

**Cause.** Your `async def _source()` accumulated all events in a list
before yielding any.

**Fix.** Yield events as you produce them. `merge_with_trace` runs the
source in a background task and a queue interleaves it with trace
emissions, but only if the source actually yields incrementally.

---

## 8. Permission tiers and confirmation cards

**Status.** The TracedMcpClient classifies every tool into
`read` / `write` / `destructive`. Non-`read` calls go through a
`confirm` hook before invocation. The default hook auto-approves so
nothing breaks.

**When the UI lands.** The `confirm` hook will resolve only after the
user clicks the confirmation card. Until then, treat destructive tools
as feature-flagged: gate them with an env var on the call site so a
demo can't accidentally `delete_personal_collection`.

---

## Quick links

- `_framework/` — base classes and primitives
- `connectors/` — typed wrappers per external platform
- `mcp_runtime/` — MCP registry + traced client + trace bus
- `agents/_templates/simple_qa/` — minimal Q&A example
- `agents/_templates/fan_out_planner/` — planner + concurrent steps example
- `scripts/new_agent.py` — `python scripts/new_agent.py NAME [--template ...]`
