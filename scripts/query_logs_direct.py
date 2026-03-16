"""
Direct Azure Log Analytics Query Script
Query logs directly and display results cleanly
"""
import subprocess
import json
import sys
from datetime import datetime, timedelta

# Configuration
WORKSPACE_ID = "cda38287-9eca-4375-9b39-8ac7a7cc1291"
TIME_WINDOW_MINUTES = 120

# KQL Query to find recent wildfire/MODIS queries
kql_query = f"""
ContainerAppConsoleLogs_CL 
| where TimeGenerated > ago({TIME_WINDOW_MINUTES}m)
| where Log_s contains 'California' or Log_s contains 'wildfire' or Log_s contains 'MODIS' or Log_s contains 'modis-14A1'
| project TimeGenerated, Log_s
| order by TimeGenerated desc
| take 50
"""

print("=" * 100)
print("[SEARCH] QUERYING AZURE LOG ANALYTICS FOR CALIFORNIA WILDFIRE QUERY")
print("=" * 100)
print(f"Workspace ID: {WORKSPACE_ID}")
print(f"Time Window: Last {TIME_WINDOW_MINUTES} minutes")
print(f"Looking for: California, wildfire, MODIS queries")
print("=" * 100)
print()

# Execute az monitor query
cmd = [
    "az", "monitor", "log-analytics", "query",
    "--workspace", WORKSPACE_ID,
    "--analytics-query", kql_query,
    "--output", "json"
]

try:
    print("[LAUNCH] Executing query...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        print(f"[FAIL] Error executing query:")
        print(result.stderr)
        sys.exit(1)
    
    # Parse results
    logs = json.loads(result.stdout)
    
    if not logs:
        print("[WARN]  No matching logs found in the last 2 hours")
        print()
        print("This could mean:")
        print("  1. The query was run more than 2 hours ago")
        print("  2. Logs haven't been ingested yet (5-10 min delay)")
        print("  3. The container app wasn't queried recently")
        sys.exit(0)
    
    print(f"[OK] Found {len(logs)} matching log entries")
    print("=" * 100)
    print()
    
    # Display logs
    for i, log_entry in enumerate(logs, 1):
        timestamp = log_entry.get('TimeGenerated', 'N/A')
        log_msg = log_entry.get('Log_s', '')
        
        # Format timestamp
        if timestamp != 'N/A':
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except:
                pass
        
        print(f"{i}. [{timestamp}]")
        print(f"   {log_msg}")
        print()
    
    print("=" * 100)
    print(f"[OK] Query complete - {len(logs)} entries displayed")
    print("=" * 100)
    
except subprocess.TimeoutExpired:
    print("[FAIL] Query timed out after 60 seconds")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"[FAIL] Failed to parse JSON response: {e}")
    print(f"Raw output: {result.stdout[:500]}")
    sys.exit(1)
except Exception as e:
    print(f"[FAIL] Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
