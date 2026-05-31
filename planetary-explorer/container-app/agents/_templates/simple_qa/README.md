# `simple_qa` template

Minimal MAF agent built on `_framework/` primitives.

## What it shows

| Pattern | Where |
|---|---|
| Single LLM endpoint resolution (AOAI vs Foundry) | `LlmClient.from_env()` |
| gpt-5 sampling-param stripping | inside `LlmClient.chat()` |
| OBO-bound downstream calls | `OBOContextMixin.fabric_token()` |
| Traced MCP tool invocation | `TracedMcpClient.from_mpc_public()` (default for agents; switch to `from_mpc_pro()` only when Pro-only features are needed) |

## Use it as a starting point

```bash
python scripts/new_agent.py weather_chat
```

That copies this directory to `container-app/agents/weather_chat/` and
rewrites the class name + imports.
