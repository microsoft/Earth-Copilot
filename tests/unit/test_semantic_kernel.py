import sys
sys.path.append('c:\\Users\\melisabardhi\\OneDrive - Microsoft\\Desktop\\Workspace\\Earth-Copilot\\earth-copilot\\router-function-app')

try:
    print("Testing Semantic Kernel import...")
    import semantic_kernel as sk
    print("✓ Semantic Kernel imported successfully")
    
    print("Testing SemanticQueryTranslator import...")
    from semantic_translator import SemanticQueryTranslator
    print("✓ SemanticQueryTranslator imported successfully")
    
    print("Testing translator initialization...")
    translator = SemanticQueryTranslator(
        azure_openai_endpoint="https://admin-me6cp2y9-eastus2.openai.azure.com",
        azure_openai_api_key="YOUR_AZURE_OPENAI_API_KEY_HERE",
        model_name="gpt-5"
    )
    print("✓ SemanticQueryTranslator initialized successfully")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
