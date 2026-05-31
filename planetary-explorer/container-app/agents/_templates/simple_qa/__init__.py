"""Reference template — a minimal Q&A agent built on the framework.

Copy this directory, rename, and you've got a working agent that:

* Resolves the LLM endpoint once (no AOAI-vs-Foundry confusion).
* Strips sampling params for gpt-5 family models.
* Optionally fans out to MPC Pro MCP tools through the traced client.
* Carries an OBO assertion for downstream Fabric / Search calls.

Use ``scripts/new_agent.py NAME`` to copy this template automatically.
"""
from .agent import SimpleQaAgent

__all__ = ["SimpleQaAgent"]
