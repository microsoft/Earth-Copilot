"""Retry empty-title MISSes with id-based queries, then write final report."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.load_agent.load_agent import LoadAgent  # noqa: E402
from agents.load_agent.load_agent_models import LoadAgentInput  # noqa: E402
from verify_catalog_routing import CATALOG_PATH, _hit, _candidate_ids  # noqa: E402

LOCATION = "California"
INC_PATH = Path(__file__).resolve().parent / "live_results" / "_catalog_incremental.json"


# Friendly query templates per id for ids with empty titles in the catalog.
ID_QUERIES = {
    "cop-dem-glo-30": "Show Copernicus DEM 30 meter elevation for California",
    "cop-dem-glo-90": "Show Copernicus DEM 90 meter elevation for California",
    "3dep-lidar-classification": "Show 3DEP lidar classification for California",
    "3dep-lidar-dsm": "Show 3DEP lidar digital surface model DSM for California",
    "3dep-lidar-dtm": "Show 3DEP lidar digital terrain model DTM for California",
    "3dep-lidar-dtm-native": "Show 3DEP lidar native DTM for California",
    "3dep-lidar-hag": "Show 3DEP lidar height above ground for California",
    "3dep-lidar-intensity": "Show 3DEP lidar intensity for California",
    "3dep-lidar-pointsourceid": "Show 3DEP lidar point source id for California",
    "3dep-lidar-returns": "Show 3DEP lidar returns for California",
    "3dep-seamless": "Show 3DEP seamless elevation DEM for California",
    "chesapeake-lc-13": "Show Chesapeake 13-class land cover for California",
    "io-lulc-9-class": "Show 10m Annual Land Use Land Cover v1 9-class for California",
    "io-lulc-annual-v02": "Show 10m Annual Land Use Land Cover v2 9-class for California",
    "noaa-mrms-qpe-1h-pass1": "Show NOAA MRMS QPE 1-Hour Pass 1 precipitation for California",
}


async def _retry_one(agent: LoadAgent, cid: str, query: str) -> dict:
    last_err = None
    for attempt in range(3):
        try:
            payload = LoadAgentInput(query=query, location_name=LOCATION)
            plan = await asyncio.wait_for(agent.plan(payload), timeout=60.0)
            cands = _candidate_ids(plan)
            return {
                "id": cid,
                "title": query,
                "query": query,
                "location": LOCATION,
                "action": plan.action,
                "stac_query": plan.stac_query,
                "top_candidates": cands[:5],
                "hit": _hit(cid, plan),
                "exact_top": bool(cands and cands[0].lower() == cid.lower()),
                "clarification_question": plan.clarification_question,
                "latency_s": 0.0,
                "error": None,
            }
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(8.0 * (attempt + 1))
    return {
        "id": cid, "title": query, "query": query, "location": LOCATION,
        "error": f"{type(last_err).__name__}: {last_err}",
    }


async def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    all_colls = []
    for cat in catalog["categories"]:
        for c in cat["collections"]:
            all_colls.append({**c, "category": cat["name"]})

    existing = json.loads(INC_PATH.read_text(encoding="utf-8")) if INC_PATH.exists() else []
    by_id = {r["id"]: r for r in existing}

    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        raise RuntimeError("AZURE_OPENAI_ENDPOINT must be set before running this script.")
    os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
    agent = LoadAgent()

    # Targeted retry: any MISS that has a friendly id-query OR title is empty
    todo = []
    for c in all_colls:
        r = by_id.get(c["id"])
        if r is None:
            todo.append(c)
            continue
        cands = r.get("top_candidates") or []
        if (not r.get("hit") and not r.get("error")
                and r.get("action") == "execute" and not cands):
            todo.append(c)

    print(f"Retrying {len(todo)} MISS/missing collections", flush=True)
    for i, c in enumerate(todo, 1):
        cid = c["id"]
        query = ID_QUERIES.get(cid)
        if not query:
            title = c.get("title") or cid
            query = f"Show {title} for {LOCATION}"
        await asyncio.sleep(7.0)
        r = await _retry_one(agent, cid, query)
        # Preserve original category/title for the report
        r["category"] = c.get("category", "")
        if not r.get("title") or r["title"] == query:
            r["title"] = c.get("title") or cid
        by_id[cid] = r
        INC_PATH.write_text(json.dumps(list(by_id.values()), indent=2), encoding="utf-8")
        tag = ("ERR" if r.get("error")
               else "EXACT" if r.get("exact_top")
               else "OK" if r.get("hit")
               else "CLAR" if r.get("action") == "clarify"
               else "MISS")
        print(f"  [{i}/{len(todo)}] {tag:5s} {cid:<35} cands={(r.get('top_candidates') or [])[:2]}", flush=True)

    # Build final report
    results = [by_id[c["id"]] for c in all_colls if c["id"] in by_id]
    n = len(results)
    exact = sum(1 for r in results if r.get("exact_top"))
    hit = sum(1 for r in results if r.get("hit"))
    clarify = sum(1 for r in results if not r.get("error") and r.get("action") == "clarify")
    errors = sum(1 for r in results if r.get("error"))
    miss = n - hit - clarify - errors

    cat_of = {c["id"]: c["category"] for c in all_colls}
    title_of = {c["id"]: (c.get("title") or c["id"]) for c in all_colls}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = INC_PATH.parent
    jpath = out_dir / f"catalog_verification_{ts}.json"
    mpath = out_dir / f"catalog_verification_{ts}.md"

    jpath.write_text(json.dumps({
        "summary": {
            "total": n, "hit_anywhere": hit, "exact_top": exact,
            "wrong_collection": miss, "clarify": clarify, "errors": errors,
            "location": LOCATION,
        },
        "results": results,
    }, indent=2), encoding="utf-8")

    lines = [
        f"# Data Catalog routing — {ts}",
        "",
        f"Location: **{LOCATION}**  |  Deployment: **gpt-5**",
        "",
        f"**Total**: {n} | **Exact top**: {exact} | **Hit (any rank)**: {hit} | **Wrong**: {miss} | **Clarify**: {clarify} | **Errors**: {errors}",
        "",
    ]
    results_sorted = sorted(results, key=lambda r: (cat_of.get(r["id"], "zzz"), r["id"]))
    current_cat = None
    for r in results_sorted:
        cat = cat_of.get(r["id"], "")
        if cat != current_cat:
            lines += ["", f"## {cat}", "",
                      "| id | title | top candidates | result |",
                      "|----|-------|----------------|--------|"]
            current_cat = cat
        if r.get("error"):
            tag, cands = f"ERR ({r['error'][:40]})", "—"
        elif r.get("exact_top"):
            tag, cands = "EXACT", ", ".join(r["top_candidates"])
        elif r.get("hit"):
            tag, cands = "OK", ", ".join(r["top_candidates"])
        elif r.get("action") == "clarify":
            tag, cands = "CLARIFY", ", ".join(r.get("top_candidates") or [])
        else:
            tag = "WRONG/EMPTY"
            cands = ", ".join(r.get("top_candidates") or []) or (r.get("stac_query") or "")
        title = (title_of.get(r["id"], "") or r["id"])[:55]
        lines.append(f"| `{r['id']}` | {title} | {cands} | {tag} |")

    mpath.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"EXACT={exact}/{n}  HIT={hit}/{n}  WRONG={miss}  CLARIFY={clarify}  ERR={errors}")
    print(f"Wrote: {jpath}")
    print(f"Wrote: {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
