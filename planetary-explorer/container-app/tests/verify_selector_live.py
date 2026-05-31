"""Live smoke-test of collection_selector.select_collection against
the real MPC public catalog. Proves the v2 pipeline picks sane ids for
a representative slice of natural-language queries before we flip
COLLECTION_SELECTOR=v2 in prod.

Run:
  $env:AZURE_OPENAI_ENDPOINT="https://<your-aoai-account>.cognitiveservices.azure.com/"
  $env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5"
  $env:AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
  python -u tests/verify_selector_live.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collection_index import get_collection_index  # noqa: E402
from collection_selector import select_collection  # noqa: E402

# Curated representative queries spanning the public PC families plus
# the historically problematic facet-token leakers and v1/v2 ambiguity
# pairs identified by tests/verify_catalog_routing.py.
QUERIES = [
    # Natural-language family lookups
    ("show sentinel-2 imagery for california", "sentinel-2-l2a"),
    ("landsat 8 for california",                "landsat-c2-l2"),
    ("naip aerial imagery",                     "naip"),
    ("modis snow cover daily",                  "modis-10A1-061"),
    ("modis snow cover 8-day",                  "modis-10A2-061"),
    ("modis ndvi 250m",                         "modis-13Q1-061"),
    ("modis ndvi 500m",                         "modis-13A1-061"),
    ("modis land surface temperature daily",    "modis-11A1-061"),
    ("modis burned area",                       "modis-64A1-061"),
    ("io land cover annual v2",                 "io-lulc-annual-v02"),
    ("io land cover 9 class v1",                "io-lulc-9-class"),
    ("esri 10m land cover",                     "io-lulc"),
    ("chesapeake land cover 13 class",          "chesapeake-lc-13"),
    ("chesapeake land cover 7 class",           "chesapeake-lc-7"),
    ("copernicus dem 30 meter",                 "cop-dem-glo-30"),
    ("copernicus dem 90 meter",                 "cop-dem-glo-90"),
    ("3dep lidar dtm",                          "3dep-lidar-dtm"),
    ("3dep seamless dem",                       "3dep-seamless"),
    ("nasadem elevation",                       "nasadem"),
    ("hls landsat",                             "hls2-l30"),
    ("hls sentinel",                            "hls2-s30"),
    ("noaa mrms 1 hour precipitation",          "noaa-mrms-qpe-1h-pass1"),
    # Exact-id short-circuit
    ('"sentinel-2-l2a"',                        "sentinel-2-l2a"),
    ("sentinel-2-l2a",                          "sentinel-2-l2a"),
    # Domain phrases (no sensor named)
    ("snow cover for the rockies",              "modis-10A1-061"),
    ("burned area for california fires",        "modis-64A1-061"),
    ("vegetation index for amazon",             "modis-13Q1-061"),
    ("elevation map of nepal",                  "cop-dem-glo-30"),
]


async def main() -> int:
    print(f"AOAI endpoint:   {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    print(f"Chat deployment: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME')}")
    print(f"Embedding dep:   {os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', '(unset -> lexical fallback)')}")
    print()
    idx = await get_collection_index()
    snap = await idx.snapshot("public")
    print(f"Live public inventory: {len(snap)} collections cached")
    if not snap:
        print("ERROR: empty inventory -- cannot proceed")
        return 1
    print()

    rows = []
    ok = 0
    soft = 0
    bad = 0
    for q, expected in QUERIES:
        t0 = time.monotonic()
        try:
            sel = await asyncio.wait_for(
                select_collection(q, "public"), timeout=45.0
            )
        except Exception as e:
            sel = None
            err = f"{type(e).__name__}: {e}"
        else:
            err = None
        dt = (time.monotonic() - t0) * 1000.0

        picked = sel.collection_id if sel else None
        stage = sel.stage if sel else "error"
        preset = sel.render_preset if sel else None
        conf = sel.confidence if sel else 0.0
        cand = list(sel.candidates) if sel else []

        if err:
            tag = "ERR"
            bad += 1
        elif picked == expected:
            tag = "OK "
            ok += 1
        elif expected in cand:
            tag = "SOFT"
            soft += 1
        else:
            tag = "BAD"
            bad += 1

        rows.append({
            "query": q, "expected": expected, "picked": picked,
            "stage": stage, "preset": preset, "confidence": conf,
            "candidates": cand[:5], "tag": tag, "elapsed_ms": dt,
            "error": err,
        })
        print(f"  {tag} [{stage:12s}] q={q!r:55s} -> {picked!r:30s} (exp={expected}, conf={conf:.2f}, {dt:.0f}ms)")

    total = len(QUERIES)
    print()
    print(f"=== {ok}/{total} OK, {soft} SOFT (expected in top-K), {bad} BAD ===")

    out = Path(__file__).resolve().parent / "live_results" / "selector_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "summary": {"total": total, "ok": ok, "soft": soft, "bad": bad},
        "rows": rows,
    }, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
