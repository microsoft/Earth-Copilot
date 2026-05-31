"""Verify routing for every collection listed in the public Data Catalog.

For each collection in web-ui/public/pc_collections_metadata.json we ask
LoadAgent "Show <title> for California" (or another popular target if the
collection has limited extent — handled per-id below) and assert that the
collection id appears in the top candidates or stac_query.

Outputs:
  tests/live_results/catalog_verification_<ts>.{json,md}
"""

from __future__ import annotations

import argparse
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

CATALOG_PATH = (
    ROOT.parents[0] / "web-ui" / "public" / "pc_collections_metadata.json"
)

# Collections whose footprint excludes CONUS — override the test location.
# Default is "California". For these we use a region where data exists.
LOCATION_OVERRIDES: dict[str, str] = {
    # Ocean-only / global ocean collections still work for CA coast,
    # so we keep default for SST/water.
    # Add overrides here if a collection truly fails for CA.
}


def _short_title(title: str) -> str:
    """Shorten the long PC titles to something a user would actually type."""
    # Strip trailing parens, version markers, vendor suffixes
    t = title.split(" - ")[0]
    if "(" in t:
        head, _, _ = t.partition("(")
        head = head.strip()
        if len(head) >= 10:
            t = head
    return t.strip()


def _candidate_ids(plan) -> list[str]:
    out = []
    for c in plan.collection_candidates or []:
        cid = getattr(c, "id", None) or (
            c.get("id") if isinstance(c, dict) else None
        )
        if cid:
            out.append(cid)
    return out


def _hit(expected_id: str, plan) -> bool:
    eid = expected_id.lower()
    hay = " ".join(
        [
            (plan.stac_query or "").lower(),
            " ".join(_candidate_ids(plan)).lower(),
            (getattr(plan, "collection_id", None) or "").lower(),
        ]
    )
    return eid in hay


async def run_one(agent: LoadAgent, coll: dict, location: str) -> dict:
    cid = coll["id"]
    title = coll["title"]
    short = _short_title(title)
    query = f"Show {short} for {location}"

    t0 = time.perf_counter()
    plan = None
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            payload = LoadAgentInput(query=query, location_name=location)
            plan = await asyncio.wait_for(agent.plan(payload), timeout=60.0)
            last_err = None
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(2.0 * (attempt + 1))
    if plan is None:
        return {
            "id": cid,
            "title": title,
            "query": query,
            "location": location,
            "error": f"{type(last_err).__name__}: {last_err}" if last_err else "unknown",
        }
    dt = time.perf_counter() - t0

    cands = _candidate_ids(plan)
    return {
        "id": cid,
        "title": title,
        "query": query,
        "location": location,
        "action": plan.action,
        "stac_query": plan.stac_query,
        "top_candidates": cands[:5],
        "hit": _hit(cid, plan),
        "exact_top": bool(cands and cands[0].lower() == cid.lower()),
        "clarification_question": plan.clarification_question,
        "latency_s": round(dt, 2),
        "error": None,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="California")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="Filter by collection id substring")
    args = ap.parse_args()

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    all_colls = []
    for cat in catalog["categories"]:
        for c in cat["collections"]:
            all_colls.append({**c, "category": cat["name"]})

    if args.only:
        all_colls = [c for c in all_colls if args.only.lower() in c["id"].lower()]
    if args.limit:
        all_colls = all_colls[: args.limit]

    if not os.environ.get("AZURE_OPENAI_ENDPOINT"):
        raise RuntimeError("AZURE_OPENAI_ENDPOINT must be set before running this script.")
    os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

    agent = LoadAgent()
    sem = asyncio.Semaphore(args.concurrency)

    incremental_path = (
        Path(__file__).resolve().parent
        / "live_results"
        / "_catalog_incremental.json"
    )
    incremental_path.parent.mkdir(exist_ok=True)
    results_by_id: dict[str, dict] = {}

    def _flush():
        incremental_path.write_text(
            json.dumps(list(results_by_id.values()), indent=2), encoding="utf-8"
        )

    print(f"Verifying {len(all_colls)} catalog collections @ '{args.location}' (concurrency={args.concurrency})")

    async def _bounded(coll):
        async with sem:
            try:
                loc = LOCATION_OVERRIDES.get(coll["id"], args.location)
                r = await run_one(agent, coll, loc)
            except Exception as e:  # noqa: BLE001
                r = {
                    "id": coll["id"],
                    "title": coll.get("title", ""),
                    "query": "",
                    "location": args.location,
                    "error": f"_bounded: {type(e).__name__}: {e}",
                }
            results_by_id[coll["id"]] = r
            _flush()
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
            cands = (r.get("top_candidates") or [])[:2]
            print(f"  {tag}  {coll['id']:<45} cands={cands}", flush=True)
            return r

    # First pass: parallel
    await asyncio.gather(*[_bounded(c) for c in all_colls], return_exceptions=True)

    # Retry pass: any "MISS" (action=execute but no candidates) → likely 429 fail-open.
    needs_retry = [
        c for c in all_colls
        if not results_by_id[c["id"]].get("hit")
        and not results_by_id[c["id"]].get("error")
        and results_by_id[c["id"]].get("action") == "execute"
        and not (results_by_id[c["id"]].get("top_candidates") or [])
    ]
    if needs_retry:
        print(f"\nRetrying {len(needs_retry)} cases that appear to have hit 429 fail-open...")
        for c in needs_retry:
            await asyncio.sleep(8)  # cool-off between retries
            loc = LOCATION_OVERRIDES.get(c["id"], args.location)
            r = await run_one(agent, c, loc)
            results_by_id[c["id"]] = r
            _flush()
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
            cands = (r.get("top_candidates") or [])[:2]
            print(f"  retry {tag}  {c['id']:<45} cands={cands}", flush=True)

    results = [results_by_id[c["id"]] for c in all_colls]

    n = len(results)
    exact = sum(1 for r in results if r.get("exact_top"))
    hit = sum(1 for r in results if r.get("hit"))
    clarify = sum(
        1 for r in results if not r.get("error") and r.get("action") == "clarify"
    )
    errors = sum(1 for r in results if r.get("error"))
    miss = n - hit - clarify - errors

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent / "live_results"
    out_dir.mkdir(exist_ok=True)
    jpath = out_dir / f"catalog_verification_{ts}.json"
    mpath = out_dir / f"catalog_verification_{ts}.md"

    jpath.write_text(
        json.dumps(
            {
                "summary": {
                    "total": n,
                    "hit_anywhere": hit,
                    "exact_top": exact,
                    "wrong_collection": miss,
                    "clarify": clarify,
                    "errors": errors,
                    "location": args.location,
                },
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Data Catalog routing — {ts}",
        "",
        f"Location: **{args.location}**",
        "",
        f"**Total**: {n} | **Exact top**: {exact} | **Hit (any rank)**: {hit} | **Wrong**: {miss} | **Clarify**: {clarify} | **Errors**: {errors}",
        "",
        "| id | title | top candidates | result |",
        "|----|-------|----------------|--------|",
    ]
    for r in results:
        if r.get("error"):
            tag = f"ERR ({r['error'][:60]})"
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
        lines.append(
            f"| `{r['id']}` | {r['title'][:60]} | {cands} | {tag} |"
        )
    mpath.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(
        f"EXACT={exact}/{n}  HIT={hit}/{n}  WRONG={miss}  CLARIFY={clarify}  ERR={errors}"
    )
    print(f"Wrote: {jpath}")
    print(f"Wrote: {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
