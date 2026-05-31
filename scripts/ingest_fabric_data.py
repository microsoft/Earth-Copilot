# ingest_fabric_data.py
#
# Materializes the 5 GeoAI Accelerator demo tables from real public sources
# into Parquet files (locally first, then optionally uploaded to OneLake).
#
# Tables produced:
#   1. candidate_sites          ← EPA RE-Powering America's Land
#   2. power_infrastructure     ← HIFLD substations + transmission + EIA Form 860
#   3. water_assets             ← USGS NWIS + WRI Aqueduct
#   4. existing_data_centers    ← OpenStreetMap Overpass API
#   5. site_scores_derived      ← empty schema (populated later by the agent)
#
# All sources are public. No synthetic data. Each row carries provenance
# (source_dataset, source_url, retrieval_date).
#
# Usage:
#   python ingest_fabric_data.py --output-dir ./data/lakehouse_seed
#   python ingest_fabric_data.py --table candidate_sites          # one table only
#   python ingest_fabric_data.py --upload-onelake \
#       --workspace-id <workspace-guid> \
#       --lakehouse-id <lakehouse-guid>
#
# Dependencies (pip install):
#   requests pandas geopandas pyarrow shapely tqdm

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import requests
from tqdm import tqdm

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

# States chosen for the demo: high data-center activity + coal retirement +
# water diversity (humid east, dry southwest).
TARGET_STATES = ["VA", "TX", "OH", "GA", "IA", "AZ", "NC", "IL"]

# Minimum parcel acreage for candidate_sites — typical AI campus needs 50+ acres.
MIN_PARCEL_ACRES = 50.0

NOW_ISO = datetime.now(timezone.utc).isoformat()

# ──────────────────────────────────────────────────────────────────────────────
# Source registry
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Source:
    """Provenance record attached to every row from a given dataset."""
    dataset: str        # short stable id, e.g. "EPA-RE-Powering-v2025"
    url: str            # canonical landing page or download URL
    authority: str      # "federal" | "state" | "iso" | "ngo" | "osm"


SOURCES: dict[str, Source] = {
    "epa_repowering": Source(
        dataset="EPA-RE-Powering-AmericasLand-v2025",
        url="https://www.epa.gov/re-powering/re-powering-mapper",
        authority="federal",
    ),
    "osm_substations": Source(
        dataset="OpenStreetMap-Overpass-power_substation",
        url="https://overpass-api.de/",
        authority="osm",
    ),
    "osm_transmission": Source(
        dataset="OpenStreetMap-Overpass-power_line_HV",
        url="https://overpass-api.de/",
        authority="osm",
    ),
    "eia_860_plants": Source(
        dataset="EIA-Form-860-current",
        url="https://www.eia.gov/electricity/data/eia860/",
        authority="federal",
    ),
    "usgs_nwis_sites": Source(
        dataset="USGS-NWIS-SiteService",
        url="https://waterservices.usgs.gov/rest/Site-Service.html",
        authority="federal",
    ),
    "osm_data_centers": Source(
        dataset="OpenStreetMap-Overpass-data_centers",
        url="https://overpass-api.de/",
        authority="osm",
    ),
}


def with_provenance(df: pd.DataFrame, source_key: str) -> pd.DataFrame:
    """Append source_dataset / source_url / source_authority / retrieval_date columns."""
    s = SOURCES[source_key]
    df = df.copy()
    df["source_dataset"] = s.dataset
    df["source_url"] = s.url
    df["source_authority"] = s.authority
    df["retrieval_date"] = NOW_ISO
    return df


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get(url: str, *, params: dict | None = None, timeout: int = 120) -> requests.Response:
    """GET with a polite UA + retry-once on transient failure."""
    headers = {"User-Agent": "GeoAI-Accelerator-Ingest/1.0 (+planetary-explorer)"}
    for attempt in (1, 2):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except (requests.RequestException, requests.HTTPError) as exc:
            if attempt == 2:
                raise
            print(f"  retrying {url} after {exc}", file=sys.stderr)


# ──────────────────────────────────────────────────────────────────────────────
# Table 1 — candidate_sites (EPA RE-Powering)
# ──────────────────────────────────────────────────────────────────────────────

# EPA publishes the full screening dataset as an .xlsx on epa.gov
# (~77 MB, ~190k rows). We download once, cache locally, then filter.
EPA_REPOWERING_XLSX = (
    "https://www.epa.gov/system/files/documents/2023-05/"
    "re-powering-screening-dataset-2022%20Updated.xlsx"
)
EPA_CACHE_NAME = "re-powering-screening-dataset-2022.xlsx"


