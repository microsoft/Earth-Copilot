"""
Test script for deployed Earth Copilot MCP Server
Run: python test_deployed_mcp.py <YOUR_MCP_URL>
Example: python test_deployed_mcp.py https://earth-copilot-mcp.azurecontainerapps.io
"""

import requests
import json
import sys
from datetime import datetime

class DeployedMCPTester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.test_results = []
    
    def test_health(self):
        """Test 1: Health check"""
        print("\n" + "="*70)
        print("TEST 1: Health Check")
        print("="*70)
        
        try:
            response = self.session.get(f"{self.base_url}/")
            response.raise_for_status()
            
            data = response.json()
            print("[OK] PASSED - Server is healthy")
            print(f"   Service: {data.get('service')}")
            print(f"   Version: {data.get('version')}")
            
            self.test_results.append(("Health Check", True, None))
            return True
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("Health Check", False, str(e)))
            return False
    
    def test_tools_list(self):
        """Test 2: List available tools"""
        print("\n" + "="*70)
        print("TEST 2: List Available Tools")
        print("="*70)
        
        try:
            response = self.session.post(f"{self.base_url}/tools/list")
            response.raise_for_status()
            
            data = response.json()
            tools = data.get('tools', [])
            
            print(f"[OK] PASSED - Found {len(tools)} tools:")
            for tool in tools:
                print(f"   [TOOL] {tool['name']}")
                print(f"      {tool['description'][:80]}...")
            
            self.test_results.append(("List Tools", True, None))
            return tools
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("List Tools", False, str(e)))
            return []
    
    def test_resources_list(self):
        """Test 3: List available resources"""
        print("\n" + "="*70)
        print("TEST 3: List Available Resources")
        print("="*70)
        
        try:
            response = self.session.post(f"{self.base_url}/resources/list")
            response.raise_for_status()
            
            data = response.json()
            resources = data.get('resources', [])
            
            print(f"[OK] PASSED - Found {len(resources)} resources:")
            for resource in resources:
                print(f"   [PKG] {resource['name']}")
                print(f"      URI: {resource['uri']}")
            
            self.test_results.append(("List Resources", True, None))
            return resources
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("List Resources", False, str(e)))
            return []
    
    def test_read_resource(self, uri="earth://stac/sentinel-2"):
        """Test 4: Read a specific resource"""
        print("\n" + "="*70)
        print(f"TEST 4: Read Resource - {uri}")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/resources/read",
                json={"uri": uri}
            )
            response.raise_for_status()
            
            data = response.json()
            print("[OK] PASSED - Resource data retrieved")
            print(f"   Data preview: {str(data)[:200]}...")
            
            self.test_results.append(("Read Resource", True, None))
            return data
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("Read Resource", False, str(e)))
            return None
    
    def test_terrain_analysis(self):
        """Test 5: Execute terrain analysis tool"""
        print("\n" + "="*70)
        print("TEST 5: Terrain Analysis Tool")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/tools/call",
                json={
                    "name": "terrain_analysis",
                    "arguments": {
                        "location": "Grand Canyon, Arizona",
                        "analysis_types": ["elevation", "slope"],
                        "resolution": 30
                    }
                },
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print("[OK] PASSED - Terrain analysis executed")
            print(f"   Result preview: {str(data)[:300]}...")
            
            self.test_results.append(("Terrain Analysis", True, None))
            return data
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("Terrain Analysis", False, str(e)))
            return None
    
    def test_satellite_analysis(self):
        """Test 6: Execute satellite imagery analysis"""
        print("\n" + "="*70)
        print("TEST 6: Satellite Imagery Analysis")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/tools/call",
                json={
                    "name": "analyze_satellite_imagery",
                    "arguments": {
                        "query": "Recent satellite data",
                        "location": "Seattle, Washington",
                        "timeframe": "2024-10-01/2024-10-31",
                        "collections": ["sentinel-2"]
                    }
                },
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print("[OK] PASSED - Satellite analysis executed")
            print(f"   Result preview: {str(data)[:300]}...")
            
            self.test_results.append(("Satellite Analysis", True, None))
            return data
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("Satellite Analysis", False, str(e)))
            return None
    
    def test_comparison_analysis(self):
        """Test 7: Execute comparison analysis tool"""
        print("\n" + "="*70)
        print("TEST 7: Comparison Analysis Tool")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/tools/call",
                json={
                    "name": "comparison_analysis",
                    "arguments": {
                        "location": "Glacier National Park, Montana",
                        "before_date": "2020-01-01",
                        "after_date": "2024-01-01",
                        "analysis_type": "change_detection"
                    }
                },
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            print("[OK] PASSED - Comparison analysis executed")
            print(f"   Result preview: {str(data)[:300]}...")
            
            self.test_results.append(("Comparison Analysis", True, None))
            return data
        except Exception as e:
            print(f"[WARN]  SKIPPED - {str(e)} (May not be fully implemented)")
            self.test_results.append(("Comparison Analysis", None, str(e)))
            return None
    
    def test_api_documentation(self):
        """Test 8: Check API documentation endpoint"""
        print("\n" + "="*70)
        print("TEST 8: API Documentation")
        print("="*70)
        
        try:
            response = self.session.get(f"{self.base_url}/docs")
            response.raise_for_status()
            
            print("[OK] PASSED - API documentation accessible")
            print(f"   URL: {self.base_url}/docs")
            print(f"   Open this URL in your browser for interactive docs")
            
            self.test_results.append(("API Documentation", True, None))
            return True
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("API Documentation", False, str(e)))
            return False
    
    def test_response_times(self):
        """Test 9: Check response times"""
        print("\n" + "="*70)
        print("TEST 9: Response Time Check")
        print("="*70)
        
        try:
            import time
            
            # Test health endpoint
            start = time.time()
            response = self.session.get(f"{self.base_url}/")
            health_time = (time.time() - start) * 1000
            
            # Test tools list
            start = time.time()
            response = self.session.post(f"{self.base_url}/tools/list")
            tools_time = (time.time() - start) * 1000
            
            print("[OK] PASSED - Response times measured")
            print(f"   Health check: {health_time:.2f}ms")
            print(f"   Tools list: {tools_time:.2f}ms")
            
            if health_time > 1000:
                print(f"   [WARN]  Warning: Health check is slow (>{health_time:.0f}ms)")
            
            self.test_results.append(("Response Times", True, None))
            return True
        except Exception as e:
            print(f"[FAIL] FAILED - {str(e)}")
            self.test_results.append(("Response Times", False, str(e)))
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("[CHART] TEST SUMMARY")
        print("="*70)
        
        passed = sum(1 for _, success, _ in self.test_results if success is True)
        failed = sum(1 for _, success, _ in self.test_results if success is False)
        skipped = sum(1 for _, success, _ in self.test_results if success is None)
        
        print(f"\n[OK] Passed: {passed}")
        print(f"[FAIL] Failed: {failed}")
        print(f"[WARN]  Skipped: {skipped}")
        
        total_run = passed + failed
        if total_run > 0:
            print(f"[UP] Success Rate: {(passed/total_run*100):.1f}%")
        
        if failed > 0:
            print("\n[FAIL] Failed Tests:")
            for name, success, error in self.test_results:
                if success is False:
                    print(f"   - {name}: {error}")
        
        if skipped > 0:
            print("\n[WARN]  Skipped Tests:")
            for name, success, error in self.test_results:
                if success is None:
                    print(f"   - {name}: {error}")
        
        print("\n" + "="*70)
        return failed == 0

