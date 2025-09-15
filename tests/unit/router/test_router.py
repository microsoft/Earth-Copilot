# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Test script for Router Function App
Tests the router logic without Azure Functions runtime
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Add the router function app directory to path for imports
router_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'earth_copilot', 'router_function_app')
sys.path.insert(0, router_path)

from router_logic import RouterAgent

async def test_router_queries():
    """Test various queries through the router agent"""
    
    router = RouterAgent()
    
    test_queries = [
        {
            "query": "Show me Landsat 8 imagery over Seattle",
            "expected_intent": "map_visualization",
            "expected_domain": "general",
            "expected_needs_map": True
        },
        {
            "query": "Find wildfire data in California from 2023",
            "expected_intent": "data_search", 
            "expected_domain": "wildfire",
            "expected_needs_map": False
        },
        {
            "query": "Analyze vegetation trends in the Amazon over the last 5 years",
            "expected_intent": "analysis",
            "expected_domain": "vegetation", 
            "expected_needs_map": False
        },
        {
            "query": "What is NDVI and how is it calculated?",
            "expected_intent": "information",
            "expected_domain": "vegetation",
            "expected_needs_map": False
        },
        {
            "query": "Display flood extent mapping for Houston during Hurricane Harvey",
            "expected_intent": "map_visualization",
            "expected_domain": "flooding",
            "expected_needs_map": True
        }
    ]
    
    print("🚀 Testing Earth Copilot Router Function App")
    print("=" * 60)
    
    for i, test_case in enumerate(test_queries, 1):
        print(f"\n📋 Test {i}: {test_case['query']}")
        print("-" * 50)
        
        # Prepare input data
        input_data = {
            "user_query": test_case["query"],
            "chat_history": [],
            "session_context": {}
        }
        
        try:
            # Process through router
            result = await router.process(input_data)
            
            # Display results
            print(f"✅ Intent: {result['intent']}")
            print(f"✅ Domain: {result['domain']}")
            print(f"✅ Needs Map: {result['needs_map']}")
            print(f"✅ Needs Time Range: {result['needs_time_range']}")
            print(f"✅ Confidence: {result['confidence']}")
            print(f"✅ Routing Decision: {result['routing_decision']}")
            print(f"✅ Extracted Entities: {result['extracted_entities']}")
            print(f"✅ Guardrails: {result['guardrails_check']}")
            print(f"✅ Status: {result['status']}")
            
            # Validate against expectations
            assertions = []
            if result['intent'] == test_case['expected_intent']:
                assertions.append("✅ Intent matches expected")
            else:
                assertions.append(f"❌ Intent mismatch: got {result['intent']}, expected {test_case['expected_intent']}")
            
            if result['domain'] == test_case['expected_domain']:
                assertions.append("✅ Domain matches expected")
            else:
                assertions.append(f"❌ Domain mismatch: got {result['domain']}, expected {test_case['expected_domain']}")
                
            if result['needs_map'] == test_case['expected_needs_map']:
                assertions.append("✅ Needs map matches expected")
            else:
                assertions.append(f"❌ Needs map mismatch: got {result['needs_map']}, expected {test_case['expected_needs_map']}")
            
            print("\n🔍 Validation:")
            for assertion in assertions:
                print(f"  {assertion}")
            
        except Exception as e:
            print(f"❌ Error processing query: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Router Function App Test Complete!")

async def test_function_app_simulation():
    """Simulate the Azure Function App HTTP interface"""
    
    print("\n🌐 Testing Function App HTTP Interface Simulation")
    print("=" * 60)
    
    router = RouterAgent()
    
    # Simulate HTTP request body
    request_body = {
        "query": "Show me Landsat 8 imagery over Seattle",
        "chat_history": [
            "Hello, I'm looking for satellite data",
            "I need data for the Pacific Northwest"
        ],
        "session_context": {
            "user_id": "test_user_123",
            "session_id": "session_456"
        }
    }
    
    print(f"📡 Simulating HTTP POST to /api/chat")
    print(f"📋 Request Body: {json.dumps(request_body, indent=2)}")
    
    try:
        # Process the request (simulating function_app.py logic)
        input_data = {
            "user_query": request_body["query"],
            "chat_history": request_body.get("chat_history", []),
            "session_context": request_body.get("session_context", {})
        }
        
        # Get routing decision
        routing_result = await router.process(input_data)
        
        # Add Function App metadata (simulating function_app.py)
        routing_result["timestamp"] = datetime.utcnow().isoformat() + "Z"
        routing_result["function_version"] = "1.0.0"
        
        # Simulate HTTP response
        response = {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": routing_result
        }
        
        print(f"\n📤 HTTP Response:")
        print(f"Status: {response['status_code']}")
        print(f"Body: {json.dumps(response['body'], indent=2)}")
        
        print("\n✅ Function App simulation successful!")
        
    except Exception as e:
        print(f"❌ Function App simulation error: {e}")

if __name__ == "__main__":
    asyncio.run(test_router_queries())
    asyncio.run(test_function_app_simulation())
