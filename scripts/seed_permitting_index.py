"""
Seed the `permitting-docs` Azure AI Search index with REAL public documents.

Source: Wikipedia REST API. We fetch ~30 articles spanning:
  - Major US data center facilities (with coordinates from Wikipedia infoboxes)
  - Permitting / regulatory policy articles (FERC, NEPA, PUCs, interconnection)
  - State-level data center hubs (NoVa, Quincy WA, Maiden NC, etc.)

Why Wikipedia: every article has a stable public URL, plain-text content via
the REST API, and coordinates encoded in `prop=coordinates` for facility
articles. That gives us real text + real geo-tags for the geo-distance
search filter. Real FERC orders / EIS documents can be added later via a
PDF cracking skillset; for the integration proof, Wikipedia is sufficient
and produces convincing semantic-search hits.

Index schema:
  id            Edm.String         key
  title         Edm.String         searchable, retrievable
  content       Edm.String         searchable, retrievable  (intro text, ~500 words)
  source_url    Edm.String         retrievable
  doc_date      Edm.DateTimeOffset filterable, sortable
  doc_type      Edm.String         filterable, facetable    ("facility" | "policy" | "regulator")
  state         Edm.String         filterable, facetable
  location      Edm.GeographyPoint filterable, sortable     (POINT(lng lat))

Run:
  python scripts/seed_permitting_index.py \
    --service-name srch-planetaryexplorer-dev \
    --admin-key <key>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

# ──────────────────────────────────────────────────────────────────────────────
# Curated source list. Each entry is a Wikipedia article that is either a
# specific data center facility (geo-tagged) or a permitting / regulatory
# topic. State is hand-set; for facility articles we use the article's own
# coordinates.
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Seed:
    title: str
    doc_type: str       # "facility" | "policy" | "regulator"
    state: str | None   # 2-letter, or None for nationwide policy docs


SEEDS: list[Seed] = [
    # ── Facility articles (have coordinates on Wikipedia) ──
    Seed("Microsoft Quincy data center campus", "facility", "WA"),
    Seed("Yahoo! East Wenatchee data center", "facility", "WA"),
    Seed("Lakeside Technology Center", "facility", "IL"),
    Seed("The Dalles, Oregon", "facility", "OR"),               # Google Dalles DC
    Seed("Apple Maiden data center", "facility", "NC"),
    Seed("Apple Mesa data center", "facility", "AZ"),
    Seed("Apple Reno data center", "facility", "NV"),
    Seed("Apple Prineville data center", "facility", "OR"),
    Seed("Facebook Prineville Data Center", "facility", "OR"),
    Seed("Meta Forest City data center", "facility", "NC"),
    Seed("Facebook Eagle Mountain Data Center", "facility", "UT"),
    Seed("Google Council Bluffs Data Center", "facility", "IA"),
    Seed("Switch Las Vegas", "facility", "NV"),
    Seed("Iron Mountain Underground Storage", "facility", "PA"),

    # ── Hubs / regions (geo-rough, useful for NoVa-style queries) ──
    Seed("Data centers in Northern Virginia", "facility", "VA"),
    Seed("Loudoun County, Virginia", "facility", "VA"),

    # ── Regulator + policy (no geo; we still index but with state=None) ──
    Seed("Federal Energy Regulatory Commission", "regulator", None),
    Seed("Interconnection (electric grid)", "policy", None),
    Seed("Open Access Same-Time Information System", "policy", None),
    Seed("Public utility commission", "regulator", None),
    Seed("Environmental impact statement", "policy", None),
    Seed("National Environmental Policy Act", "policy", None),
    Seed("Power purchase agreement", "policy", None),
    Seed("PJM Interconnection", "regulator", "PA"),
    Seed("Electric Reliability Council of Texas", "regulator", "TX"),
    Seed("Midcontinent Independent System Operator", "regulator", "IN"),
    Seed("California Independent System Operator", "regulator", "CA"),

    # ── Issue-specific permitting ──
    Seed("Data center water usage", "policy", None),
    Seed("Data center cooling", "policy", None),
    Seed("Brownfield land", "policy", None),
]


# ──────────────────────────────────────────────────────────────────────────────
# Wikipedia fetch
# ──────────────────────────────────────────────────────────────────────────────

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "GeoAI-Accelerator-Seed/1.0 (https://github.com/microsoft/planetary-explorer)"


def fetch_article(title: str) -> dict[str, Any] | None:
    """Get plain-text intro extract + coordinates (if any) for a Wikipedia article."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|coordinates|info",
        "exintro": "true",
        "explaintext": "true",
        "exsectionformat": "plain",
        "inprop": "url",
        "redirects": "1",
        "titles": title,
    }
    r = requests.get(WIKI_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    data = r.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None
    page = next(iter(pages.values()))
    if "missing" in page:
        return None

    extract = (page.get("extract") or "").strip()
    if not extract or len(extract) < 100:
        return None

    coords = None
    if page.get("coordinates"):
        c = page["coordinates"][0]
        coords = {"lat": float(c["lat"]), "lng": float(c["lon"])}

    return {
        "title": page.get("title"),
        "content": extract[:8000],            # cap to keep payloads small
        "source_url": page.get("fullurl") or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        "coords": coords,
        "page_id": page.get("pageid"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Azure AI Search
# ──────────────────────────────────────────────────────────────────────────────

API_VERSION = "2023-11-01"

INDEX_SCHEMA = {
    "name": "permitting-docs",
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "searchable": False, "filterable": True},
        {"name": "title", "type": "Edm.String", "searchable": True, "retrievable": True},
        {"name": "content", "type": "Edm.String", "searchable": True, "retrievable": True, "analyzer": "en.microsoft"},
        {"name": "source_url", "type": "Edm.String", "searchable": False, "retrievable": True, "filterable": False},
        {"name": "doc_date", "type": "Edm.DateTimeOffset", "filterable": True, "sortable": True, "retrievable": True},
        {"name": "doc_type", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
        {"name": "state", "type": "Edm.String", "filterable": True, "facetable": True, "retrievable": True},
        {"name": "location", "type": "Edm.GeographyPoint", "filterable": True, "sortable": True, "retrievable": True},
    ],
    "semantic": {
        "configurations": [
            {
                "name": "default",
                "prioritizedFields": {
                    "titleField": {"fieldName": "title"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                    "prioritizedKeywordsFields": [{"fieldName": "doc_type"}, {"fieldName": "state"}],
                },
            }
        ]
    },
}


def search_url(service_name: str, path: str) -> str:
    return f"https://{service_name}.search.windows.net{path}?api-version={API_VERSION}"


def create_or_update_index(service_name: str, admin_key: str) -> None:
    url = search_url(service_name, f"/indexes/{INDEX_SCHEMA['name']}")
    r = requests.put(
        url,
        headers={"api-key": admin_key, "Content-Type": "application/json"},
        json=INDEX_SCHEMA,
        timeout=30,
    )
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"Index create/update failed: {r.status_code} {r.text[:500]}")
    print(f"  ✓ index `{INDEX_SCHEMA['name']}` ready")


def upload_docs(service_name: str, admin_key: str, docs: list[dict[str, Any]]) -> None:
    url = search_url(service_name, f"/indexes/{INDEX_SCHEMA['name']}/docs/index")
    payload = {"value": [{"@search.action": "mergeOrUpload", **d} for d in docs]}
    r = requests.post(
        url,
        headers={"api-key": admin_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Upload failed: {r.status_code} {r.text[:500]}")
    summary = r.json()
    succeeded = sum(1 for x in summary.get("value", []) if x.get("status"))
    print(f"  ✓ uploaded {succeeded}/{len(docs)} docs")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--service-name", required=True, help="Azure AI Search service name (no .search.windows.net)")
    ap.add_argument("--admin-key", required=True)
    ap.add_argument("--dry-run", action="store_true", help="Fetch + print docs but do not upload")
    args = ap.parse_args()

    print(f"→ Fetching {len(SEEDS)} Wikipedia articles…")
    docs: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).isoformat()
    for s in SEEDS:
        try:
            page = fetch_article(s.title)
        except Exception as exc:
            print(f"  ✗ {s.title}: {exc}")
            continue
        if not page:
            print(f"  ✗ {s.title}: not found / too short")
            continue

        doc: dict[str, Any] = {
            "id": f"wiki-{page['page_id']}",
            "title": page["title"],
            "content": page["content"],
            "source_url": page["source_url"],
            "doc_date": today,
            "doc_type": s.doc_type,
            "state": s.state,
        }
        if page["coords"]:
            doc["location"] = {
                "type": "Point",
                "coordinates": [page["coords"]["lng"], page["coords"]["lat"]],
            }
        docs.append(doc)
        geo = "with geo" if page["coords"] else "no geo"
        print(f"  ✓ {page['title']} ({len(page['content']):,} chars, {geo})")
        time.sleep(0.2)  # be polite to wikipedia

    print(f"\n→ Fetched {len(docs)} docs ({sum(1 for d in docs if 'location' in d)} geo-tagged)")

    if args.dry_run:
        print(json.dumps(docs[0], indent=2)[:1500])
        return 0

    print("\n→ Creating / updating Azure AI Search index…")
    create_or_update_index(args.service_name, args.admin_key)

    print("→ Uploading docs…")
    # batch size 100 max for the indexing API
    for i in range(0, len(docs), 100):
        upload_docs(args.service_name, args.admin_key, docs[i : i + 100])

    print("\nDone. Verify with:")
    print(f'  curl -H "api-key: <key>" "https://{args.service_name}.search.windows.net/indexes/{INDEX_SCHEMA["name"]}/docs?api-version={API_VERSION}&search=*&$count=true&$top=3"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
