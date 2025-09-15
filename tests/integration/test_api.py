import requests
import json

url = "http://localhost:7071/api/query"
payload = {"query": "Show me Landsat 8 imagery over Seattle from 2023"}
headers = {"Content-Type": "application/json"}

try:
    response = requests.post(url, json=payload, headers=headers)
    print("Status Code:", response.status_code)
    print("Response Headers:", dict(response.headers))
    print("Response Body:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Error:", str(e))
    print("Raw response:", response.text if 'response' in locals() else "No response")
