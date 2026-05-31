"""Live smoke test for the deployed MPC Pro MCP sidecar.

Run this from inside the backend container (``az containerapp exec``)
*after* the sidecar is deployed and the GeoCatalog data-plane grant
landed, but *before* flipping ``USE_MPC_MCP=true`` in prod.

Usage::

    # Inside the backend container:
    MPC_MCP_URL=https://<sidecar-fqdn> python tools/mpc_mcp_smoke.py
    # Or against any GeoCatalog instance:
    MPC_MCP_URL=https://<sidecar-fqdn> GEOCATALOG_URI=https://<gc>.geocatalog.spatio.azure.com \\
        python tools/mpc_mcp_smoke.py

What it checks (every step must pass before Phase 2 flag flip):

  1. ``MPC_MCP_URL`` is configured.
  2. The MCP session opens and ``tools/list`` returns >= 1 tool.
  3. The ``list_personal_stac_collections`` tool is advertised.
  4. The tool call returns a JSON-parseable list (auth + grant verified).
  5. Round-trip latency is under a sane ceiling (10s by default).

Exits 0 on full pass, non-zero on the first failure with the reason
printed. Designed to be CI-friendly.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import NoReturn


LATENCY_BUDGET_S = float(os.getenv("MPC_MCP_LATENCY_BUDGET_S", "10"))


def _fail(step: str, reason: str) -> NoReturn:
    print(f"[FAIL] {step}: {reason}")
    sys.exit(1)


def _ok(step: str, detail: str = "") -> None:
    suffix = f" -- {detail}" if detail else ""
    print(f"[ OK ] {step}{suffix}")


async def main() -> None:
    print("=== MPC Pro MCP sidecar smoke test ===")

    # Step 1: env config -----------------------------------------------------
    url = (os.getenv("MPC_MCP_URL") or "").strip()
    if not url:
        _fail("env", "MPC_MCP_URL is not set")
    _ok("env", f"MPC_MCP_URL={url}")

    # Step 2: client constructs cleanly and reports configured --------------
    try:
        import mcp_catalog_client as mcc
    except ImportError as exc:
        _fail("import", f"mcp_catalog_client not importable: {exc}")

    client = mcc.get_client()
    if not client.configured:
        _fail("configure", f"client reports configured=False (url={client.url!r})")
    _ok("configure", f"client.configured=True, url={client.url}")

    # Step 3: tools/list -- proves sidecar is reachable and protocol works --
    started = time.monotonic()
    try:
        await client._ensure_session()  # noqa: SLF001 -- intentional smoke probe
    except mcc.MpcMcpUnavailable as exc:
        _fail("connect", f"could not open MCP session: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        _fail("connect", f"unexpected error opening session: {exc!r}")
    connect_s = time.monotonic() - started

    advertised = client._available_tools  # noqa: SLF001
    if not advertised:
        _fail("tools/list", "sidecar advertised zero tools")
    _ok(
        "tools/list",
        f"{len(advertised)} tools advertised in {connect_s:.2f}s",
    )

    # Step 4: required tool is present --------------------------------------
    required = "list_personal_stac_collections"
    if required not in advertised:
        _fail(
            f"tool:{required}",
            f"not advertised. Available: {sorted(advertised)[:10]}...",
        )
    _ok(f"tool:{required}", "advertised")

    # Step 5: actually call it ----------------------------------------------
    started = time.monotonic()
    try:
        cols = await client.list_personal_collections()
    except mcc.MpcMcpUnavailable as exc:
        # The most common cause is "MI not granted Reader inside the
        # GeoCatalog instance yet". Print the hint so the operator
        # doesn't have to dig.
        _fail(
            "list_personal_collections",
            (
                f"call failed: {exc}\n"
                "  Hint: confirm the sidecar's system-assigned MI principal id\n"
                "  is added as Reader inside the GeoCatalog instance via the\n"
                "  MPC Pro portal -> Access control."
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive
        _fail("list_personal_collections", f"unexpected error: {exc!r}")
    call_s = time.monotonic() - started

    if not isinstance(cols, list):
        _fail("list_personal_collections", f"returned non-list: {type(cols).__name__}")

    if call_s > LATENCY_BUDGET_S:
        _fail(
            "latency",
            f"call took {call_s:.2f}s (budget {LATENCY_BUDGET_S}s)",
        )

    _ok(
        "list_personal_collections",
        f"{len(cols)} collections in {call_s:.2f}s",
    )
    if cols:
        sample = ", ".join(c.get("id", "?") for c in cols[:5])
        print(f"        sample ids: {sample}")

    # Step 6: clean shutdown -- proves the lifespan path works too ----------
    try:
        await mcc.shutdown()
    except Exception as exc:  # pragma: no cover - defensive
        _fail("shutdown", f"shutdown raised: {exc!r}")
    _ok("shutdown", "client closed cleanly")

    print()
    print("All checks passed. Safe to flip USE_MPC_MCP=true.")


if __name__ == "__main__":
    asyncio.run(main())
