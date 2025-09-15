import asyncio
import sys
sys.path.append('earth-copilot/router-function-app')
from semantic_translator import SemanticQueryTranslator
import os
import json

async def test_semantic_translator():
    # Initialize the translator (same as in function_app.py)
    translator = SemanticQueryTranslator(
        azure_openai_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT'),
        azure_openai_api_key=os.environ.get('AZURE_OPENAI_API_KEY'),
        model_name=os.environ.get('AZURE_OPENAI_MODEL_NAME', 'gpt-5')
    )
    
    # Test the translation
    query = 'show me satellite map of seattle'
    print(f'Testing query: {query}')
    result = await translator.translate_query(query)
    
    print('Semantic Translation Result:')
    print(json.dumps(result, indent=2))
    
    # Show specific components
    print('\n--- Key Components ---')
    print(f'Collections: {result.get("collections", [])}')
    print(f'BBox: {result.get("bbox")}')
    print(f'DateTime: {result.get("datetime")}')
    print(f'Query Filters: {result.get("query")}')

if __name__ == "__main__":
    asyncio.run(test_semantic_translator())