def _download_to_cache(url: str, cache_path: Path) -> Path:
    """Stream a large download to disk; reuse cache if already present."""
    if cache_path.exists() and cache_path.stat().st_size > 1_000_000:
        print(f"  using cached {cache_path.name} ({cache_path.stat().st_size:,} bytes)")
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=600,
                      headers={"User-Agent": "GeoAI-Accelerator-Ingest/1.0"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with cache_path.open("wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc="  ", leave=False
        ) as bar:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    return cache_path


def fetch_candidate_sites() -> pd.DataFrame:
    """Pull screened brownfield + landfill + mine sites from EPA RE-Powering."""
    print("→ Fetching EPA RE-Powering screening dataset…")
    cache_dir = Path("./data/_cache")
    xlsx_path = _download_to_cache(EPA_REPOWERING_XLSX, cache_dir / EPA_CACHE_NAME)

    # The workbook has several sheets. The site-level data sits on the sheet
    # whose name contains "Site" — we discover it dynamically so a future
    # rename doesn't break us.
    print("  reading workbook (this takes ~30s for 190k rows)…")
    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
    site_sheet = next((s for s in xl.sheet_names if "site" in s.lower()), xl.sheet_names[0])
    print(f"  sheet = {site_sheet!r}; all sheets = {xl.sheet_names}")
    raw = xl.parse(site_sheet)

    # Identify columns case-insensitively (EPA has shuffled capitalization
    # between releases).
    cols = {c.lower().strip(): c for c in raw.columns}

    def col(*candidates: str) -> str | None:
        for cand in candidates:
            if cand.lower() in cols:
                return cols[cand.lower()]
        return None

    c_state = col("state", "site_state", "st")
    c_acre = col("acreage (acres)", "site_acreage", "acreage", "acres", "site acres")
    c_lat = col("latitude", "lat", "y")
    c_lon = col("longitude", "long", "lng", "x")
    c_name = col("site_name", "name", "site")
    c_county = col("county")
    c_type = col("program", "site_type", "type", "facility_type", "site category")
    c_id = col("site_id", "cross-reference number", "id", "epa_id", "registry_id")
    c_status = col("screening_status", "status", "screened", "re-powering profile")

    missing = [n for n, v in {
        "state": c_state, "acreage": c_acre, "lat": c_lat, "lon": c_lon,
    }.items() if v is None]
    if missing:
        raise RuntimeError(
            f"EPA workbook missing expected columns: {missing}. "
            f"Available: {list(raw.columns)[:30]}…"
        )

    df = raw.copy()
    df[c_state] = df[c_state].astype(str).str.strip().str.upper()
    df[c_acre] = pd.to_numeric(df[c_acre], errors="coerce")
    df = df[df[c_state].isin(TARGET_STATES) & (df[c_acre] >= MIN_PARCEL_ACRES)]

    out = pd.DataFrame({
        "site_id": df[c_id] if c_id else range(len(df)),
        "name": df[c_name] if c_name else None,
        "state": df[c_state],
        "county": df[c_county] if c_county else None,
        "parcel_acres": df[c_acre],
        "current_land_use": df[c_type] if c_type else None,
        "screening_status": df[c_status] if c_status else None,
        "latitude": pd.to_numeric(df[c_lat], errors="coerce"),
        "longitude": pd.to_numeric(df[c_lon], errors="coerce"),
        "zoning": None,
        "owner_type": None,
    })
    out = out.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    print(f"  ✓ {len(out)} candidate sites in {TARGET_STATES} ≥ {MIN_PARCEL_ACRES} acres")
    return with_provenance(out, "epa_repowering")


# ──────────────────────────────────────────────────────────────────────────────
# Table 2 — power_infrastructure (OpenStreetMap substations + HV transmission)
# ──────────────────────────────────────────────────────────────────────────────
#
# We use OSM rather than HIFLD because HIFLD's public ArcGIS endpoints were
# reorganized (datasets moved to gii.dhs.gov restricted-access portal).
# OSM has dense US coverage for `power=substation` and `power=line`. Voltage,
# operator, and substation/line-type tags are widely populated for HV assets.

_OVERPASS = "https://overpass-api.de/api/interpreter"

# State bounding boxes (south,west,north,east) — Overpass `area["name"=...]`
# lookups are slow; bbox filters are 10-100x faster.
STATE_BBOX = {
    "VA": (36.54, -83.68, 39.47, -75.24),
    "TX": (25.84, -106.65, 36.50, -93.51),
    "OH": (38.40, -84.82, 41.98, -80.52),
    "GA": (30.36, -85.61, 35.00, -80.84),
    "IA": (40.38, -96.64, 43.50, -90.14),
    "AZ": (31.33, -114.82, 37.00, -109.05),
    "NC": (33.84, -84.32, 36.59, -75.46),
    "IL": (36.97, -91.51, 42.51, -87.50),
}


def _overpass_query(query: str, timeout: int = 240) -> list[dict]:
    """POST an Overpass QL query and return elements[] from the JSON response."""
    r = requests.post(
        _OVERPASS, data={"data": query},
        headers={"User-Agent": "GeoAI-Accelerator-Ingest/1.0"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("elements", [])


def fetch_power_infrastructure() -> pd.DataFrame:
    """OSM substations (any) + transmission lines (voltage ≥ 69 kV) in target states."""
    sub_rows: list[dict] = []
    line_rows: list[dict] = []

    for state, (s, w, n, e) in tqdm(STATE_BBOX.items(), desc="states"):
        bbox = f"{s},{w},{n},{e}"

        # Substations: nodes, ways, and relations tagged power=substation.
        sub_q = f"""
        [out:json][timeout:180];
        (
          node["power"="substation"]({bbox});
          way["power"="substation"]({bbox});
          relation["power"="substation"]({bbox});
        );
        out center tags;
        """
        try:
            elements = _overpass_query(sub_q)
        except Exception as exc:
            print(f"  {state} substations: skipped ({exc})")
            elements = []
        for el in elements:
            tags = el.get("tags", {})
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if lat is None or lon is None:
                continue
            sub_rows.append({
                "asset_id": f"osm-{el['type']}-{el['id']}",
                "type": "substation",
                "name": tags.get("name"),
                "state": state,
                "county": tags.get("addr:county"),
                "voltage_kv": _parse_voltage_kv(tags.get("voltage")),
                "capacity_mw": None,
                "status": tags.get("disused:power") and "disused" or "in_service",
                "latitude": lat,
                "longitude": lon,
                "owner_utility": tags.get("operator"),
            })

        # Transmission lines: power=line with voltage ≥ 69000 V. Overpass
        # can't compare voltage numerically (it's a free-text tag), so we
        # pull all and filter in Python.
        line_q = f"""
        [out:json][timeout:180];
        (
          way["power"="line"]["voltage"]({bbox});
        );
        out center tags;
        """
        try:
            elements = _overpass_query(line_q)
        except Exception as exc:
            print(f"  {state} transmission: skipped ({exc})")
            elements = []
        for el in elements:
            tags = el.get("tags", {})
            v_kv = _parse_voltage_kv(tags.get("voltage"))
            if v_kv is None or v_kv < 69:
                continue
            center = el.get("center", {})
            line_rows.append({
                "asset_id": f"osm-{el['type']}-{el['id']}",
                "type": "transmission_line",
                "name": tags.get("name") or tags.get("ref"),
                "state": state,
                "county": None,
                "voltage_kv": v_kv,
                "capacity_mw": None,
                "status": "in_service",
                "latitude": center.get("lat"),
                "longitude": center.get("lon"),
                "owner_utility": tags.get("operator"),
            })

    subs_df = with_provenance(pd.DataFrame(sub_rows), "osm_substations")
    lines_df = with_provenance(pd.DataFrame(line_rows), "osm_transmission")
    print(f"  ✓ {len(subs_df)} substations + {len(lines_df)} HV transmission lines")
    return pd.concat([subs_df, lines_df], ignore_index=True)


def _parse_voltage_kv(raw: str | None) -> float | None:
    """OSM voltage tag → kV float. Tag can be '230000', '230000;345000', '13.8kV', etc."""
    if not raw:
        return None
    # Take the max if multi-circuit (semicolon-separated).
    candidates = []
    for piece in str(raw).replace(",", ";").split(";"):
        piece = piece.strip().lower().replace("kv", "").replace("v", "").strip()
        try:
            volts = float(piece)
            # If the value looks like volts (>= 1000), convert to kV.
            candidates.append(volts / 1000 if volts >= 1000 else volts)
        except ValueError:
            continue
    return max(candidates) if candidates else None


# ──────────────────────────────────────────────────────────────────────────────
# Table 3 — water_assets (USGS NWIS site service)
# ──────────────────────────────────────────────────────────────────────────────

NWIS_SITE_SERVICE = "https://waterservices.usgs.gov/nwis/site/"


def fetch_water_assets() -> pd.DataFrame:
    """Active USGS stream gages + surface-water withdrawal sites in target states.

    Uses the RDB tab-delimited format (NWIS's most stable export).
    """
    print("→ Fetching USGS NWIS active surface-water sites…")
    frames = []
    for state in tqdm(TARGET_STATES, desc="states"):
        params = {
            "format": "rdb",
            "stateCd": state.lower(),
            "siteType": "ST,LK,ES,SP",   # stream, lake, estuary, spring
            "siteStatus": "active",
            "hasDataTypeCd": "iv",        # has instantaneous values (real-time)
        }
        try:
            r = _get(NWIS_SITE_SERVICE, params=params, timeout=180)
        except Exception as exc:
            print(f"  {state}: skipped ({exc})")
            continue

        # NWIS RDB: comment lines start with '#', then a header row, then a
        # types row ('5s 15s ...'), then data. Strip comments + types row.
        lines = [ln for ln in r.text.splitlines() if not ln.startswith("#")]
        if len(lines) < 3:
            continue
        header = lines[0].split("\t")
        rows = [ln.split("\t") for ln in lines[2:] if ln.strip()]
        df = pd.DataFrame(rows, columns=header)
        df["_state"] = state.upper()      # NWIS doesn't return state in the row; inject from the request loop
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    raw = pd.concat(frames, ignore_index=True)
    df = pd.DataFrame({
        "asset_id": raw["site_no"],
        "name": raw["station_nm"],
        "type": raw["site_tp_cd"].map({
            "ST": "stream", "LK": "lake", "ES": "estuary", "SP": "spring",
        }).fillna("other"),
        "state": raw["_state"],
        "latitude": pd.to_numeric(raw["dec_lat_va"], errors="coerce"),
        "longitude": pd.to_numeric(raw["dec_long_va"], errors="coerce"),
        "huc_code": raw.get("huc_cd"),
    })
    df["permitted_withdrawal_mgd"] = None    # NWIS doesn't expose; WRI Aqueduct enrichment later
    df["available_capacity_mgd"] = None
    df = df.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    print(f"  ✓ {len(df)} water assets")
    return with_provenance(df, "usgs_nwis_sites")


# ──────────────────────────────────────────────────────────────────────────────
# Table 4 — existing_data_centers (OpenStreetMap Overpass API)
# ──────────────────────────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def fetch_existing_data_centers() -> pd.DataFrame:
    """Buildings tagged as data centers in OSM across target states.

    OSM tag: telecom=data_center  OR  office=it  (broader, includes server rooms).
    """
    print("→ Fetching OSM data centers (Overpass API)…")
    # Query US-wide; we filter by state via reverse-geocoding the result coords
    # against the US Census state bboxes (cheap). Overpass area-by-state lookups
    # are slow.
    query = """
    [out:json][timeout:180];
    area["ISO3166-1"="US"][admin_level=2]->.usa;
    (
      node["telecom"="data_center"](area.usa);
      way["telecom"="data_center"](area.usa);
      relation["telecom"="data_center"](area.usa);
    );
    out center tags;
    """
    r = requests.post(OVERPASS_URL, data={"data": query},
                      headers={"User-Agent": "GeoAI-Accelerator/1.0"},
                      timeout=240)
    r.raise_for_status()
    elements = r.json().get("elements", [])
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        rows.append({
            "facility_id": f"osm-{el['type']}-{el['id']}",
            "operator": tags.get("operator") or tags.get("name"),
            "mw_capacity": None,
            "mw_available": None,
            "ppa_clean_energy_pct": None,
            "latency_metro_ms": None,
            "year_online": tags.get("start_date"),
            "latitude": lat,
            "longitude": lon,
            "address": tags.get("addr:full") or
                       " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city"), tags.get("addr:state")])),
        })
    df = pd.DataFrame(rows)
    print(f"  ✓ {len(df)} existing data centers")
    return with_provenance(df, "osm_data_centers")


