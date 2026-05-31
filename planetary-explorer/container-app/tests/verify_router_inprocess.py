"""In-process collection-router verification.

Calls the REAL LoadAgent (real AOAI + real catalog index) for every
M1 Get Started query and records:
  * action (execute / clarify)
  * top collection candidate id (or stac_query string)
  * whether expected_collection appears in candidates OR stac_query
  * clarification question text (when applicable)
  * latency

Auth: uses DefaultAzureCredential. Run `az login` first.
Env required:
  AZURE_OPENAI_ENDPOINT
  AZURE_OPENAI_DEPLOYMENT_NAME (defaults gpt-5)
  AZURE_AI_PROJECT_ENDPOINT (optional)

Writes:
  tests/live_results/router_verification_<ts>.json
  tests/live_results/router_verification_<ts>.md

Usage:
  python tests/verify_router_inprocess.py
  python tests/verify_router_inprocess.py --only stac_chloris_amazon
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Make container-app importable when run from repo root or from tests/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.live_get_started_runner import M1_STAC  # reuse the manifest
from agents.load_agent.load_agent import LoadAgent
from agents.load_agent.load_agent_models import LoadAgentInput


def _candidate_ids(plan) -> list[str]:
    out = []
    for c in plan.collection_candidates or []:
        cid = getattr(c, "id", None) or (c.get("id") if isinstance(c, dict) else None)
        if cid:
            out.append(cid)
    return out


def _matches(expected: str, plan) -> bool:
    """Soft match: expected id appears in candidate ids, stac_query, or
    collection_id field (case-insensitive substring tolerated)."""
    exp = (expected or "").lower()
    if not exp:
        return True
    hay = " ".join(
        [
            (plan.stac_query or "").lower(),
            " ".join(_candidate_ids(plan)).lower(),
            (getattr(plan, "collection_id", None) or "").lower(),
        ]
    )
    return exp in hay


async def run_one(agent: LoadAgent, case) -> dict:
    payload = LoadAgentInput(
        query=case.query,
        location_name=case.expected_location,
    )
    t0 = time.perf_counter()
    err = None
    plan = None
    try:
        plan = await agent.plan(payload)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    dt = time.perf_counter() - t0

    if err or plan is None:
        return {
            "id": case.id,
            "query": case.query,
            "expected_collection": case.expected_collection,
            "expected_location": case.expected_location,
            "ok": False,
            "error": err,
            "latency_s": round(dt, 2),
        }

    cands = _candidate_ids(plan)
    matched = _matches(case.expected_collection, plan) if case.expected_collection else None
    is_execute = plan.action == "execute"
    return {
        "id": case.id,
        "query": case.query,
        "expected_collection": case.expected_collection,
        "expected_location": case.expected_location,
        "action": plan.action,
        "stac_query": plan.stac_query,
        "top_candidates": cands[:5],
        "clarification_question": plan.clarification_question,
        "expected_match": matched,
        "pass": bool(is_execute and (matched if case.expected_collection else True)),
        "latency_s": round(dt, 2),
        "error": None,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Run only this case id")
    ap.add_argument("--limit", type=int, help="Run first N cases")
    ap.add_argument("--concurrency", type=int, default=5, help="Parallel workers")
    args = ap.parse_args()

    cases = list(M1_STAC)
    if args.only:
        cases = [c for c in cases if c.id == args.only]
    if args.limit:
        cases = cases[: args.limit]

    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        raise RuntimeError("AZURE_OPENAI_ENDPOINT must be set before running this script.")
    os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

    agent = LoadAgent()

    print(f"Running {len(cases)} M1 STAC cases in-process (concurrency={args.concurrency})...")
    sem = asyncio.Semaphore(args.concurrency)

    async def _bounded(case):
        async with sem:
            r = await run_one(agent, case)
            if r.get("error"):
                print(f"  ERR  {case.id} ({r['latency_s']}s) {r['error']}")
            else:
                tag = "PASS" if r["pass"] else ("CLAR" if r["action"] == "clarify" else "MISS")
                print(f"  {tag} {case.id} action={r['action']} cands={r['top_candidates'][:2]} ({r['latency_s']}s)")
            return r

    results = await asyncio.gather(*[_bounded(c) for c in cases])

    # Tally
    n = len(results)
    passed = sum(1 for r in results if r.get("pass"))
    clarify = sum(1 for r in results if not r.get("error") and r.get("action") == "clarify")
    errors = sum(1 for r in results if r.get("error"))
    miss = n - passed - clarify - errors

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent / "live_results"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / f"router_verification_{ts}.json"
    md_path = out_dir / f"router_verification_{ts}.md"

    json_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total": n,
                    "passed": passed,
                    "clarify": clarify,
                    "wrong_collection": miss,
                    "errors": errors,
                },
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Router verification — {ts}",
        "",
        f"**Total**: {n} | **Pass**: {passed} | **Clarify**: {clarify} | **Wrong collection**: {miss} | **Errors**: {errors}",
        "",
        "| # | id | action | expected | top_candidate(s) | match | latency | clarify_q |",
        "|---|----|--------|----------|------------------|-------|---------|-----------|",
    ]
    for i, r in enumerate(results, 1):
        cands = ", ".join(r.get("top_candidates") or []) if not r.get("error") else "—"
        q = (r.get("clarification_question") or "").replace("|", "/")[:80]
        match = "✓" if r.get("pass") else ("clarify" if r.get("action") == "clarify" else "✗")
        if r.get("error"):
            lines.append(
                f"| {i} | {r['id']} | ERROR | {r.get('expected_collection') or '—'} | — | — | {r['latency_s']}s | {r['error']} |"
            )
        else:
            lines.append(
                f"| {i} | {r['id']} | {r['action']} | {r.get('expected_collection') or '—'} | {cands} | {match} | {r['latency_s']}s | {q} |"
            )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"PASS={passed}/{n}  CLARIFY={clarify}  WRONG={miss}  ERROR={errors}")
    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
