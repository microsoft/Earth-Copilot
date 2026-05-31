"""Convert seed parquet files in Files/seed/<table>/ to Delta tables in Tables/<table>/.

Uses the rust-based `deltalake` library to write directly to OneLake — no Spark
notebook or Fabric job required. The resulting Delta tables are auto-discovered
by the Lakehouse SQL endpoint and become queryable from Fabric, Power BI,
Direct Lake, and Notebooks.

Auth: AzureCliCredential (the user must be a workspace Contributor).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
from azure.identity import AzureCliCredential
from deltalake import write_deltalake

# Set FABRIC_LAKEHOUSE_WORKSPACE_ID + FABRIC_LAKEHOUSE_ID env vars before running.
WORKSPACE_ID = os.environ["FABRIC_LAKEHOUSE_WORKSPACE_ID"]
LAKEHOUSE_ID = os.environ["FABRIC_LAKEHOUSE_ID"]
ONELAKE_HOST = "onelake.dfs.fabric.microsoft.com"

SEED_DIR = Path("./data/lakehouse_seed")

TABLES = [
    "candidate_sites",
    "power_infrastructure",
    "water_assets",
    "existing_data_centers",
    "site_scores_derived",
]


def main() -> int:
    # Strip env-var SP creds so DefaultAzureCredential doesn't pick up the
    # FABRIC_* container-app SP (which is a workspace member but may not have
    # OneLake write rights at the per-table level).
    for var in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
        os.environ.pop(var, None)

    cred = AzureCliCredential()
    token = cred.get_token("https://storage.azure.com/.default").token

    storage_options = {
        "bearer_token": token,
        "use_fabric_endpoint": "true",
    }

    for table in TABLES:
        parquet_path = SEED_DIR / f"{table}.parquet"
        if not parquet_path.exists():
            print(f"  ✗ skip {table}: {parquet_path} not found")
            continue

        df = pd.read_parquet(parquet_path)
        print(f"→ {table}: {len(df):,} rows / {len(df.columns)} cols")

        # Coerce object cols to string so Arrow can serialize them
        # consistently (some EPA / OSM cols mix str + None + numeric).
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype("string")

        table_uri = (
            f"abfss://{WORKSPACE_ID}@{ONELAKE_HOST}/"
            f"{LAKEHOUSE_ID}/Tables/{table}"
        )

        write_deltalake(
            table_uri,
            pa.Table.from_pandas(df, preserve_index=False),
            mode="overwrite",
            schema_mode="overwrite",
            storage_options=storage_options,
        )
        print(f"  ✓ wrote Delta to Tables/{table}")

    print("\nDone. Open the Lakehouse in Fabric and refresh — the 5 tables "
          "should appear under Tables/ and be queryable via the SQL endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
