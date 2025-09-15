"""
Test script to verify RouterAgent temporal entity extraction works
"""

import sys
import os
import asyncio

# Add the router function app directory to path to access router_logic module
router_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'earth_copilot', 'router_function_app')
sys.path.append(router_path)

try:
    print("Testing RouterAgent import...")
    from router_logic import RouterAgent
    print("✅ RouterAgent imported successfully!")
    
    # Test initialization
    print("Testing RouterAgent initialization...")
    router_agent = RouterAgent()
    print("✅ RouterAgent initialized successfully!")
    
    # Test entity extraction with "recent"
    print("Testing entity extraction with 'recent'...")
    
    async def test_entity_extraction():
        query = "Show me recent satellite imagery of California wildfires"
        entities = await router_agent._extract_entities(query)
        print(f"✅ Entity extraction result: {entities}")
        
        # Check if timeframe was converted properly
        if "timeframe" in entities and "/" in entities["timeframe"]:
            print(f"🎉 Success! 'recent' was converted to ISO8601 interval: {entities['timeframe']}")
        else:
            print(f"⚠️  Warning: timeframe not converted properly: {entities.get('timeframe')}")
        
        return entities
    
    # Run the test
    result = asyncio.run(test_entity_extraction())
    print("🎉 All tests completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
