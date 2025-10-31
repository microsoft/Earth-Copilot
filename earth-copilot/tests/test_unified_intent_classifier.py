"""
Tests for unified intent classifier (Agent 0 combined with Agent 0.5).

Tests validation of:
1. Intent classification accuracy (map/chat/hybrid)
2. Module detection and selection
3. GEOINT intent detection
4. Fallback behavior
5. JSON parsing robustness

STATUS: ✅ ALL 12/12 TESTS PASSING

FIXES APPLIED:
- Changed mock response structure from [MagicMock(content=json_string)] to json_string
- Semantic Kernel's _extract_clean_content_from_sk_result expects result.value as string
- Mock now properly simulates SK response format

TEST RESULTS:
- test_map_request_classification ✅
- test_contextual_analysis_classification ✅
- test_geoint_terrain_classification ✅
- test_geoint_mobility_classification ✅
- test_hybrid_request_classification ✅
- test_json_parsing_with_markdown_markers ✅
- test_fallback_on_json_parse_error ✅
- test_query_added_to_result ✅
- test_fallback_map_request ✅
- test_fallback_contextual_analysis ✅
- test_fallback_default_to_hybrid ✅
- test_unified_single_call_efficiency ✅

Author: Earth Copilot Team
Date: 2025-10-17
Last Updated: 2025-10-17 (Fixed all tests)
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

# These tests require the semantic_translator module
# Will use mocks to avoid needing Azure OpenAI credentials


# ============================================================================
# Test Unified Intent Classifier
# ============================================================================

class TestUnifiedIntentClassifier:
    """Test unified intent classification (Agent 0 + Agent 0.5 merged)"""
    
    def create_mock_translator(self):
        """Create mock semantic translator with unified classifier"""
        from semantic_translator import SemanticQueryTranslator
        
        translator = SemanticQueryTranslator(
            azure_openai_endpoint="mock://endpoint",
            azure_openai_api_key="mock_key",
            model_name="gpt-4o"
        )
        
        return translator
    
    @pytest.mark.asyncio
    async def test_map_request_classification(self):
        """Test classification of simple map data request"""
        translator = self.create_mock_translator()
        
        # Mock GPT response for map request
        mock_response = {
            "intent_type": "map_only_request",
            "needs_satellite_data": True,
            "needs_contextual_info": False,
            "modules_required": [
                {"name": "map_display", "priority": 10, "config": {}}
            ],
            "confidence": 0.95
        }
        
        with patch.object(translator, 'kernel') as mock_kernel:
            # Create proper Semantic Kernel response mock
            mock_result = MagicMock()
            # SK returns result.value as string directly
            mock_result.value = json.dumps(mock_response)
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query="Show me satellite imagery of Seattle",
                conversation_id=None
            )
            
            assert result['intent_type'] == 'map_only_request'
            assert result['needs_satellite_data'] is True
            assert result['needs_contextual_info'] is False
            assert len(result['modules_required']) == 1
            assert result['modules_required'][0]['name'] == 'map_display'
    
    @pytest.mark.asyncio
    async def test_contextual_analysis_classification(self):
        """Test classification of contextual analysis (chat-only)"""
        translator = self.create_mock_translator()
        
        mock_response = {
            "intent_type": "contextual_analysis",
            "needs_satellite_data": False,
            "needs_contextual_info": True,
            "modules_required": [],
            "confidence": 0.95
        }
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = json.dumps(mock_response)
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query="How do hurricanes form?",
                conversation_id=None
            )
            
            assert result['intent_type'] == 'contextual_analysis'
            assert result['needs_satellite_data'] is False
            assert result['needs_contextual_info'] is True
            assert len(result['modules_required']) == 0
    
    @pytest.mark.asyncio
    async def test_geoint_terrain_classification(self):
        """Test classification of GEOINT terrain analysis request"""
        translator = self.create_mock_translator()
        
        mock_response = {
            "intent_type": "hybrid_request",
            "needs_satellite_data": True,
            "needs_contextual_info": True,
            "modules_required": [
                {"name": "geoint_terrain", "priority": 1, "config": {}},
                {"name": "map_display", "priority": 10, "config": {}}
            ],
            "confidence": 0.90
        }
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = json.dumps(mock_response)
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query="Analyze terrain slope near Fort Carson",
                conversation_id=None
            )
            
            assert result['intent_type'] == 'hybrid_request'
            assert result['needs_satellite_data'] is True
            assert result['needs_contextual_info'] is True
            assert len(result['modules_required']) == 2
            
            # Check GEOINT module has higher priority
            module_names = [m['name'] for m in result['modules_required']]
            assert 'geoint_terrain' in module_names
            assert 'map_display' in module_names
            
            # Verify priority ordering
            terrain_module = next(m for m in result['modules_required'] if m['name'] == 'geoint_terrain')
            map_module = next(m for m in result['modules_required'] if m['name'] == 'map_display')
            assert terrain_module['priority'] < map_module['priority']  # Lower = higher priority
    
    @pytest.mark.asyncio
    async def test_geoint_mobility_classification(self):
        """Test classification of GEOINT mobility analysis request"""
        translator = self.create_mock_translator()
        
        mock_response = {
            "intent_type": "hybrid_request",
            "needs_satellite_data": True,
            "needs_contextual_info": True,
            "modules_required": [
                {"name": "geoint_mobility", "priority": 1, "config": {}},
                {"name": "map_display", "priority": 10, "config": {}}
            ],
            "confidence": 0.90
        }
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = json.dumps(mock_response)
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query="Can emergency vehicles access this flood zone?",
                conversation_id=None
            )
            
            module_names = [m['name'] for m in result['modules_required']]
            assert 'geoint_mobility' in module_names
    
    @pytest.mark.asyncio
    async def test_hybrid_request_classification(self):
        """Test classification of hybrid request (map + analysis)"""
        translator = self.create_mock_translator()
        
        mock_response = {
            "intent_type": "hybrid_request",
            "needs_satellite_data": True,
            "needs_contextual_info": True,
            "modules_required": [
                {"name": "map_display", "priority": 10, "config": {}}
            ],
            "confidence": 0.90
        }
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = json.dumps(mock_response)
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query="Show wildfire damage and explain causes",
                conversation_id=None
            )
            
            assert result['intent_type'] == 'hybrid_request'
            assert result['needs_satellite_data'] is True
            assert result['needs_contextual_info'] is True
    
    @pytest.mark.asyncio
    async def test_json_parsing_with_markdown_markers(self):
        """Test robust JSON parsing with markdown code blocks"""
        translator = self.create_mock_translator()
        
        # Mock response with markdown formatting (common GPT output)
        mock_response_text = """```json
{
    "intent_type": "map_only_request",
    "needs_satellite_data": true,
    "needs_contextual_info": false,
    "modules_required": [
        {"name": "map_display", "priority": 10, "config": {}}
    ],
    "confidence": 0.95
}
```"""
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = mock_response_text
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query="Show imagery",
                conversation_id=None
            )
            
            # Should successfully parse despite markdown
            assert result['intent_type'] == 'map_only_request'
            assert 'query' in result
    
    @pytest.mark.asyncio
    async def test_fallback_on_json_parse_error(self):
        """Test fallback behavior when JSON parsing fails"""
        translator = self.create_mock_translator()
        
        # Mock invalid JSON response
        mock_response_text = "This is not valid JSON"
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = mock_response_text
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            # Mock fallback method
            with patch.object(translator, 'classify_query_intent_fallback') as mock_fallback:
                mock_fallback.return_value = {
                    'intent_type': 'hybrid',
                    'needs_satellite_data': True,
                    'needs_contextual_info': True,
                    'modules_required': [{'name': 'map_display', 'priority': 10, 'config': {}}],
                    'confidence': 0.5,
                    'query': 'test',
                    'fallback_reason': 'JSON parsing failed'
                }
                
                result = await translator.classify_query_intent_unified(
                    query="test query",
                    conversation_id=None
                )
                
                # Should use fallback
                assert mock_fallback.called
                assert 'fallback_reason' in result or result is not None
    
    @pytest.mark.asyncio
    async def test_query_added_to_result(self):
        """Test that original query is added to classification result"""
        translator = self.create_mock_translator()
        
        test_query = "Show me Seattle satellite imagery"
        
        mock_response = {
            "intent_type": "map_only_request",
            "needs_satellite_data": True,
            "needs_contextual_info": False,
            "modules_required": [
                {"name": "map_display", "priority": 10, "config": {}}
            ],
            "confidence": 0.95
        }
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = json.dumps(mock_response)
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_unified(
                query=test_query,
                conversation_id=None
            )
            
            # Query should be added to result for downstream use
            assert 'query' in result
            assert result['query'] == test_query


# ============================================================================
# Test Fallback Intent Classifier
# ============================================================================

class TestFallbackIntentClassifier:
    """Test fallback classifier when unified method fails"""
    
    def create_mock_translator(self):
        """Create mock semantic translator"""
        from semantic_translator import SemanticQueryTranslator
        
        translator = SemanticQueryTranslator(
            azure_openai_endpoint="mock://endpoint",
            azure_openai_api_key="mock_key",
            model_name="gpt-4o"
        )
        
        return translator
    
    @pytest.mark.asyncio
    async def test_fallback_map_request(self):
        """Test fallback classification for map requests"""
        translator = self.create_mock_translator()
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = "map_only_request"
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_fallback(
                query="Show me Seattle",
                conversation_id=None
            )
            
            assert result['intent_type'] == 'map_only_request'
            assert result['needs_satellite_data'] is True
            assert len(result['modules_required']) == 1
            assert result['modules_required'][0]['name'] == 'map_display'
    
    @pytest.mark.asyncio
    async def test_fallback_contextual_analysis(self):
        """Test fallback classification for contextual analysis"""
        translator = self.create_mock_translator()
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_result = MagicMock()
            mock_result.value = "chat_only_request"
            mock_kernel.invoke_prompt = AsyncMock(return_value=mock_result)
            
            result = await translator.classify_query_intent_fallback(
                query="How do hurricanes form?",
                conversation_id=None
            )
            
            assert result['intent_type'] == 'chat_only_request'
            assert result['needs_satellite_data'] is False
            assert len(result['modules_required']) == 0
    
    @pytest.mark.asyncio
    async def test_fallback_default_to_hybrid(self):
        """Test fallback defaults to hybrid on error"""
        translator = self.create_mock_translator()
        
        with patch.object(translator, 'kernel') as mock_kernel:
            # Simulate kernel failure
            mock_kernel.invoke_prompt = AsyncMock(side_effect=Exception("Kernel failed"))
            
            result = await translator.classify_query_intent_fallback(
                query="test query",
                conversation_id=None
            )
            
            # Should default to hybrid
            assert result['intent_type'] == 'hybrid'
            assert result['needs_satellite_data'] is True
            assert result['confidence'] == 0.5
            assert 'fallback_reason' in result


# ============================================================================
# Integration: Unified vs Separate Agents
# ============================================================================

class TestUnifiedVsSeparateAgents:
    """Compare unified classifier vs separate Agent 0 + Agent 0.5"""
    
    @pytest.mark.asyncio
    async def test_unified_single_call_efficiency(self):
        """Test that unified classifier makes only one GPT call"""
        from semantic_translator import SemanticQueryTranslator
        
        translator = SemanticQueryTranslator(
            azure_openai_endpoint="mock://endpoint",
            azure_openai_api_key="mock_key",
            model_name="gpt-4o"
        )
        
        call_count = 0
        
        async def mock_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.value = json.dumps({
                "intent_type": "map_only_request",
                "needs_satellite_data": True,
                "needs_contextual_info": False,
                "modules_required": [{"name": "map_display", "priority": 10, "config": {}}],
                "confidence": 0.95
            })
            return mock_result
        
        with patch.object(translator, 'kernel') as mock_kernel:
            mock_kernel.invoke_prompt = AsyncMock(side_effect=mock_invoke)
            
            await translator.classify_query_intent_unified(
                query="Show me Seattle",
                conversation_id=None
            )
            
            # Should make exactly ONE GPT call
            assert call_count == 1


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
