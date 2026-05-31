from pathlib import Path
import os
import sys
sys.path.insert(0, "scripts")
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

WS = os.environ["FABRIC_LAKEHOUSE_WORKSPACE_ID"]
LH = os.environ["FABRIC_LAKEHOUSE_ID"]
REGION = os.environ.get("FABRIC_ONELAKE_REGION", "westus")

account_url = f"https://{REGION}-onelake.dfs.fabric.microsoft.com"
cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
service = DataLakeServiceClient(account_url=account_url, credential=cred)
fs = service.get_file_system_client(file_system=WS)

results = []
for p in sorted(Path("data/lakehouse_seed").glob("*.parquet")):
    name = p.stem
    # OneLake with GUIDs: no .Lakehouse suffix
    file_path = f"{LH}/Files/seed/{name}/{p.name}"
    print(f"-> {file_path} ({p.stat().st_size} bytes)")
    try:
        fc = fs.get_file_client(file_path)
        with p.open("rb") as f:
            fc.upload_data(f, overwrite=True)
        print(f"  OK {name}")
        results.append((name, "ok", None))
    except Exception as e:
        print(f"  X {name}: {e!r}")
        results.append((name, "error", repr(e)))

print("\n=== SUMMARY ===")
for r in results:
    print(r)
