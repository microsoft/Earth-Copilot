"""Resume + finalize the catalog routing verification from incremental state.

Reads tests/live_results/_catalog_incremental.json, retries any rows that
look like 429 fail-opens (empty candidates, action=execute) or are missing
entirely, then writes the final catalog_verification_<ts>.{json,md}.
"""

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

from verify_catalog_routing import (  # noqa: E402
    CATALOG_PATH,
    LOCATION_OVERRIDES,
    _candidate_ids,
    _hit,
    _short_title,
    run_one,
)

LOCATION = "California"
INC_PATH = Path(__file__).resolve().parent / "live_results" / "_catalog_incremental.json"


async def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    all_colls = []
    for cat in catalog["categories"]:
        for c in cat["collections"]:
            all_colls.append({**c, "category": cat["name"]})

    existing = []
    if INC_PATH.exists():
        existing = json.loads(INC_PATH.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in existing}

    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        raise RuntimeError("AZURE_OPENAI_ENDPOINT must be set before running this script.")
    os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

    agent = LoadAgent()

    def _flush():
        INC_PATH.write_text(
            json.dumps(list(by_id.values()), indent=2), encoding="utf-8"
        )

    # Build to-do list: missing entirely OR fail-open-looking (no cands, execute, no hit)
    todo = []
    for c in all_colls:
        r = by_id.get(c["id"])
        if r is None:
            todo.append(c)
            continue
        if r.get("error"):
            todo.append(c)
            continue
        cands = r.get("top_candidates") or []
        if (
            not r.get("hit")
            and r.get("action") == "execute"
            and not cands
        ):
            todo.append(c)

    print(f"Total collections: {len(all_colls)}  Already-good: {len(all_colls) - len(todo)}  To retry: {len(todo)}", flush=True)

    for i, c in enumerate(todo, 1):
        loc = LOCATION_OVERRIDES.get(c["id"], LOCATION)
        # Aggressive backoff between calls to dodge 429s
        await asyncio.sleep(6.0)
        r = await run_one(agent, c, loc)
        by_id[c["id"]] = r
        _flush()
        cands = (r.get("top_candidates") or [])[:2]
        if r.get("error"):
            tag = "ERR "
        elif r.get("exact_top"):
            tag = "PASS"
        elif r.get("hit"):
            tag = "OK  "
        elif r.get("action") == "clarify":
            tag = "CLAR"
        else:
            tag = "MISS"
        print(f"  [{i}/{len(todo)}] {tag}  {c['id']:<45} cands={cands}", flush=True)

    # Build final report
    results = [by_id[c["id"]] for c in all_colls if c["id"] in by_id]
    n = len(results)
    exact = sum(1 for r in results if r.get("exact_top"))
    hit = sum(1 for r in results if r.get("hit"))
    clarify = sum(1 for r in results if not r.get("error") and r.get("action") == "clarify")
    errors = sum(1 for r in results if r.get("error"))
    miss = n - hit - clarify - errors

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = INC_PATH.parent
    jpath = out_dir / f"catalog_verification_{ts}.json"
    mpath = out_dir / f"catalog_verification_{ts}.md"

    # Group by category for readability
    cat_of = {c["id"]: c["category"] for c in all_colls}
    title_of = {c["id"]: c["title"] for c in all_colls}

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
        f"Location: **{LOCATION}**",
        "",
        f"**Total**: {n} | **Exact top**: {exact} | **Hit (any rank)**: {hit} | **Wrong**: {miss} | **Clarify**: {clarify} | **Errors**: {errors}",
        "",
    ]
    # Sort: category, then id
    results_sorted = sorted(results, key=lambda r: (cat_of.get(r["id"], ""), r["id"]))
    current_cat = None
    for r in results_sorted:
        cat = cat_of.get(r["id"], "")
        if cat != current_cat:
            lines.append("")
            lines.append(f"## {cat}")
            lines.append("")
            lines.append("| id | title | top candidates | result |")
            lines.append("|----|-------|----------------|--------|")
            current_cat = cat
        if r.get("error"):
            tag = f"ERR ({r['error'][:40]})"
            cands = "—"
        elif r.get("exact_top"):
            tag = "EXACT"
            cands = ", ".join(r["top_candidates"])
        elif r.get("hit"):
            tag = "OK"
            cands = ", ".join(r["top_candidates"])
        elif r.get("action") == "clarify":
            tag = "CLARIFY"
            cands = ", ".join(r.get("top_candidates") or [])
        else:
            tag = "WRONG"
            cands = ", ".join(r.get("top_candidates") or []) or (r.get("stac_query") or "")
        title = title_of.get(r["id"], r.get("title", ""))[:60]
        lines.append(f"| `{r['id']}` | {title} | {cands} | {tag} |")

    mpath.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"EXACT={exact}/{n}  HIT={hit}/{n}  WRONG={miss}  CLARIFY={clarify}  ERR={errors}")
    print(f"Wrote: {jpath}")
    print(f"Wrote: {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
