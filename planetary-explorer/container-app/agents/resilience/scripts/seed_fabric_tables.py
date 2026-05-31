"""Seed the Resilience agent's MVP Delta tables into the existing Fabric lakehouse.

Writes three Delta tables to OneLake using the same Fabric workspace + lakehouse
that Site Intel already uses (env-overridable):

    Tables/facilities       \u2014 10-row TX facility registry
    Tables/supply_edges     \u2014 20-row 1-hop supply graph
    Tables/bcp_playbooks    \u2014 5 BCP playbooks (structured JSON)

After this script runs the agent's data_loader.py + ContextExecutor will
automatically prefer the Fabric tables over the bundled seed JSON.

Auth model
----------
This is an *admin* seeding tool, not an OBO call path. It uses the same
app-identity credential chain that ``fabric_client._init_credential`` builds:

    1. FABRIC_CLIENT_ID + FABRIC_CLIENT_SECRET + FABRIC_TENANT_ID  \u2192 SP
    2. DefaultAzureCredential (Managed Identity / az login / VS Code)

The credential must have:
    * **Contributor** (or Member) on the Fabric workspace
    * **Storage Blob Data Contributor** on the OneLake account is *not*
      needed \u2014 Fabric workspace role is what governs OneLake write access.

Usage
-----
PowerShell:

    $env:FABRIC_LAKEHOUSE_WORKSPACE_ID = '<workspace-uuid>'
    $env:FABRIC_LAKEHOUSE_ID = '<lakehouse-uuid>'
    # Optional service principal:
    $env:FABRIC_CLIENT_ID = '<app-id>'
    $env:FABRIC_CLIENT_SECRET = '<secret>'
    $env:FABRIC_TENANT_ID = '<tenant>'

    cd planetary-explorer/container-app
    python -m agents.resilience.scripts.seed_fabric_tables

Or override the target lakehouse on the command line:

    python -m agents.resilience.scripts.seed_fabric_tables `
        --workspace-id <ws> --lakehouse-id <lh> --tables facilities,supply_edges

Idempotent: each write uses ``mode='overwrite'`` so re-running just refreshes
the table. Use ``--dry-run`` to print row counts without writing.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger("resilience.seed_fabric")

_THIS_DIR = Path(__file__).resolve().parent
_SEED_DIR = _THIS_DIR.parent / "seed_data"

DEFAULT_WORKSPACE_ID = os.getenv(
    "RESILIENCE_FABRIC_WORKSPACE_ID",
    os.getenv("FABRIC_LAKEHOUSE_WORKSPACE_ID", ""),
)
DEFAULT_LAKEHOUSE_ID = os.getenv(
    "RESILIENCE_FABRIC_LAKEHOUSE_ID",
    os.getenv("FABRIC_LAKEHOUSE_ID", ""),
)
STORAGE_SCOPE = "https://storage.azure.com/.default"

# Table-name → seed file. Add a fourth table here and it'll just work.
TABLE_SOURCES: dict[str, Path] = {
    "facilities":     _SEED_DIR / "facilities.json",
    "supply_edges":   _SEED_DIR / "supply_edges.json",
    "bcp_playbooks":  _SEED_DIR / "bcp_playbooks.json",
}


def _table_uri(table: str, workspace_id: str, lakehouse_id: str) -> str:
    return (
        f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/"
        f"{lakehouse_id}/Tables/{table}"
    )


def _load_seed(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"seed file missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def _acquire_app_token() -> str:
    """Acquire an app-identity OneLake storage token.

    Mirrors ``fabric_client._init_credential`` so behavior matches the
    container app: SP env vars first, otherwise DefaultAzureCredential.
    """
    try:
        from azure.identity import ClientSecretCredential, DefaultAzureCredential
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "azure-identity is required. Install with: pip install azure-identity"
        ) from exc

    client_id = os.getenv("FABRIC_CLIENT_ID")
    client_secret = os.getenv("FABRIC_CLIENT_SECRET")
    tenant_id = os.getenv("FABRIC_TENANT_ID") or os.getenv("AZURE_TENANT_ID")

    if client_id and client_secret and tenant_id:
        logger.info("auth: ClientSecretCredential (sp=%s)", client_id)
        cred = ClientSecretCredential(tenant_id, client_id, client_secret)
    else:
        logger.info("auth: DefaultAzureCredential (az login / Managed Identity / env)")
        cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)

    token = cred.get_token(STORAGE_SCOPE)
    return token.token


def write_table(
    name: str,
    df: pd.DataFrame,
    workspace_id: str,
    lakehouse_id: str,
    bearer_token: str,
    *,
    dry_run: bool = False,
) -> None:
    uri = _table_uri(name, workspace_id, lakehouse_id)
    logger.info("table %s: %d rows \u2192 %s", name, len(df), uri)

    if dry_run:
        logger.info("  [dry-run] columns: %s", list(df.columns))
        return

    try:
        from deltalake import write_deltalake
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "deltalake is required. Install with: pip install deltalake"
        ) from exc

    # OneLake writes use the same bearer_token + use_fabric_endpoint flag
    # that the read path uses in ``agents/site_audit.py::_load_table``.
    write_deltalake(
        uri,
        df,
        mode="overwrite",
        storage_options={
            "bearer_token": bearer_token,
            "use_fabric_endpoint": "true",
        },
    )
    logger.info("  \u2713 wrote %s", name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Resilience MVP Delta tables.")
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID,
                        help="Fabric workspace UUID (env: FABRIC_LAKEHOUSE_WORKSPACE_ID)")
    parser.add_argument("--lakehouse-id", default=DEFAULT_LAKEHOUSE_ID,
                        help="Fabric lakehouse UUID (env: FABRIC_LAKEHOUSE_ID)")
    parser.add_argument("--tables", default=",".join(TABLE_SOURCES.keys()),
                        help=f"Comma-separated subset of: {','.join(TABLE_SOURCES.keys())}")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load + validate seed data but skip the OneLake write.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.workspace_id or not args.lakehouse_id:
        logger.error(
            "workspace-id and lakehouse-id are required. "
            "Set FABRIC_LAKEHOUSE_WORKSPACE_ID and FABRIC_LAKEHOUSE_ID, "
            "or pass --workspace-id / --lakehouse-id."
        )
        return 2

    table_names = [t.strip() for t in args.tables.split(",") if t.strip()]
    unknown = [t for t in table_names if t not in TABLE_SOURCES]
    if unknown:
        logger.error("unknown table(s): %s; known: %s", unknown, list(TABLE_SOURCES.keys()))
        return 2

    logger.info("workspace=%s lakehouse=%s tables=%s dry_run=%s",
                args.workspace_id, args.lakehouse_id, table_names, args.dry_run)

    # Validate every seed file BEFORE acquiring a token so failures are cheap.
    seeds: dict[str, pd.DataFrame] = {}
    for name in table_names:
        df = _load_seed(TABLE_SOURCES[name])
        if df.empty:
            logger.warning("seed for %s is empty \u2014 skipping", name)
            continue
        seeds[name] = df
        logger.info("  loaded seed %s: %d rows, %d cols", name, len(df), len(df.columns))

    if not seeds:
        logger.error("no non-empty seeds to write")
        return 1

    token = "" if args.dry_run else _acquire_app_token()

    for name, df in seeds.items():
        try:
            write_table(
                name, df,
                workspace_id=args.workspace_id,
                lakehouse_id=args.lakehouse_id,
                bearer_token=token,
                dry_run=args.dry_run,
            )
        except Exception as exc:  # noqa: BLE001 — keep going across tables
            logger.exception("table %s failed: %s", name, exc)
            return 1

    logger.info("done. %d table(s) written.", len(seeds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