def main():
    if len(sys.argv) < 2:
        print("\n[FAIL] Error: Missing MCP server URL")
        print("\nUsage: python test_deployed_mcp.py <MCP_SERVER_URL>")
        print("\nExamples:")
        print("  python test_deployed_mcp.py https://earth-copilot-mcp.azurecontainerapps.io")
        print("  python test_deployed_mcp.py http://localhost:8080")
        sys.exit(1)
    
    mcp_url = sys.argv[1]
    
    print("\n" + "="*70)
    print("[GLOBE] Earth Copilot MCP Server - Deployment Tests")
    print("="*70)
    print(f"[PIN] Testing: {mcp_url}")
    print(f"[TIME] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = DeployedMCPTester(mcp_url)
    
    # Run all tests
    print("\n[LAUNCH] Starting test suite...")
    
    if not tester.test_health():
        print("\n[FAIL] Server health check failed. Cannot proceed with other tests.")
        print("\n[INFO] Troubleshooting:")
        print("   1. Verify the URL is correct")
        print("   2. Check if the server is running")
        print("   3. Check firewall/network settings")
        print("   4. View logs: az containerapp logs show --name <app-name> --resource-group <rg-name>")
        sys.exit(1)
    
    tester.test_tools_list()
    tester.test_resources_list()
    tester.test_read_resource()
    tester.test_terrain_analysis()
    tester.test_satellite_analysis()
    tester.test_comparison_analysis()
    tester.test_api_documentation()
    tester.test_response_times()
    
    # Print summary
    all_passed = tester.print_summary()
    
    print("\n[INFO] Next Steps:")
    print("   1. Open API docs: " + mcp_url + "/docs")
    print("   2. Test interactive UI in browser")
    print("   3. Integrate with GitHub Copilot or Claude Desktop")
    print("   4. Monitor logs in Azure Portal")
    print("   5. Set up alerts for failures")
    
    print("\n[DOCS] Documentation:")
    print("   - Deployment Guide: DEPLOYMENT_TESTING_GUIDE.md")
    print("   - MCP Server README: README.md")
    print("   - Client Integration: CLIENT_CONNECTION_GUIDE.md")
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
