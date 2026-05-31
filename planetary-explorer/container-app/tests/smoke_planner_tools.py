"""Direct exercise of the 6 planner tools against the seed registry.

Run with:  RESILIENCE_FORCE_SEED=1 python tests/smoke_planner_tools.py
No Azure OpenAI required — this only hits the deterministic tool layer.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("RESILIENCE_FORCE_SEED", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.resilience.tools import TOOL_DISPATCH  # noqa: E402


def _print(title: str, payload: dict) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("-" * 78)
    # Trim noisy fields for readability
    trimmed = json.loads(json.dumps(payload, default=str))
    if isinstance(trimmed, dict):
        for k, v in trimmed.items():
            if isinstance(v, list) and len(v) > 6:
                trimmed[k] = v[:6] + [f"...({len(v) - 6} more)"]
    print(json.dumps(trimmed, indent=2)[:4000])


async def main() -> None:
    # 1. query_facilities — registry inspection
    res = await TOOL_DISPATCH["query_facilities"](region_filter="TX")
    _print("Q7 'List every TX facility' -> query_facilities(region=TX)", res)

    res = await TOOL_DISPATCH["query_facilities"](facility_type="fab", min_criticality=0.8)
    _print("Q7 'TX fabs with criticality > 0.8' -> query_facilities(facility_type=fab, min=0.8)", res)

    # 2. search_playbooks - RAG only
    res = await TOOL_DISPATCH["search_playbooks"](query="heat dome cooling guidance", hazards=["heat"])
    _print("Q6 'Heat-dome playbook' -> search_playbooks(hazards=[heat])", res)

    res = await TOOL_DISPATCH["search_playbooks"](query="wildfire smoke BCP", hazards=["wildfire"])
    _print("Q6 'Wildfire BCP' -> search_playbooks(hazards=[wildfire])", res)

    # 3. simulate_outage — multi-hop graph
    # Pick an actual facility id from the seed registry
    fac = await TOOL_DISPATCH["query_facilities"](region_filter="TX")
    facilities = fac.get("facilities", [])
    sample_id = None
    for f in facilities:
        if "port" in (f.get("type") or "").lower() or "distribution" in (f.get("type") or "").lower():
            sample_id = f.get("facility_id")
            break
    if not sample_id and facilities:
        sample_id = facilities[0].get("facility_id")
    print(f"\n[picked source facility for outage sim: {sample_id}]")

    res = await TOOL_DISPATCH["simulate_outage"](
        facility_id=sample_id, days=5, max_hops=3
    )
    _print(f"Q3 'Houston port down 5 days' -> simulate_outage({sample_id}, days=5, max_hops=3)", res)

    res = await TOOL_DISPATCH["simulate_outage"](
        facility_id=sample_id, days=5, max_hops=1
    )
    _print(f"Q3 'one-hop blast radius' -> simulate_outage({sample_id}, max_hops=1)", res)

    res = await TOOL_DISPATCH["simulate_outage"](
        facility_id="does-not-exist", days=5, max_hops=3
    )
    _print("Q9 'unknown facility' -> simulate_outage(does-not-exist)", res)

    # 4. find_similar_facilities
    ref_id = None
    for f in facilities:
        if (f.get("type") or "").lower() == "fab":
            ref_id = f.get("facility_id")
            break
    if not ref_id and facilities:
        ref_id = facilities[0].get("facility_id")
    print(f"\n[picked reference for similarity: {ref_id}]")

    res = await TOOL_DISPATCH["find_similar_facilities"](
        reference_id=ref_id, same_type=True
    )
    _print(f"Q5 'similar to Austin Fab' -> find_similar_facilities({ref_id})", res)

    res = await TOOL_DISPATCH["find_similar_facilities"](reference_id="nope-123")
    _print("Q9 'unknown ref' -> find_similar_facilities(nope-123)", res)

    # 5. run_standard_assessment + compare_periods (these hit MAF; may be slow)
    try:
        res = await TOOL_DISPATCH["run_standard_assessment"](
            region_filter="TX", horizon_days=7, hazards=["heat"]
        )
        # Strip facilities array for printing
        printable = {k: v for k, v in res.items() if k not in {"facilities"}}
        printable["facilities_count"] = len(res.get("facilities") or [])
        _print("Q1 'TX heat 7d' -> run_standard_assessment(region=TX, h=7, hazards=heat)", printable)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[run_standard_assessment skipped: {type(exc).__name__}: {exc}]")

    try:
        res = await TOOL_DISPATCH["compare_periods"](
            region_filter="TX",
            horizon_days_a=7,
            horizon_days_b=14,
            hazards=["heat"],
        )
        printable = {k: v for k, v in res.items() if k != "deltas" or True}
        if "deltas" in printable and isinstance(printable["deltas"], list):
            printable["deltas"] = printable["deltas"][:5]
        _print("Q4 'this week vs 14-day' -> compare_periods(7 vs 14, hazards=heat)", printable)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[compare_periods skipped: {type(exc).__name__}: {exc}]")


if __name__ == "__main__":
    asyncio.run(main())