# ──────────────────────────────────────────────────────────────────────────────
# Table 5 — site_scores_derived (empty schema)
# ──────────────────────────────────────────────────────────────────────────────

def empty_site_scores() -> pd.DataFrame:
    return pd.DataFrame({
        "site_id": pd.Series(dtype="string"),
        "water_score": pd.Series(dtype="float64"),
        "hazard_score": pd.Series(dtype="float64"),
        "grid_score": pd.Series(dtype="float64"),
        "latency_score": pd.Series(dtype="float64"),
        "overall_score": pd.Series(dtype="float64"),
        "confidence": pd.Series(dtype="float64"),
        "pareto_rank": pd.Series(dtype="int64"),
        "last_scored_at": pd.Series(dtype="string"),
        "explanation_blob": pd.Series(dtype="string"),
        "evidence_doc_ids": pd.Series(dtype="string"),  # JSON-encoded list
    })


# ──────────────────────────────────────────────────────────────────────────────
# OneLake upload (optional)
# ──────────────────────────────────────────────────────────────────────────────

def upload_to_onelake(parquet_path: Path, workspace_id: str, lakehouse_id: str,
                      table_name: str, region: str = "westus") -> None:
    """Upload a parquet file to OneLake under <lakehouse>/Files/seed/<table>/.

    We write to Files/ (not Tables/) because Tables/ requires Delta format.
    A follow-up Fabric notebook converts Files/seed/<table>/*.parquet → Tables/<table>
    as a Delta table for SQL endpoint access.

    Uses the regional OneLake DFS endpoint, e.g.:
        https://westus-onelake.dfs.fabric.microsoft.com/{workspace}/{lakehouse}.Lakehouse/Files/seed/{table}/

    Auth: DefaultAzureCredential — picks up `az login` user, env vars, or
    managed identity. The principal must have Contributor on the workspace.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.filedatalake import DataLakeServiceClient
    except ImportError:
        raise SystemExit(
            "OneLake upload requires: pip install azure-identity azure-storage-file-datalake"
        )

    account_url = f"https://{region}-onelake.dfs.fabric.microsoft.com"
    print(f"→ Uploading {parquet_path.name} → {account_url}/.../Files/seed/{table_name}/")
    cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    service = DataLakeServiceClient(account_url=account_url, credential=cred)
    fs = service.get_file_system_client(file_system=workspace_id)
    # When workspace+lakehouse are referenced by GUID (the normal case via
    # the REST API), OneLake DFS rejects the ".Lakehouse" suffix. The suffix
    # is only required when using friendly display names.
    looks_like_guid = (
        len(lakehouse_id) == 36
        and lakehouse_id.count("-") == 4
        and all(c in "0123456789abcdef-" for c in lakehouse_id.lower())
    )
    lh_segment = lakehouse_id if looks_like_guid else f"{lakehouse_id}.Lakehouse"
    file_path = f"{lh_segment}/Files/seed/{table_name}/{parquet_path.name}"
    file_client = fs.get_file_client(file_path)
    with parquet_path.open("rb") as f:
        file_client.upload_data(f, overwrite=True)
    print(f"  ✓ uploaded to {file_path}")


# ──────────────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────────────

LOADERS: dict[str, Callable[[], pd.DataFrame]] = {
    "candidate_sites": fetch_candidate_sites,
    "power_infrastructure": fetch_power_infrastructure,
    "water_assets": fetch_water_assets,
    "existing_data_centers": fetch_existing_data_centers,
    "site_scores_derived": empty_site_scores,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, default=Path("./data/lakehouse_seed"))
    ap.add_argument("--table", choices=list(LOADERS), help="Run a single table only")
    ap.add_argument("--upload-onelake", action="store_true")
    ap.add_argument("--workspace-id", help="Fabric workspace GUID (required with --upload-onelake)")
    ap.add_argument("--lakehouse-id", help="Fabric lakehouse GUID (required with --upload-onelake)")
    ap.add_argument("--onelake-region", default="westus", help="OneLake regional endpoint prefix")
    args = ap.parse_args()

    if args.upload_onelake and not (args.workspace_id and args.lakehouse_id):
        ap.error("--upload-onelake requires --workspace-id AND --lakehouse-id")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    tables = [args.table] if args.table else list(LOADERS)
    manifest = {}
    for name in tables:
        print(f"\n══════════ {name} ══════════")
        try:
            df = LOADERS[name]()
        except Exception as exc:
            print(f"  ✗ {name} failed: {exc}", file=sys.stderr)
            manifest[name] = {"status": "error", "error": str(exc)}
            continue

        out = args.output_dir / f"{name}.parquet"
        df.to_parquet(out, index=False)
        manifest[name] = {
            "status": "ok",
            "rows": int(len(df)),
            "columns": list(df.columns),
            "path": str(out.resolve()),
            "size_bytes": out.stat().st_size,
        }
        print(f"  → wrote {out} ({len(df)} rows, {out.stat().st_size:,} bytes)")

        if args.upload_onelake:
            try:
                upload_to_onelake(out, args.workspace_id, args.lakehouse_id, name,
                                  region=args.onelake_region)
                manifest[name]["uploaded"] = True
            except Exception as exc:
                print(f"  ✗ upload failed: {exc}", file=sys.stderr)
                manifest[name]["uploaded"] = False
                manifest[name]["upload_error"] = str(exc)

    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\n→ manifest: {manifest_path}")

    failed = [n for n, m in manifest.items() if m["status"] == "error"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
