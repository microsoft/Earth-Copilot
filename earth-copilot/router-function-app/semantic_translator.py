import asyncio
import json
import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import aiohttp
import re
import time
import hashlib

# Import the consolidated location resolver
from location_resolver import EnhancedLocationResolver

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Import dynamic collection profiles for comprehensive coverage
try:
    from collection_profiles import COLLECTION_PROFILES
    PROFILES_AVAILABLE = True
    logger.info("✅ Collection profiles loaded - dynamic mapping enabled")
except ImportError:
    COLLECTION_PROFILES = {}
    PROFILES_AVAILABLE = False
    logger.warning("⚠️ Collection profiles not available - using static mapping")

# Configure enhanced debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('semantic_translator_debug.log', mode='w')
    ]
)

# Semantic Kernel imports with proper error handling
try:
    import semantic_kernel as sk
    from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
    from semantic_kernel.functions import KernelFunction, KernelArguments
    from semantic_kernel.prompt_template import PromptTemplateConfig, InputVariable
    from semantic_kernel.contents.chat_history import ChatHistory
    from semantic_kernel import Kernel
    SK_AVAILABLE = True
    logging.info("✓ Semantic Kernel successfully imported")
except ImportError as e:
    SK_AVAILABLE = False
    logging.warning(f"✗ Semantic Kernel not available: {e}")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class LocationCache:
    """In-memory location cache with TTL for performance optimization"""
    
    def __init__(self, ttl_hours: int = 24, max_entries: int = 500):
        self.cache = {}
        self.ttl_seconds = ttl_hours * 3600
        self.max_entries = max_entries
    
    def _generate_key(self, location_name: str, location_type: str) -> str:
        """Generate cache key for location"""
        key_string = f"{location_name.lower().strip()}:{location_type.lower()}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """Get cached location bbox"""
        key = self._generate_key(location_name, location_type)
        
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                logger.info(f"Cache hit for location: {location_name}")
                return entry["bbox"]
            else:
                del self.cache[key]
        
        return None
    
    def set(self, location_name: str, location_type: str, bbox: List[float]):
        """Cache location bbox"""
        key = self._generate_key(location_name, location_type)
        
        if len(self.cache) >= self.max_entries:
            self._evict_oldest()
        
        self.cache[key] = {
            "bbox": bbox,
            "timestamp": time.time(),
            "location_name": location_name
        }
        logger.info(f"Cached location: {location_name}")
    
    def _evict_oldest(self):
        """Remove oldest cache entry"""
        if self.cache:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]

class SemanticQueryTranslator:
    """Enhanced query translator using Semantic Kernel for intelligent entity extraction and contextual Earth science analysis"""
    
    def __init__(self, azure_openai_endpoint: str, azure_openai_api_key: str, model_name: str):
        if not SK_AVAILABLE:
            raise ImportError("Semantic Kernel is not available")
        
        # Store configuration for lazy initialization
        self.azure_openai_endpoint = azure_openai_endpoint
        self.azure_openai_api_key = azure_openai_api_key
        self.model_name = model_name
        
        # Kernel will be initialized lazily on first use
        self.kernel = None
        self._kernel_initialized = False
        
        # Initialize consolidated location resolver
        self.location_resolver = EnhancedLocationResolver()
        
        # Initialize location cache (kept for compatibility)
        self.location_cache = LocationCache()
        
        logger.info("✓ Using consolidated EnhancedLocationResolver (Azure Maps → Nominatim → Azure OpenAI)")
        
        # Initialize STAC query checker (disabled for streamlined version)
        self.query_checker = None  # Disabled for streamlined version
        
        # Comprehensive collection mappings for ALL use cases (not just disasters)
        self.collection_mappings = {
            # Disaster response collections
            "disaster": {
                "hurricane": {
                    "primary": ["sentinel-1-grd", "sentinel-2-l2a"],
                    "secondary": ["landsat-c2-l2", "naip", "hls-s30"],
                    "thermal": []
                },
                "wildfire": {
                    "primary": ["modis-14A1-061", "modis-14A2-061", "viirs-14A1-001"],  # Validated working collections
                    "secondary": ["modis-64A1-061", "sentinel-2-l2a", "landsat-c2-l2"],  # Burned area + optical
                    "thermal": ["modis-14A1-061", "modis-14A2-061", "viirs-14A1-001"]  # All thermal anomaly collections
                },
                "flood": {
                    "primary": ["sentinel-1-grd"],
                    "secondary": ["sentinel-2-l2a", "hls-s30"],
                    "thermal": []
                },
                "earthquake": {
                    "primary": ["sentinel-1-grd", "cop-dem-glo-30"],
                    "secondary": ["sentinel-2-l2a", "nasadem"],
                    "thermal": []
                }
            },
            
            # Agricultural and vegetation analysis
            "agriculture": {
                "crop_monitoring": ["modis-13q1-061", "hls-l30", "hls-s30", "sentinel-2-l2a"],
                "crop_classification": ["usda-cdl", "sentinel-2-l2a", "landsat-c2-l2"],
                "irrigation": ["sentinel-1-grd", "sentinel-2-l2a"],
                "yield_estimation": ["modis-13q1-061", "landsat-c2-l2"]
            },
            
            # Climate and weather analysis
            "climate": {
                "weather_patterns": ["era5-pds", "era5-land", "daymet-daily-na"],
                "precipitation": ["gpm-imerg-hhr", "era5-pds"],
                "temperature": ["era5-pds", "era5-land", "daymet-daily-na"],
                "thermal_infrared": ["landsat-c2-l2", "modis-14A1-061"],
                "snow_cover": ["modis-10a1-061", "viirs-snow-cover"]
            },
            
            # Environmental monitoring
            "environment": {
                "land_cover": ["esa-worldcover", "io-lulc-annual-v02", "usda-cdl"],
                "deforestation": ["sentinel-2-l2a", "landsat-c2-l2", "modis-13q1-061"],
                "water_quality": ["sentinel-2-l2a", "landsat-c2-l2"],
                "air_quality": ["sentinel-5p-l2", "tropomi-no2"]
            },
            
            # Ocean and marine
            "ocean": {
                "sea_surface_temperature": ["modis-sst"],
                "ocean_color": ["modis-oc"],
                "coastal_monitoring": ["sentinel-2-l2a", "naip", "landsat-c2-l2"]
            },
            
            # Urban and infrastructure
            "urban": {
                "city_development": ["naip", "sentinel-2-l2a", "landsat-c2-l2"],
                "infrastructure": ["sentinel-1-grd", "naip", "sentinel-2-l2a"],
                "population_mapping": ["naip", "sentinel-2-l2a"]
            },
            
            # Terrain and topography
            "terrain": {
                "elevation": ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem"],
                "slope_analysis": ["cop-dem-glo-30", "nasadem"],
                "watershed": ["cop-dem-glo-30", "cop-dem-glo-90"]
            }
        }
        
        # For backwards compatibility, keep disaster_collections as a reference
        self.disaster_collections = self.collection_mappings["disaster"]
        
        logger.info("✓ SemanticQueryTranslator created with comprehensive collection mappings and enhanced Earth science capabilities")
    
    async def classify_query_intent(self, query: str) -> Dict[str, Any]:
        """Classify query to determine if it needs STAC data search or contextual Earth science analysis"""
        
        logger.debug(f"🚀 QUERY CLASSIFICATION: Starting for '{query}'")
        
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            logger.debug("⚠️  Semantic Kernel not available, using fallback classification")
            # Fallback classification without AI
            return self._fallback_query_classification(query)
        
        try:
            # Create classification prompt
            classification_prompt = """
            You are an Earth science query classifier. Analyze the query and determine the appropriate response type.
            
            Return ONLY a valid JSON object with this exact structure:
            {
                "intent_type": "geospatial_data_search|contextual_analysis|hybrid",
                "needs_satellite_data": true/false,
                "needs_contextual_info": true/false,
                "location_focus": "specific_location_name or null",
                "temporal_focus": "specific_time_period or null", 
                "disaster_or_event": "disaster/event_name or null",
                "confidence": 0.0-1.0
            }
            
            Classification Rules:
            - "geospatial_data_search": Simple requests for map visualization, satellite imagery, elevation data, climate data, fire detection, or other geospatial datasets WITHOUT asking for analysis, impacts, or explanations
              Examples: "Show me satellite images of California", "Find elevation data for Colorado", "Display fire detection data for Australia", "Show climate data for Texas", "Get DEM data for the Rocky Mountains", "Show vegetation data"
              Keywords: "show me", "find", "get", "display", "map", "imagery", "elevation", "climate", "fire detection", "vegetation", "landsat", "sentinel", "DEM"
            - "contextual_analysis": Questions asking HOW, WHY, WHAT about impacts, effects, analysis, damage assessment, or general knowledge that doesn't require map visualization
              Examples: "How was NYC impacted by Hurricane Sandy?", "What damage did the earthquake cause?", "Why did the wildfire spread so fast?", "How do hurricanes form?", "What causes earthquakes?"
              Keywords: "how", "why", "what impact", "damage", "effects", "analysis", "assessment", "causes", "forms", "where is the tower in paris"
            - "hybrid": Questions that ask for impacts/analysis AND request geospatial data visualization
              Examples: "Show me Hurricane Sandy damage and explain the impacts", "Display wildfire imagery and analyze the spread"
            
            KEY INDICATORS FOR CONTEXTUAL ANALYSIS:
            - Question words: how, what, why, when, where (in context of impacts/effects/knowledge)
            - Impact/analysis words: impact, effect, damage, affect, consequence, result
            - Assessment words: assessment, analysis, evaluation, study
            - Disaster context: hurricane names, earthquake events, wildfire incidents, flood events
            - Historical events: specific named disasters (Sandy, Katrina, etc.)
            - General knowledge: formation processes, causes, definitions
            
            Query: {{$query}}
            
            Classify this query:
            """
            
            # Create prompt configuration
            prompt_config = PromptTemplateConfig(
                template=classification_prompt,
                name="classify_query",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="query", description="The user's query to classify")
                ]
            )
            
            # Create classification function
            classify_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_config,
                function_name="classify_query",
                plugin_name="semantic_translator"
            )
            
            # Execute classification with timeout
            arguments = KernelArguments(query=query)
            result = await asyncio.wait_for(
                self.kernel.invoke(classify_function, arguments=arguments),
                timeout=15.0
            )
            
            # Parse the JSON response
            content = str(result.value) if hasattr(result, 'value') else str(result)
            content = content.strip()
            
            # Clean up the response to extract JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            classification = json.loads(content)
            
            # Validate required fields
            required_fields = ['intent_type', 'needs_satellite_data', 'needs_contextual_info', 'confidence']
            for field in required_fields:
                if field not in classification:
                    logger.warning(f"Missing field {field} in classification, using fallback")
                    return self._fallback_query_classification(query)
            
            logger.info(f"Query classified as: {classification['intent_type']} (confidence: {classification['confidence']})")
            return classification
            
        except Exception as e:
            logger.error(f"Query classification failed: {e}, using fallback")
            return self._fallback_query_classification(query)
    
    def _fallback_query_classification(self, query: str) -> Dict[str, Any]:
        """Enhanced fallback query classification using comprehensive keyword matching"""
        
        logger.debug(f"🔍 FALLBACK CLASSIFICATION: Starting analysis for query: '{query}'")
        query_lower = query.lower()
        
        # Keywords for different intent types
        geospatial_data_keywords = ['satellite', 'imagery', 'stac', 'landsat', 'sentinel', 'modis', 'show me satellite', 'find satellite', 'download', 'elevation', 'dem', 'climate', 'weather', 'fire detection', 'vegetation']
        contextual_keywords = ['how', 'what', 'why', 'where', 'when', 'impact', 'effect', 'damage', 'affected', 'happened', 'analysis', 'explain', 'assess', 'consequence', 'result', 'causes', 'forms', 'tower in paris']
        location_keywords = ['hurricane', 'earthquake', 'wildfire', 'flood', 'disaster', 'city', 'county', 'state', 'country']
        
        # Specific disaster/event indicators that strongly suggest contextual analysis
        disaster_events = ['sandy', 'katrina', 'harvey', 'irma', 'michael', 'florence', 'dorian', 'ida']
        named_disasters = any(event in query_lower for event in disaster_events)
        
        # Detect matched keywords for debugging
        matched_geospatial = [kw for kw in geospatial_data_keywords if kw in query_lower]
        matched_contextual = [kw for kw in contextual_keywords if kw in query_lower]
        matched_locations = [kw for kw in location_keywords if kw in query_lower]
        
        logger.debug(f"📊 KEYWORD MATCHES:")
        logger.debug(f"   Geospatial keywords: {matched_geospatial}")
        logger.debug(f"   Contextual keywords: {matched_contextual}")
        logger.debug(f"   Location keywords: {matched_locations}")
        logger.debug(f"   Named disasters detected: {named_disasters}")
        
        geospatial_data_score = sum(1 for kw in geospatial_data_keywords if kw in query_lower)
        contextual_score = sum(1 for kw in contextual_keywords if kw in query_lower)
        
        # Boost contextual score for questions that don't need map visualization
        pure_knowledge_patterns = ['how do', 'what causes', 'why do', 'where is the', 'what is the', 'how are', 'what are']
        pure_knowledge_boost = 0
        if any(pattern in query_lower for pattern in pure_knowledge_patterns):
            contextual_score += 3
            pure_knowledge_boost = 3
        
        # Boost contextual score for named disasters/events
        disaster_boost = 0
        if named_disasters:
            contextual_score += 2
            disaster_boost = 2
            
        # Boost contextual score for specific question patterns
        pattern_boost = 0
        if any(pattern in query_lower for pattern in ['how was', 'what was', 'how did', 'what happened']):
            contextual_score += 2
            pattern_boost = 2
        
        logger.debug(f"📈 SCORING CALCULATIONS:")
        logger.debug(f"   Geospatial base score: {geospatial_data_score}")
        logger.debug(f"   Contextual base score: {contextual_score - pure_knowledge_boost - disaster_boost - pattern_boost}")
        logger.debug(f"   Pure knowledge boost: +{pure_knowledge_boost}")
        logger.debug(f"   Named disaster boost: +{disaster_boost}")
        logger.debug(f"   Question pattern boost: +{pattern_boost}")
        logger.debug(f"   FINAL SCORES - Geospatial: {geospatial_data_score}, Contextual: {contextual_score}")
            
        # Determine intent type with enhanced logic
        if contextual_score > geospatial_data_score and contextual_score > 0:
            intent_type = "contextual_analysis"
            needs_satellite_data = any(kw in query_lower for kw in location_keywords)
            needs_contextual_info = True
        elif geospatial_data_score > 0 and contextual_score > 0:
            intent_type = "hybrid"
            needs_satellite_data = True
            needs_contextual_info = True
        else:
            intent_type = "geospatial_data_search"
            needs_satellite_data = True
            needs_contextual_info = False
        
        logger.debug(f"🎯 CLASSIFICATION DECISION:")
        logger.debug(f"   Intent type: {intent_type}")
        logger.debug(f"   Needs satellite data: {needs_satellite_data}")
        logger.debug(f"   Needs contextual info: {needs_contextual_info}")
        
        # Extract location focus
        location_focus = None
        common_locations = ['california', 'texas', 'florida', 'new york', 'nyc', 'houston', 'miami', 'san francisco']
        for loc in common_locations:
            if loc in query_lower:
                location_focus = loc
                break
        
        # Detect disaster events
        disaster_or_event = None
        if named_disasters or any(disaster in query_lower for disaster in ['hurricane', 'earthquake', 'wildfire', 'flood', 'tornado']):
            disaster_or_event = "natural_disaster"
        
        confidence = 0.8 if named_disasters else 0.7
        
        return {
            "intent_type": intent_type,
            "needs_satellite_data": needs_satellite_data,
            "needs_contextual_info": needs_contextual_info,
            "location_focus": location_focus,
            "temporal_focus": None,
            "disaster_or_event": disaster_or_event,
            "confidence": confidence,
            "fallback_reason": f"Used fallback classification: geospatial_keywords={geospatial_data_score}, contextual={contextual_score}"
        }
        
    async def _ensure_kernel_initialized(self):
        """Lazy initialization of the Semantic Kernel with proper error handling"""
        if self._kernel_initialized:
            return
            
        try:
            logger.info("🔄 Initializing Semantic Kernel...")
            self.kernel = sk.Kernel()
            
            # Add Azure OpenAI service with timeout
            self.kernel.add_service(
                AzureChatCompletion(
                    deployment_name=self.model_name,
                    endpoint=self.azure_openai_endpoint,
                    api_key=self.azure_openai_api_key,
                    service_id="azure_openai"
                )
            )
            
            self._kernel_initialized = True
            logger.info("✓ Semantic Kernel initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Semantic Kernel: {e}")
            # Raise error - require proper Azure OpenAI connection
            self.kernel = None
            self._kernel_initialized = False
    
    async def extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract structured entities using proper SK template system with timeout and error handling"""
        
        # Ensure kernel is initialized before use
        await self._ensure_kernel_initialized()
        
        # If kernel initialization failed, raise error for proper Semantic Kernel operation
        if not self._kernel_initialized or self.kernel is None:
            raise Exception("Semantic Kernel initialization failed - cannot process query without proper AI model")
        
        try:
            # Add timeout wrapper for Azure OpenAI calls
            return await asyncio.wait_for(self._extract_entities_internal(query), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error(f"Entity extraction timed out after 30 seconds for query: {query}")
            raise Exception(f"Semantic Kernel timed out processing query: {query}")
        except Exception as e:
            logger.error(f"Entity extraction failed with error: {e}")
            raise Exception(f"Semantic Kernel failed to process query: {query} - {e}")
    
    async def _extract_entities_internal(self, query: str) -> Dict[str, Any]:
        """Extract structured entities using proper SK template system"""
        
        # Improved prompt with better structure and examples
        entity_extraction_prompt = """
        You are an expert at extracting structured information from satellite imagery and disaster response queries.
        
        Extract information from this query and return ONLY a valid JSON object with this exact structure:
        
        {
            "location": {
                "name": "string or null",
                "type": "city|state|country|region",
                "confidence": 0.0
            },
            "temporal": {
                "year": "YYYY or null",
                "month": "MM or null", 
                "season": "spring|summer|fall|winter or null",
                "relative": "recent|current|last_month|last_year or null",
                "confidence": 0.0
            },
            "disaster": {
                "type": "hurricane|wildfire|flood|earthquake|tornado|volcano|drought|storm or null",
                "name": "string or null",
                "confidence": 0.0
            },
            "damage_indicators": {
                "blue_tarp": false,
                "structural_damage": false,
                "flooding": false,
                "fire_damage": false,
                "debris": false,
                "confidence": 0.0
            },
            "analysis_intent": {
                "type": "impact_assessment|damage_analysis|recovery_monitoring|comparison|general_imagery",
                "urgency": "emergency|high|medium|low",
                "confidence": 0.0
            }
        }
        
        IMPORTANT EXTRACTION RULES:
        - For locations: Extract specific place names (California, Houston, Turkey, etc.)
        - For months: Convert month names to numbers (January=01, February=02, March=03, April=04, May=05, June=06, July=07, August=08, September=09, October=10, November=11, December=12)
        - For disasters: Identify specific disaster types from context
        - For temporal relative terms: "last year" → "last_year", "recent" → "recent", "current" → "current", "last month" → "last_month"
        - For seasons: "spring", "summer", "fall"/"autumn", "winter"
        - Use confidence scores between 0.0-1.0 based on clarity
        - Use null for missing information
        
        EXAMPLES:
        Query: "Show me wildfire damage in California from September 2023"
        Response: {"location": {"name": "California", "type": "state", "confidence": 0.9}, "temporal": {"year": "2023", "month": "09", "season": null, "relative": null, "confidence": 0.9}, "disaster": {"type": "wildfire", "name": null, "confidence": 0.9}, "damage_indicators": {"fire_damage": true, "confidence": 0.8}, "analysis_intent": {"type": "damage_analysis", "urgency": "medium", "confidence": 0.8}}
        
        Query: "Hurricane impact assessment for Florida from last year"
        Response: {"location": {"name": "Florida", "type": "state", "confidence": 0.9}, "temporal": {"year": null, "month": null, "season": null, "relative": "last_year", "confidence": 0.9}, "disaster": {"type": "hurricane", "name": null, "confidence": 0.8}, "damage_indicators": {"structural_damage": true, "confidence": 0.7}, "analysis_intent": {"type": "impact_assessment", "urgency": "medium", "confidence": 0.8}}
        
        Query: "Recent earthquake activity in California"
        Response: {"location": {"name": "California", "type": "state", "confidence": 0.9}, "temporal": {"year": null, "month": null, "season": null, "relative": "recent", "confidence": 0.8}, "disaster": {"type": "earthquake", "name": null, "confidence": 0.9}, "damage_indicators": {"structural_damage": true, "confidence": 0.6}, "analysis_intent": {"type": "damage_analysis", "urgency": "medium", "confidence": 0.7}}
        
        Query to analyze: {{$query}}
        
        Return only the JSON object. No explanations or additional text.
        """
        
        try:
            # Create proper template with input variables
            prompt_template_config = PromptTemplateConfig(
                template=entity_extraction_prompt,
                name="extract_entities",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="query", description="The user's natural language query")
                ]
            )
            
            # Create function using proper SK API
            extraction_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_template_config,
                function_name="extract_entities",
                plugin_name="semantic_translator"
            )
            
            # Invoke with proper arguments - try multiple approaches
            try:
                # Try newer SK API
                arguments = KernelArguments(query=query)
                result = await self.kernel.invoke(extraction_function, arguments=arguments)
            except ImportError:
                # Use older SK API if needed
                try:
                    result = await self.kernel.invoke(extraction_function, query=query)
                except:
                    # Last resort - pass as KernelArguments
                    result = await self.kernel.invoke(extraction_function, arguments=KernelArguments(query=query))
            
            # Extract and clean response
            if hasattr(result, 'value'):
                content = str(result.value)
            elif hasattr(result, 'result'):
                content = str(result.result)
            else:
                content = str(result)
            
            # Handle ChatMessageContent properly    
            if 'ChatMessageContent' in content:
                # Extract content from ChatMessageContent
                import re
                content_match = re.search(r"content='([^']+)'", content)
                if content_match:
                    content = content_match.group(1)
                else:
                    # Try different extraction
                    content_match = re.search(r'message=ChatCompletionMessage\(content=\'([^\']*?)\'', content)
                    if content_match:
                        content = content_match.group(1)
            
            logger.info(f"Raw SK response: {repr(content[:500])}")  # Truncate for logging
            
            # Robust JSON extraction
            entities = self._extract_json_safely(content)
            
            # Validate and sanitize extracted entities
            entities = self._validate_entities(entities, query)
            
            logger.info(f"Successfully extracted entities: {entities}")
            return entities
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            # Raise error - we require proper Semantic Kernel processing
            raise Exception(f"Semantic Kernel entity extraction failed: {e}")
    
    def _extract_json_safely(self, content: str) -> Dict[str, Any]:
        """Enhanced JSON extraction with multiple parsing strategies"""
        
        content = content.strip()
        
        # Strategy 1: Direct JSON parsing
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract JSON from markdown code blocks
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    # Clean up the match
                    cleaned = re.sub(r'\\n', '\n', match)
                    cleaned = re.sub(r'\\"', '"', cleaned)
                    return json.loads(cleaned)
                except (json.JSONDecodeError, TypeError):
                    continue
        
        # Strategy 3: Line-by-line JSON reconstruction
        lines = content.split('\n')
        json_lines = []
        in_json = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('{'):
                in_json = True
                json_lines = [line]
            elif in_json:
                json_lines.append(line)
                if line.endswith('}') and len(json_lines) > 1:
                    try:
                        json_content = '\n'.join(json_lines)
                        return json.loads(json_content)
                    except json.JSONDecodeError:
                        continue
        
        # Strategy 4: Extract from ChatMessageContent format
        if 'ChatMessageContent' in content or 'content=' in content:
            content_patterns = [
                r"content=['\"]([^'\"]*)['\"]",
                r"content='([^']*)'",
                r'content="([^"]*)"',
                r"message=ChatCompletionMessage\(content='([^']*)'",
            ]
            
            for pattern in content_patterns:
                match = re.search(pattern, content)
                if match:
                    extracted_content = match.group(1)
                    # Unescape content
                    extracted_content = extracted_content.replace('\\"', '"').replace('\\n', '\n')
                    try:
                        return json.loads(extracted_content)
                    except json.JSONDecodeError:
                        continue
        
        # Strategy 5: Build JSON from extracted components
        logger.warning("All JSON extraction strategies failed, using component extraction")
        return self._extract_components_from_text(content)
    
    def _extract_components_from_text(self, content: str) -> Dict[str, Any]:
        """Extract individual components when JSON parsing fails completely"""
        
        # Use regex to extract key information
        location_match = re.search(r'(?:location|place|area)["\']?\s*:\s*["\']?([^,\n"\']+)', content, re.IGNORECASE)
        disaster_match = re.search(r'(?:disaster|event|type)["\']?\s*:\s*["\']?([^,\n"\']+)', content, re.IGNORECASE)
        year_match = re.search(r'(?:year)["\']?\s*:\s*["\']?(\d{4})', content, re.IGNORECASE)
        month_match = re.search(r'(?:month)["\']?\s*:\s*["\']?(\d{1,2})', content, re.IGNORECASE)
        
        # Build basic structure
        result = {
            "location": {
                "name": location_match.group(1).strip() if location_match else None,
                "type": "region",
                "confidence": 0.6 if location_match else 0.1
            },
            "temporal": {
                "year": year_match.group(1) if year_match else None,
                "month": f"{int(month_match.group(1)):02d}" if month_match else None,
                "season": None,
                "relative": None,
                "confidence": 0.5 if year_match or month_match else 0.1
            },
            "disaster": {
                "type": disaster_match.group(1).strip().lower() if disaster_match else None,
                "name": None,
                "confidence": 0.6 if disaster_match else 0.1
            },
            "damage_indicators": {
                "blue_tarp": False,
                "structural_damage": False,
                "flooding": False,
                "fire_damage": False,
                "debris": False,
                "confidence": 0.1
            },
            "analysis_intent": {
                "type": "general_imagery",
                "urgency": "low", 
                "confidence": 0.1
            }
        }
        
        logger.warning(f"Used component extraction for parsing: {result}")
        return result
        
        # Handle escaped newlines first
        content = content.replace('\\n', '\n').replace('\\"', '"')
        
        # Strategy 1: Direct JSON parsing
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Find JSON block with newlines
        patterns = [
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Better nested JSON handling
            r'```json\s*(\{.*?\})\s*```',  # Markdown JSON block
            r'```\s*(\{.*?\})\s*```'  # Generic code block
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)
            for match in matches:
                try:
                    # Clean the match
                    clean_match = match.strip()
                    return json.loads(clean_match)
                except json.JSONDecodeError:
                    continue
        
        # Strategy 3: Extract using braces (improved for multiline)
        start_idx = content.find('{')
        if start_idx != -1:
            brace_count = 0
            end_idx = -1
            in_string = False
            escape_next = False
            
            for i in range(start_idx, len(content)):
                char = content[i]
                
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
            
            if end_idx != -1:
                try:
                    json_str = content[start_idx:end_idx]
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error: {e}, JSON: {json_str[:200]}")
        
        raise ValueError(f"Could not extract valid JSON from response: {content[:200]}...")
    
    def _validate_entities(self, entities: Dict[str, Any], query: str = "") -> Dict[str, Any]:
        """Validate and sanitize extracted entities"""
        
        # Add the original query for collection selection logic
        entities["original_query"] = query
        
        # Ensure all required top-level keys exist
        required_keys = ["location", "temporal", "disaster", "damage_indicators", "analysis_intent"]
        for key in required_keys:
            if key not in entities:
                entities[key] = {}
        
        # Validate confidence scores
        for section in entities.values():
            if isinstance(section, dict) and "confidence" in section:
                conf = section.get("confidence", 0.0)
                if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                    section["confidence"] = 0.5  # Default confidence
        
        # Validate and enhance temporal information
        temporal = entities.get("temporal", {})
        if temporal.get("year"):
            try:
                year = int(temporal["year"])
                if year < 1900 or year > 2030:
                    temporal["year"] = None
            except (ValueError, TypeError):
                temporal["year"] = None
        
        return entities
    
    async def resolve_location_to_bbox(self, location_name: str, location_type: str = "region") -> Optional[List[float]]:
        """
        🎯 Use consolidated EnhancedLocationResolver
        
        Strategy order (via EnhancedLocationResolver):
        1. Predefined regions (highest accuracy)
        2. Azure Maps API (primary)  
        3. Mapbox (geographic specialist)
        4. Google Maps (comprehensive)
        5. Nominatim (fallback)
        
        Returns: [west, south, east, north] bounding box or None
        """
        logger.info(f"🔍 Resolving location via consolidated resolver: '{location_name}' (type: {location_type})")
        
        if not location_name:
            return None
        
        try:
            # Use the consolidated location resolver
            bbox = await self.location_resolver.resolve_location_to_bbox(location_name, location_type)
            
            if bbox:
                logger.info(f"✅ Consolidated resolver resolved: {location_name} → {bbox}")
                # Cache the result for performance
                self.location_cache.set(location_name, location_type, bbox)
                return bbox
            else:
                logger.warning(f"❌ Consolidated resolver could not resolve: {location_name}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error in consolidated location resolver for {location_name}: {e}")
            return None
    
    async def _resolve_via_nominatim(self, location_name: str) -> Optional[List[float]]:
        """Use Nominatim (OpenStreetMap) API as fallback"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    "q": location_name,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 1
                }
                headers = {"User-Agent": "EarthCopilot/1.0"}
                
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.get(url, params=params, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            result = data[0]
                            lat = float(result["lat"])
                            lon = float(result["lon"])
                            
                            # Convert to bounding box (add small buffer)
                            buffer = 0.1  # degrees
                            bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]
                            
                            logger.info(f"🗺️ Nominatim resolved {location_name}: {bbox}")
                            return bbox
        except Exception as e:
            logger.warning(f"Nominatim failed for {location_name}: {e}")
        return None
    
    async def _resolve_via_azure_maps(self, location_name: str) -> Optional[List[float]]:
        """Use Azure Maps API as fallback"""
        azure_maps_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY")
        if not azure_maps_key:
            logger.info("Azure Maps API key not available, skipping Azure Maps resolution")
            return None
            
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = "https://atlas.microsoft.com/search/address/json"
                params = {
                    "api-version": "1.0",
                    "subscription-key": azure_maps_key,
                    "query": location_name,
                    "limit": 1
                }
                
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.get(url, params=params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]
                            
                            # Azure Maps returns viewport in different format
                            if "viewport" in result:
                                viewport = result["viewport"]
                                bbox = [
                                    viewport["topLeftPoint"]["lon"],
                                    viewport["btmRightPoint"]["lat"],
                                    viewport["btmRightPoint"]["lon"],
                                    viewport["topLeftPoint"]["lat"]
                                ]
                            else:
                                # Fallback to position with buffer
                                position = result["position"]
                                lat, lon = position["lat"], position["lon"]
                                buffer = 0.1
                                bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]
                            
                            logger.info(f"🗺️ Azure Maps resolved {location_name}: {bbox}")
                            return bbox
                    else:
                        logger.warning(f"Azure Maps API error {response.status}: {await response.text()}")
        except Exception as e:
            logger.warning(f"Azure Maps failed for {location_name}: {e}")
        return None
    
    async def _resolve_via_mapbox(self, location_name: str) -> Optional[List[float]]:
        """Use Mapbox Geocoding API as fallback"""
        mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN")
        if not mapbox_token:
            logger.info("Mapbox API token not available, skipping Mapbox resolution")
            return None
            
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{location_name}.json"
                params = {"access_token": mapbox_token, "limit": 1}
                
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.get(url, params=params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("features"):
                            feature = data["features"][0]
                            if "bbox" in feature:
                                bbox = feature["bbox"]
                            else:
                                # Fallback to center coordinates with buffer
                                coords = feature["geometry"]["coordinates"]
                                lon, lat = coords[0], coords[1]
                                buffer = 0.1
                                bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]
                            
                            logger.info(f"🗺️ Mapbox resolved {location_name}: {bbox}")
                            return bbox
        except Exception as e:
            logger.warning(f"Mapbox failed for {location_name}: {e}")
        return None
    
    async def _resolve_via_semantic_kernel(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """Use Azure OpenAI directly for geographic location resolution with enhanced debugging"""
        
        logger.info(f"🔧 SEMANTIC KERNEL DEBUG: Starting location resolution for '{location_name}'")
        
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized:
            logger.error(f"❌ Azure OpenAI not available for location resolution: {location_name}")
            return None
        
        try:
            # 🎯 PURE API-BASED location resolution prompt (NO hardcoded coordinates)
            location_prompt = f"""You are a geographic expert with access to comprehensive global geographic knowledge. 

Analyze the location: {location_name}

Return ONLY valid JSON with precise bounding box coordinates based on your geographic knowledge:

Format: {{"bbox": [west_longitude, south_latitude, east_longitude, north_latitude], "confidence": 0.0_to_1.0}}

Guidelines:
- Use your comprehensive geographic knowledge to determine accurate coordinates
- Return bounding box in [west, south, east, north] format (decimal degrees)
- West/East: longitude values (-180 to +180, negative = west, positive = east)  
- South/North: latitude values (-90 to +90, negative = south, positive = north)
- Confidence: 0.9 for well-known places, 0.7 for regions, 0.5 for less certain locations
- Ensure west < east and south < north
- For cities: tight bounding box around urban area
- For states/provinces: encompass the full administrative boundary
- For countries: include the main territory boundaries

Location to analyze: {location_name}"""

            # Use Azure OpenAI directly with enhanced strategies
            azure_openai_endpoint = self.azure_openai_endpoint
            azure_openai_api_key = self.azure_openai_api_key
            model_name = self.model_name
            
            headers = {
                "Content-Type": "application/json",
                "api-key": azure_openai_api_key
            }
            
            # 🔄 Strategy 1: JSON mode with pure geographic knowledge
            payload_json = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a geographic expert with comprehensive global knowledge. Return ONLY valid JSON with accurate bounding box coordinates for any requested location worldwide."
                    },
                    {
                        "role": "user",
                        "content": f"Provide accurate geographic bounding box coordinates for: {location_name}\n\nFormat: {{\"bbox\": [west_longitude, south_latitude, east_longitude, north_latitude], \"confidence\": confidence_score}}\n\nUse your geographic knowledge to determine precise coordinates."
                    }
                ],
                "max_tokens": 150,
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            
            # 🔄 Strategy 2: Simple structured prompt  
            payload_simple = {
                "messages": [
                    {
                        "role": "user",
                        "content": location_prompt
                    }
                ],
                "max_tokens": 100,
                "temperature": 0.0
            }
            
            strategies = [
                ("JSON Mode", payload_json),
                ("Simple Prompt", payload_simple)
            ]
            
            async with aiohttp.ClientSession() as session:
                url = f"{azure_openai_endpoint}/openai/deployments/{model_name}/chat/completions?api-version=2024-06-01"
                timeout = aiohttp.ClientTimeout(total=30)
                
                # 🔄 Try multiple strategies in order
                for strategy_name, payload in strategies:
                    try:
                        logger.info(f"🔄 Trying location resolution strategy: {strategy_name} for {location_name}")
                        
                        async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                            logger.info(f"🌐 Azure OpenAI response status: {response.status} for {strategy_name}")
                            
                            if response.status == 200:
                                result = await response.json()
                                
                                # Enhanced response processing
                                if "choices" in result and result["choices"]:
                                    content = result["choices"][0]["message"]["content"]
                                    logger.info(f"🔍 Raw Azure OpenAI content ({strategy_name}): '{content}'")
                                    
                                    # Check if response is empty
                                    if not content or content.strip() == "":
                                        logger.warning(f"⚠️ Empty response from Azure OpenAI for {location_name} with {strategy_name}")
                                        continue  # Try next strategy
                                        
                                    # Enhanced JSON parsing
                                    try:
                                        # Clean up any markdown formatting
                                        cleaned_content = content.strip()
                                        if '```json' in cleaned_content:
                                            cleaned_content = cleaned_content.split('```json')[1].split('```')[0]
                                        elif '```' in cleaned_content:
                                            cleaned_content = cleaned_content.split('```')[1].split('```')[0]
                                        
                                        cleaned_content = cleaned_content.strip()
                                        logger.info(f"🧹 Cleaned content: '{cleaned_content}'")
                                        
                                        if not cleaned_content:
                                            logger.warning(f"⚠️ Content empty after cleaning for {location_name} with {strategy_name}")
                                            continue  # Try next strategy
                                        
                                        location_data = json.loads(cleaned_content)
                                        bbox = location_data.get('bbox')
                                        confidence = location_data.get('confidence', 0.0)
                                        
                                        logger.info(f"🔍 Parsed JSON - bbox: {bbox}, confidence: {confidence}")
                                        
                                        if bbox and len(bbox) == 4 and confidence > 0.5:
                                            west, south, east, north = bbox
                                            
                                            # Validate coordinates
                                            if (-180 <= west <= 180 and -180 <= east <= 180 and 
                                                -90 <= south <= 90 and -90 <= north <= 90 and
                                                west < east and south < north):
                                                
                                                logger.info(f"✅ Azure OpenAI successfully resolved {location_name}: {bbox} (confidence: {confidence:.2f}, strategy: {strategy_name})")
                                                return bbox
                                            else:
                                                logger.warning(f"⚠️ Invalid coordinates from Azure OpenAI for {location_name}: {bbox} (strategy: {strategy_name})")
                                        else:
                                            logger.warning(f"⚠️ Low confidence or invalid bbox from Azure OpenAI for {location_name}: {location_data} (strategy: {strategy_name})")
                                            
                                    except json.JSONDecodeError as e:
                                        logger.error(f"❌ Failed to parse Azure OpenAI response for {location_name} with {strategy_name}: '{cleaned_content}'")
                                        logger.error(f"JSON error: {e}")
                                        continue  # Try next strategy
                                else:
                                    logger.warning(f"⚠️ No choices in Azure OpenAI response for {location_name} with {strategy_name}")
                            else:
                                error_text = await response.text()
                                logger.error(f"❌ Azure OpenAI API error {response.status} for {strategy_name}: {error_text}")
                                continue  # Try next strategy
                                
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ Azure OpenAI timeout resolving {location_name} with {strategy_name}")
                        continue  # Try next strategy
                    except Exception as e:
                        logger.error(f"❌ Azure OpenAI error resolving {location_name} with {strategy_name}: {e}")
                        continue  # Try next strategy
                
                # All strategies failed
                logger.error(f"❌ ALL Azure OpenAI strategies failed for {location_name}")
            
        except Exception as e:
            logger.error(f"❌ Critical error in Azure OpenAI resolution for {location_name}: {e}")
        
        return None
    
    # No more predefined regions or Nominatim fallbacks - pure Semantic Kernel approach
    
    def resolve_temporal_to_datetime(self, temporal_info: Dict[str, Any], collections: Optional[List[str]] = None) -> Optional[str]:
        """
        Convert temporal information to ISO8601 datetime range with collection-specific optimization
        
        🎯 COLLECTION-SPECIFIC DATETIME HANDLING based on deep probe findings:
        - Elevation/DEM collections: NO datetime filter (static data)
        - Climate collections: Use historical dates (2020-2023) for optimal coverage
        - Optical collections: Use normal datetime handling
        """
        
        current_date = datetime.now()
        
        # 🏔️ ELEVATION/DEM COLLECTIONS: Return None to skip datetime filter
        elevation_collections = ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "3dep-seamless"]
        if collections and any(col in collections for col in elevation_collections):
            logger.info(f"🏔️ Elevation collection detected - skipping datetime filter for: {collections}")
            return None  # No datetime filter for elevation data
        
        # 🌡️ CLIMATE COLLECTIONS: Use historical dates for optimal coverage
        climate_collections = ["era5-pds", "era5-land", "daymet-daily-na", "gpm-imerg-hhr"]
        if collections and any(col in collections for col in climate_collections):
            logger.info(f"🌡️ Climate collection detected - using historical dates for: {collections}")
            # Use 2020-2023 range for better data availability
            return "2020-01-01T00:00:00Z/2023-12-31T23:59:59Z"
        
        # Handle specific year and month
        year = temporal_info.get("year")
        month = temporal_info.get("month")
        
        if year:
            try:
                year_int = int(year)
                if month:
                    try:
                        month_int = int(month)
                        if 1 <= month_int <= 12:
                            # Specific year and month
                            if month_int == 12:
                                next_month = f"{year_int + 1}-01-01"
                            else:
                                next_month = f"{year_int}-{month_int + 1:02d}-01"
                            return f"{year_int}-{month_int:02d}-01T00:00:00Z/{next_month}T00:00:00Z"
                    except ValueError:
                        pass
                
                # Just year specified
                return f"{year_int}-01-01T00:00:00Z/{year_int}-12-31T23:59:59Z"
            except ValueError:
                pass
        
        # Handle relative dates
        relative = temporal_info.get("relative")
        if relative:
            if relative in ["recent", "current"]:
                start_date = current_date - timedelta(days=30)
                return f"{start_date.isoformat()}Z/{current_date.isoformat()}Z"
            elif relative == "last_month":
                start_date = current_date - timedelta(days=30)
                return f"{start_date.isoformat()}Z/{current_date.isoformat()}Z"
            elif relative == "last_year":
                last_year = current_date.year - 1
                return f"{last_year}-01-01T00:00:00Z/{last_year}-12-31T23:59:59Z"
        
        # Handle seasons (use current year if no year specified)
        season = temporal_info.get("season")
        target_year = int(year) if year else current_date.year
        
        if season:
            season_ranges = {
                "spring": (f"{target_year}-03-01", f"{target_year}-05-31"),
                "summer": (f"{target_year}-06-01", f"{target_year}-08-31"),  
                "fall": (f"{target_year}-09-01", f"{target_year}-11-30"),
                "winter": (f"{target_year}-12-01", f"{target_year + 1}-02-28")
            }
            
            if season in season_ranges:
                start, end = season_ranges[season]
                return f"{start}T00:00:00Z/{end}T23:59:59Z"
        
        # 🆕 ENHANCED: For general queries without specific temporal info, use a broader range
        # Default to recent 2 years to increase data availability
        recent_year = current_date.year - 1  # Use previous year for more complete data
        return f"{recent_year}-01-01T00:00:00Z/{current_date.year}-12-31T23:59:59Z"
    
    def select_collections(self, entities: Dict[str, Any]) -> List[str]:
        """
        🚀 ENHANCED: Dynamic collection selection using collection profiles
        
        This method now dynamically maps queries to collections using:
        1. Collection profiles metadata (if available)
        2. Category-based keyword matching
        3. Fallback to static mappings
        """
        
        collections = []
        query_text = entities.get("original_query", "").lower()
        analysis_intent = entities.get("analysis_intent", {}).get("type", "")
        
        # 🛰️ SATELLITE MAP DETECTION (new logic for optical imagery)
        if any(keyword in query_text for keyword in ["satellite map", "satellite imagery", "optical imagery", "rgb", "true color"]):
            logger.info("🛰️ Detected satellite map query - using optical collections")
            return self._get_dynamic_collections_by_category("optical") or ["sentinel-2-l2a", "landsat-c2-l2", "naip"]
        
        # 🔥 MODIS SPECIFIC: Check for MODIS keywords first (highest priority)
        if "modis" in query_text:
            logger.info(f"🔥 MODIS SPECIFIC DETECTED in query: {query_text}")
            if any(fire_word in query_text for fire_word in ["fire", "thermal", "anomal", "heat", "burn"]):
                logger.info("🔥 MODIS fire/thermal detected - using MODIS fire collections")
                return ["modis-14A1-061", "modis-14A2-061", "modis-64A1-061"]
            elif any(veg_word in query_text for veg_word in ["vegetation", "ndvi", "greenness", "leaf"]):
                logger.info("🌿 MODIS vegetation detected")
                return ["modis-13Q1-061", "modis-13A1-061", "modis-15A2H-061", "modis-17A2H-061"]
            elif any(temp_word in query_text for temp_word in ["temperature", "lst", "surface temperature"]):
                logger.info("🌡️ MODIS land surface temperature detected")
                return ["modis-11A1-061"]
            elif any(snow_word in query_text for snow_word in ["snow", "ice", "snow cover"]):
                logger.info("❄️ MODIS snow/ice detected")
                return ["modis-10A1-061", "modis-10A2-061"]
            elif any(reflectance_word in query_text for reflectance_word in ["reflectance", "surface reflectance", "optical"]):
                logger.info("🌍 MODIS surface reflectance detected")
                return ["modis-09A1-061", "modis-09Q1-061"]
            else:
                logger.info("🔥 General MODIS query - defaulting to fire collections")
                return ["modis-14A1-061", "modis-14A2-061", "modis-64A1-061"]
        
        # 🔥 THERMAL: Check for thermal infrared keywords (Landsat specific)
        if any(thermal_word in query_text for thermal_word in ["thermal", "infrared", "lwir"]) and "landsat" in query_text:
            logger.info(f"🔥 LANDSAT THERMAL INFRARED DETECTED in query: {query_text}")
            return ["landsat-c2-l2"]
        
        # 🏔️ ELEVATION/DEM: Check for elevation keywords (highest priority after thermal)
        elevation_keywords = ["elevation", "dem", "topography", "terrain", "altitude", "height", "slope", "contour"]
        if any(elev_word in query_text for elev_word in elevation_keywords):
            logger.info(f"🏔️ ELEVATION/DEM DETECTED in query: {query_text}")
            return self._get_dynamic_collections_by_category("elevation") or ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem"]
        
        # 🔥 FIRE/WILDFIRE detection (non-MODIS)
        if any(keyword in query_text for keyword in ["fire", "wildfire", "burn"]) and "modis" not in query_text:
            logger.info(f"🔥 General fire detection (non-MODIS): {query_text}")
            return self._get_dynamic_collections_by_category("fire") or ["modis-14A1-061", "modis-14A2-061", "viirs-14A1-001"]
        
        # 🌊 WATER/FLOOD detection  
        if any(keyword in query_text for keyword in ["flood", "water", "inundation", "hurricane"]):
            return self._get_dynamic_collections_by_category("sar") or ["sentinel-1-grd", "sentinel-2-l2a"]
        
        # 🌿 VEGETATION detection
        if any(keyword in query_text for keyword in ["vegetation", "ndvi", "forest", "agriculture", "crop"]):
            return self._get_dynamic_collections_by_category("vegetation") or ["sentinel-2-l2a", "landsat-c2-l2", "modis-13q1-061"]
        
        # 🌡️ CLIMATE/WEATHER detection
        if any(keyword in query_text for keyword in ["climate", "weather", "temperature", "precipitation", "rain"]):
            return self._get_dynamic_collections_by_category("climate") or ["era5-pds", "era5-land", "daymet-daily-na"]
        
        # 🌊 OCEAN detection
        if any(keyword in query_text for keyword in ["ocean", "sea", "marine", "coastal"]):
            return self._get_dynamic_collections_by_category("ocean") or ["modis-oc", "modis-sst", "sentinel-2-l2a"]
        
        # ❄️ SNOW/ICE detection
        if any(keyword in query_text for keyword in ["snow", "ice", "glacier"]):
            return self._get_dynamic_collections_by_category("snow") or ["modis-10a1-061", "viirs-snow-cover"]
        
        # 🌬️ AIR QUALITY detection
        if any(keyword in query_text for keyword in ["air quality", "pollution", "emission", "aerosol"]):
            return self._get_dynamic_collections_by_category("air_quality") or ["sentinel-5p-l2", "tropomi-no2"]
        
        # 🌍 Default for general geographic queries
        logger.info("🌍 Using default optical collections for general query")
        return self._get_dynamic_collections_by_category("optical") or ["sentinel-2-l2a", "landsat-c2-l2"]
    
    def _get_dynamic_collections_by_category(self, category: str) -> Optional[List[str]]:
        """
        🎯 Dynamic collection selection using collection profiles
        
        Args:
            category: Category to search for (optical, sar, elevation, etc.)
            
        Returns:
            List of collection IDs matching the category
        """
        if not PROFILES_AVAILABLE:
            logger.debug(f"Collection profiles not available, using static mapping for {category}")
            return None
        
        matching_collections = []
        
        # Search through collection profiles to find matching categories
        for collection_id, profile in COLLECTION_PROFILES.items():
            profile_category = profile.get("category", "").lower()
            
            # Direct category match
            if profile_category == category.lower():
                matching_collections.append(collection_id)
            
            # Special category mappings
            elif category == "thermal" and "thermal" in profile.get("visualization", {}).get("assets", {}):
                matching_collections.append(collection_id)
            elif category == "elevation" and profile_category in ["dem", "elevation", "topography"]:
                matching_collections.append(collection_id)
            elif category == "fire" and "thermal" in collection_id or "fire" in collection_id:
                matching_collections.append(collection_id)
            elif category == "vegetation" and profile_category in ["vegetation", "ndvi", "land_cover"]:
                matching_collections.append(collection_id)
            elif category == "climate" and profile_category in ["climate", "weather", "meteorological"]:
                matching_collections.append(collection_id)
            elif category == "ocean" and profile_category in ["ocean", "marine", "sea"]:
                matching_collections.append(collection_id)
            elif category == "snow" and profile_category in ["snow", "ice", "cryosphere"]:
                matching_collections.append(collection_id)
            elif category == "air_quality" and profile_category in ["atmospheric", "air_quality", "pollution"]:
                matching_collections.append(collection_id)
        
        if matching_collections:
            logger.info(f"✅ Dynamic mapping found {len(matching_collections)} collections for {category}: {matching_collections[:5]}")
            return matching_collections[:5]  # Limit to top 5 collections
        else:
            logger.debug(f"No dynamic collections found for category: {category}")
            return None
            collections = ["landsat-c2-l2"]  # Only Landsat for thermal infrared
            logger.info(f"🔥 Selected thermal collections: {collections}")
            return collections[:3]  # Early return for thermal infrared
        
        # 🏔️ ELEVATION/DEM: Check for elevation keywords first (highest priority after thermal)
        elevation_keywords = ["elevation", "dem", "topography", "terrain", "altitude", "height", "slope", "contour"]
        if any(elev_word in query_text for elev_word in elevation_keywords):
            logger.info(f"🏔️ ELEVATION/DEM DETECTED in query: {query_text}")
            collections = ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "3dep-seamless"]
            logger.info(f"🏔️ Selected elevation collections: {collections}")
            return collections[:3]  # Early return for elevation data
        
        # Match to comprehensive collection categories and subcategories
        for category, config in self.collection_mappings.items():
            # Check subcategory names as keywords (e.g., "thermal_infrared", "wildfire", etc.)
            for subcategory, subcollections in config.items():
                # Convert subcategory name to searchable keywords
                subcategory_keywords = subcategory.replace("_", " ").split()
                if any(keyword in query_text for keyword in subcategory_keywords):
                    logger.debug(f"Found {category}->{subcategory} match for keywords: {subcategory_keywords}")
                    if isinstance(subcollections, list):
                        collections.extend(subcollections)
                    elif isinstance(subcollections, dict):
                        # Handle nested structure like disaster categories
                        collections.extend(subcollections.get("primary", []))
                        if analysis_intent in ["impact_assessment", "damage_analysis"]:
                            collections.extend(subcollections.get("secondary", []))
                    break
            if collections:  # If we found a match, stop searching
                break
        
        # Handle specific damage indicators and refinements
        damage_indicators = entities.get("damage_indicators", {})
        
        if damage_indicators.get("blue_tarp"):
            # Very high resolution needed - prioritize
            collections = ["naip", "sentinel-2-l2a"] + collections
        
        if damage_indicators.get("flooding"):
            # SAR is critical for flood detection
            if "sentinel-1-grd" not in collections:
                collections.insert(0, "sentinel-1-grd")
        
        if damage_indicators.get("fire_damage"):
            # Thermal detection is key
            thermal_collections = ["modis-14A1-061", "modis-14A2-061", "modis-64A1-061"]
            collections = thermal_collections + collections
        
        # Analysis intent refinements for high-resolution needs
        if analysis_intent in ["impact_assessment", "damage_analysis", "detailed_monitoring"]:
            # Ensure high-resolution optical data is available
            if not any(col in collections for col in ["sentinel-2-l2a", "naip"]):
                collections.insert(0, "sentinel-2-l2a")
        
        # Remove duplicates while preserving priority order
        seen = set()
        unique_collections = []
        for collection in collections:
            if collection not in seen:
                seen.add(collection)
                unique_collections.append(collection)
        
        # Default collections if none selected
        if not unique_collections:
            unique_collections = ["sentinel-2-l2a", "landsat-c2-l2"]
        
        # Limit to reasonable number for performance
        return unique_collections[:3]
    
    def build_stac_query(self, entities: Dict[str, Any], bbox: Optional[List[float]], 
                        datetime_range: Optional[str], collections: List[str]) -> Dict[str, Any]:
        """
        Build comprehensive STAC query with collection-specific optimizations
        
        🎯 COLLECTION-SPECIFIC STAC QUERY BUILDING based on deep probe findings:
        - Elevation/DEM collections: No datetime filter (static data)
        - Climate collections: Specific datetime ranges for optimal coverage
        - Optical collections: Normal datetime + cloud cover filtering
        """
        
        query_filters = {}
        
        # 🏔️ ELEVATION/DEM COLLECTIONS: Special handling for missing fields
        elevation_collections = ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "3dep-seamless"]
        has_elevation = any(col in collections for col in elevation_collections)
        
        # Cloud cover filtering for optical collections (comprehensive list matching our disaster mappings)
        optical_collections = ["sentinel-2-l2a", "landsat-c2-l2", "naip", "hls-l30", "hls-s30"]
        
        # SAR collections don't need cloud filtering (penetrate clouds)
        sar_collections = ["sentinel-1-grd"]
        
        # Thermal/fire collections have different quality metrics
        thermal_collections = ["modis-14A1-061", "modis-14A2-061", "modis-64A1-061"]
        
        # Apply cloud cover filter only to optical collections
        if any(col in collections for col in optical_collections):
            cloud_limit = self._determine_cloud_cover_limit(entities)
            query_filters["eo:cloud_cover"] = {"lt": cloud_limit}
            
        # Add quality filters for thermal collections if present
        if any(col in collections for col in thermal_collections):
            # MODIS fire products have confidence metrics
            query_filters["confidence"] = {"gte": 30}  # Medium to high confidence fire pixels
        
        # Build complete STAC query
        stac_query = {
            "collections": collections,
            "limit": 50,  # Increased limit for better coverage
            "query": query_filters if query_filters else None
        }
        
        # 🎯 CONDITIONAL DATETIME: Only add if not None (elevation collections skip this)
        if datetime_range is not None:
            stac_query["datetime"] = datetime_range
            logger.info(f"🕐 Added datetime filter: {datetime_range}")
        else:
            logger.info(f"🏔️ Skipping datetime filter for elevation collections: {collections}")
        
        # Add spatial filter if available
        if bbox:
            stac_query["bbox"] = bbox
        
        # Add sorting for most recent first (but handle elevation collections without datetime)
        if datetime_range is not None:
            stac_query["sortby"] = [{"field": "datetime", "direction": "desc"}]
        else:
            # For elevation data, sort by spatial relevance or just use default
            stac_query["sortby"] = [{"field": "id", "direction": "asc"}]
        
        logger.info(f"🔧 Final STAC query structure: {stac_query}")
        return stac_query
    
    def _determine_cloud_cover_limit(self, entities: Dict[str, Any]) -> int:
        """Smart cloud cover determination based on analysis needs"""
        
        damage_indicators = entities.get("damage_indicators", {})
        analysis_intent = entities.get("analysis_intent", {})
        query_text = entities.get("original_query", "").lower()
        
        # 🆕 ENHANCED: For general "satellite map" queries, be more permissive
        if "satellite map" in query_text and not any(word in query_text for word in ["disaster", "damage", "fire", "flood", "hurricane"]):
            return 50  # More permissive for general viewing
        
        # Blue tarp detection needs crystal clear imagery  
        if damage_indicators.get("blue_tarp"):
            return 5
        
        # Emergency situations need good visibility
        if analysis_intent.get("urgency") == "emergency":
            return 10
        
        # Default urgency levels for different analysis types
        urgency_map = {
            "emergency": 10,
            "high": 15,  
            "medium": 25,
            "low": 40
        }
        
        urgency = analysis_intent.get("urgency", "medium")
        if urgency in urgency_map:
            logger.debug(f"🎯 DEBUG: Selected cloud cover limit {urgency_map[urgency]} for urgency '{urgency}'")
            return urgency_map[urgency]
        
        # Damage analysis needs clear conditions
        if analysis_intent.get("type") in ["impact_assessment", "damage_analysis"]:
            return 15
        
        # Fire analysis can work with more clouds (uses thermal)
        if damage_indicators.get("fire_damage"):
            return 40
        
        # Default for general analysis
        return 25
    
    async def translate_query(self, natural_query: str) -> Dict[str, Any]:
        """Main translation method with comprehensive error handling"""
        
        # Initialize analysis variable at the start to prevent scope issues
        analysis = {"needs_clarification": False, "quality_score": 0.8}
        
        try:
            # Extract entities using Semantic Kernel
            entities = await self.extract_entities(natural_query)
            
            # Resolve location to bounding box
            bbox = None
            location_info = entities.get("location", {})
            location_name = location_info.get("name")
            
            logger.info(f"Location extracted: {location_name}")
            
            if location_name:
                bbox = await self.resolve_location_to_bbox(
                    location_name, 
                    location_info.get("type", "region")
                )
                logger.info(f"Resolved bbox: {bbox}")
            else:
                logger.warning(f"No location extracted from query: {natural_query}")
                # Without location, bbox will be None - let STAC query handle this
                bbox = None
            
            # Select appropriate collections first (needed for temporal optimization)
            collections = self.select_collections(entities)
            
            # Resolve temporal information with collection-specific optimization
            temporal_info = entities.get("temporal", {})
            datetime_range = self.resolve_temporal_to_datetime(temporal_info, collections)
            
            # Build STAC query
            stac_query = self.build_stac_query(entities, bbox, datetime_range, collections)
            
            # Analyze query completeness and generate clarifications if needed (disabled in streamlined version)
            clarification_questions = []
            if self.query_checker:
                analysis = self.query_checker.analyze_query_completeness(entities, stac_query, natural_query)
                
                # Generate clarification questions if query quality is poor
                if analysis["needs_clarification"]:
                    clarification_questions = self.query_checker.generate_clarification_questions(analysis, natural_query)
            
            # Calculate overall confidence
            confidence_scores = []
            for section in entities.values():
                if isinstance(section, dict) and "confidence" in section:
                    confidence_scores.append(section["confidence"])
            
            overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
            
            # Build result
            result = {
                **stac_query,
                "confidence": overall_confidence,
                "reasoning": self._build_reasoning(entities, location_info),
                "extracted_entities": entities,
                "translation_method": "semantic_kernel",
                "analysis": analysis,
                "clarification_questions": clarification_questions,
                "needs_clarification": analysis["needs_clarification"]
            }
            
            logger.info(f"Translation successful with confidence {overall_confidence:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            
            # Enhanced error response with context preservation
            error_context = {
                "original_query": natural_query,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "attempted_extraction": None,
                "suggestions": []
            }
            
            # Try to provide some extracted information even on failure
            try:
                partial_entities = await self.extract_entities(natural_query)
                error_context["attempted_extraction"] = partial_entities
            except:
                error_context["attempted_extraction"] = "Complete extraction failure"
            
            # Add specific suggestions based on error type
            if "location" in str(e).lower():
                error_context["suggestions"].append("Try specifying a more well-known location (e.g., 'California', 'Houston, Texas')")
            if "timeout" in str(e).lower():
                error_context["suggestions"].append("The service is experiencing delays. Please try again in a moment.")
            if "json" in str(e).lower() or "parse" in str(e).lower():
                error_context["suggestions"].append("There was an issue processing your query. Try rephrasing with simpler terms.")
            
            # Always provide helpful suggestions
            if not error_context["suggestions"]:
                error_context["suggestions"] = [
                    "Try being more specific about the location and time period",
                    "Use common location names (cities, states, countries)",
                    "Specify the type of disaster or analysis you need"
                ]
            
            raise Exception(f"Semantic translation failed with context: {json.dumps(error_context, indent=2)}")
    
    def _build_reasoning(self, entities: Dict[str, Any], location_info: Dict[str, Any]) -> str:
        """Build human-readable reasoning for the translation"""
        
        parts = []
        
        disaster_type = entities.get("disaster", {}).get("type")
        if disaster_type:
            parts.append(f"{disaster_type} analysis")
        
        location_name = location_info.get("name")
        if location_name:
            parts.append(f"for {location_name}")
        
        temporal = entities.get("temporal", {})
        if temporal.get("year"):
            parts.append(f"in {temporal['year']}")
        elif temporal.get("season"):
            parts.append(f"during {temporal['season']}")
        
        if not parts:
            parts.append("general satellite imagery analysis")
        
        return "Semantic Kernel extraction: " + " ".join(parts)
    
    async def generate_intelligent_response(self, natural_query: str, stac_response: Dict[str, Any]) -> Dict[str, Any]:
        """Generate intelligent, data-grounded response using Semantic Kernel LLM analysis"""
        
        # Ensure kernel is initialized before use
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            raise Exception("Semantic Kernel initialization failed - cannot generate response without proper AI model")
        
        try:
            # Extract STAC data for analysis
            results = stac_response.get("results", {})
            features = results.get("features", [])
            collection_summary = results.get("collection_summary", {})
            
            # Prepare comprehensive data summary for LLM analysis
            data_analysis = self._prepare_stac_data_summary(features, collection_summary)
            
            # Create comprehensive prompt for intelligent response generation
            response_prompt = self._create_response_generation_prompt()
            
            # Generate response using Semantic Kernel
            response_content = await self._generate_response_with_sk(
                response_prompt, 
                natural_query, 
                data_analysis
            )
            
            return {
                "message": response_content,
                "has_results": len(features) > 0,
                "query_type": "intelligent_analysis",
                "data_grounded": True,
                "features_analyzed": len(features),
                "collections_used": data_analysis.get("collections", [])
            }
            
        except Exception as e:
            logger.error(f"Intelligent response generation failed: {e}")
            # Fallback to basic response if LLM fails
            feature_count = len(stac_response.get("results", {}).get("features", []))
            return {
                "message": f"Found {feature_count} satellite images for your query. The system encountered an issue generating detailed analysis.",
                "has_results": feature_count > 0,
                "query_type": "basic_fallback",
                "error": str(e)
            }
    
    async def generate_contextual_earth_science_response(self, natural_query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate comprehensive contextual Earth science response with optional satellite data integration"""
        
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            return await self._fallback_contextual_response(natural_query, classification, stac_response)
        
        try:
            # Create contextual analysis prompt
            contextual_prompt = self._create_contextual_analysis_prompt()
            
            # Prepare context data
            context_data = self._prepare_contextual_analysis_data(natural_query, classification, stac_response)
            
            # Generate contextual response
            response_content = await self._generate_contextual_response_with_sk(
                contextual_prompt,
                natural_query,
                context_data
            )
            
            # Determine map data if available
            map_data = None
            if stac_response and stac_response.get("success"):
                features = stac_response.get("results", {}).get("features", [])
                if features:
                    map_data = {
                        "features": features,
                        "bbox": self._extract_bbox_from_features(features),
                        "center": self._calculate_center_from_features(features),
                        "zoom": self._calculate_appropriate_zoom(features)
                    }
            
            return {
                "message": response_content,
                "query_type": "contextual_earth_science",
                "has_satellite_data": stac_response is not None and stac_response.get("success", False),
                "has_contextual_analysis": True,
                "map_data": map_data,
                "location_focus": classification.get("location_focus"),
                "temporal_focus": classification.get("temporal_focus"),
                "disaster_or_event": classification.get("disaster_or_event")
            }
            
        except Exception as e:
            logger.error(f"Contextual Earth science response generation failed: {e}")
            return await self._fallback_contextual_response(natural_query, classification, stac_response)
    
    def _create_contextual_analysis_prompt(self) -> str:
        """Create prompt for comprehensive Earth science contextual analysis"""
        
        return """
        You are an expert Earth scientist, disaster analyst, and environmental consultant with deep knowledge of natural disasters, climate phenomena, and their impacts on human communities and infrastructure. 

        **STRICT FORMATTING REQUIREMENTS:**
        - Write exactly 1-2 paragraphs maximum
        - Use conversational, professional tone
        - NO emojis, symbols, bullet points, or section headings
        - NO lists or technical metadata displays
        - Focus on practical, actionable insights for the user

        When answering about natural disasters, elevation data, climate patterns, or Earth science topics:
        - Provide specific impact details with numbers and dates when available
        - Explain the physical mechanisms and practical implications
        - Connect scientific phenomena to real-world applications
        - Include both immediate findings and broader context

        **USER QUERY:** {{$user_query}}
        **CONTEXT DATA:** {{$context_data}}

        Generate a concise, educational response (1-2 paragraphs only):
        """
    
    def _prepare_contextual_analysis_data(self, query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]]) -> str:
        """Prepare context data for comprehensive Earth science analysis"""
        
        context_parts = []
        
        # Add classification context
        intent_type = classification.get("intent_type", "unknown")
        context_parts.append(f"Query type: {intent_type}")
        
        if classification.get("location_focus"):
            context_parts.append(f"Location focus: {classification['location_focus']}")
        
        if classification.get("temporal_focus"):
            context_parts.append(f"Time period: {classification['temporal_focus']}")
        
        if classification.get("disaster_or_event"):
            context_parts.append(f"Event/Disaster: {classification['disaster_or_event']}")
        
        # Add satellite data context if available
        if stac_response and stac_response.get("success"):
            features = stac_response.get("results", {}).get("features", [])
            if features:
                collections = list(set(f.get("collection", "unknown") for f in features))
                context_parts.append(f"Available satellite data: {len(features)} images from {', '.join(collections)}")
                
                # Add temporal info from satellite data
                dates = [f.get("properties", {}).get("datetime", "") for f in features if f.get("properties", {}).get("datetime")]
                if dates:
                    earliest = min(dates)[:10]
                    latest = max(dates)[:10]
                    if earliest == latest:
                        context_parts.append(f"Satellite data date: {earliest}")
                    else:
                        context_parts.append(f"Satellite data period: {earliest} to {latest}")
        else:
            context_parts.append("No satellite data available for this analysis")
        
        return "; ".join(context_parts)
    
    async def _generate_contextual_response_with_sk(self, prompt_template: str, user_query: str, context_data: str) -> str:
        """Generate contextual response using Semantic Kernel"""
        
        try:
            # Create prompt configuration
            prompt_config = PromptTemplateConfig(
                template=prompt_template,
                name="generate_contextual_response",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="user_query", description="The user's natural language query"),
                    InputVariable(name="context_data", description="Contextual data for Earth science analysis")
                ]
            )
            
            # Create function
            contextual_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_config,
                function_name="generate_contextual_response",
                plugin_name="semantic_translator"
            )
            
            # Execute with timeout
            arguments = KernelArguments(
                user_query=user_query,
                context_data=context_data
            )
            
            result = await asyncio.wait_for(
                self.kernel.invoke(contextual_function, arguments=arguments),
                timeout=25.0
            )
            
            # Extract response content
            response_content = str(result.value) if hasattr(result, 'value') else str(result)
            
            # Clean up response
            response_content = response_content.strip()
            if response_content.startswith('"') and response_content.endswith('"'):
                response_content = response_content[1:-1]
            
            return response_content
            
        except Exception as e:
            logger.error(f"Contextual response generation with SK failed: {e}")
            raise
    
    async def _fallback_contextual_response(self, query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate contextual response using direct Azure OpenAI HTTP call when Semantic Kernel fails"""
        
        try:
            # Use direct HTTP call to Azure OpenAI instead of hardcoded responses
            response_content = await self._direct_llm_call_for_contextual_analysis(query, classification, stac_response)
            
            return {
                "message": response_content,
                "query_type": "direct_llm_contextual",
                "has_satellite_data": stac_response is not None and stac_response.get("success", False),
                "has_contextual_analysis": True,
                "location_focus": classification.get("location_focus"),
                "fallback_used": False,  # Not a fallback anymore, it's a direct LLM call
                "method": "direct_azure_openai_http"
            }
            
        except Exception as e:
            logger.error(f"Direct LLM call failed: {e}")
            # Last resort: minimal response indicating the system should call LLM
            return {
                "message": f"I apologize, but I'm having technical difficulties generating a detailed analysis right now. However, I can see this is a question about {query}. Please try again in a moment as the system should provide a comprehensive, AI-generated response about the impacts and analysis you're asking about.",
                "query_type": "error_fallback", 
                "has_satellite_data": False,
                "has_contextual_analysis": False,
                "error": str(e),
                "fallback_used": True
            }
    
    async def _direct_llm_call_for_contextual_analysis(self, query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]]) -> str:
        """Make direct HTTP call to Azure OpenAI for contextual analysis when Semantic Kernel fails"""
        
        import aiohttp
        import json
        
        # Prepare context data
        context_info = []
        if classification.get("location_focus"):
            context_info.append(f"Location: {classification['location_focus']}")
        if classification.get("disaster_or_event"):
            context_info.append(f"Event type: {classification['disaster_or_event']}")
        if stac_response and stac_response.get("success"):
            features = stac_response.get("results", {}).get("features", [])
            context_info.append(f"Satellite data: {len(features)} images available")
        
        context_text = "; ".join(context_info) if context_info else "General Earth science query"
        
        # Create concise prompt for direct LLM call
        system_prompt = """You are an expert Earth scientist, disaster analyst, and environmental consultant with deep knowledge of natural disasters, climate phenomena, and their impacts. Provide clear, concise responses that are scientifically accurate and accessible.

RESPONSE FORMAT REQUIREMENTS:
- Keep responses to 2-3 paragraphs maximum
- Use clear, conversational language
- Focus on the most important facts and impacts
- Include specific details (numbers, dates) when relevant
- Use emojis sparingly for key points only

When answering about natural disasters:
- Summarize key impacts (casualties, damage, timeline)
- Explain main causes and consequences briefly
- Mention recovery efforts and lessons learned

When discussing satellite data:
- Explain what satellites can observe for the topic
- Connect data capabilities to real-world applications
- Suggest relevant data sources concisely

Keep your response focused, informative, and human-readable."""

        user_prompt = f"Context: {context_text}\n\nUser Question: {query}\n\nProvide a comprehensive, educational response:"
        
        # Prepare the request
        headers = {
            "Content-Type": "application/json",
            "api-key": self.azure_openai_api_key
        }
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 800,  # Reduced to encourage concise responses
            "temperature": 0.7,
            "top_p": 0.9
        }
        
        url = f"{self.azure_openai_endpoint}/openai/deployments/{self.model_name}/chat/completions?api-version=2024-02-01"
        
        # Make the HTTP request
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    error_text = await response.text()
                    raise Exception(f"Azure OpenAI API call failed: {response.status} - {error_text}")
    
    def _extract_bbox_from_features(self, features: List[Dict]) -> Optional[List[float]]:
        """Extract bounding box from STAC features"""
        if not features:
            return None
        
        # Get bbox from first feature or calculate from all features
        if features[0].get("bbox"):
            return features[0]["bbox"]
        
        # Calculate bbox from all feature geometries
        lons, lats = [], []
        for feature in features:
            if feature.get("geometry") and feature["geometry"].get("coordinates"):
                coords = feature["geometry"]["coordinates"]
                if feature["geometry"]["type"] == "Polygon":
                    for coord_pair in coords[0]:
                        lons.append(coord_pair[0])
                        lats.append(coord_pair[1])
        
        if lons and lats:
            return [min(lons), min(lats), max(lons), max(lats)]
        
        return None
    
    def _calculate_center_from_features(self, features: List[Dict]) -> Optional[List[float]]:
        """Calculate center point from STAC features"""
        bbox = self._extract_bbox_from_features(features)
        if bbox and len(bbox) == 4:
            west, south, east, north = bbox
            return [(west + east) / 2, (south + north) / 2]
        return None
    
    def _calculate_appropriate_zoom(self, features: List[Dict]) -> int:
        """Calculate appropriate zoom level based on feature coverage"""
        bbox = self._extract_bbox_from_features(features)
        if not bbox or len(bbox) != 4:
            return 10
        
        west, south, east, north = bbox
        width = abs(east - west)
        height = abs(north - south)
        max_dimension = max(width, height)
        
        # Zoom calculation based on area size
        if max_dimension > 10:
            return 5
        elif max_dimension > 5:
            return 6
        elif max_dimension > 2:
            return 7
        elif max_dimension > 1:
            return 8
        elif max_dimension > 0.5:
            return 9
        elif max_dimension > 0.1:
            return 10
        else:
            return 11
    
    def _prepare_stac_data_summary(self, features: List[Dict], collection_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare comprehensive summary of STAC data for LLM analysis"""
        
        if not features:
            return {
                "has_data": False,
                "total_images": 0,
                "collections": [],
                "temporal_coverage": "No data available",
                "quality_summary": "No images found"
            }
        
        # Basic statistics
        total_images = len(features)
        collections = list(set(f.get("collection", "unknown") for f in features))
        
        # Temporal analysis
        dates = [f.get("properties", {}).get("datetime", "") for f in features if f.get("properties", {}).get("datetime")]
        temporal_coverage = "Unknown"
        if dates:
            earliest = min(dates)[:10] if dates else "Unknown"
            latest = max(dates)[:10] if dates else "Unknown"
            if earliest == latest:
                temporal_coverage = f"Single date: {earliest}"
            else:
                temporal_coverage = f"Date range: {earliest} to {latest}"
        
        # Quality analysis
        cloud_covers = [
            f.get("properties", {}).get("eo:cloud_cover") 
            for f in features 
            if f.get("properties", {}) and f.get("properties", {}).get("eo:cloud_cover") is not None
        ]
        
        quality_summary = "Quality data not available"
        if cloud_covers:
            avg_cloud = sum(cloud_covers) / len(cloud_covers)
            clear_images = len([c for c in cloud_covers if c < 20])
            quality_summary = f"Average cloud cover: {avg_cloud:.1f}%, Clear images (<20% clouds): {clear_images}/{len(cloud_covers)}"
        
        # Platform analysis
        platforms = list(set(
            f.get("properties", {}).get("platform", "unknown") 
            for f in features 
            if f.get("properties", {})
        ))
        
        # Geographic coverage (if bbox available)
        geographic_coverage = "Global coverage possible"
        if features and features[0].get("bbox"):
            bbox = features[0]["bbox"]
            geographic_coverage = f"Bounding box: {bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f}"
        
        return {
            "has_data": True,
            "total_images": total_images,
            "collections": collections,
            "platforms": platforms,
            "temporal_coverage": temporal_coverage,
            "quality_summary": quality_summary,
            "geographic_coverage": geographic_coverage,
            "collection_details": self._get_collection_details(collections),
            "sample_features": features[:3] if features else []  # First 3 for detailed analysis
        }
    
    def _get_collection_details(self, collections: List[str]) -> Dict[str, str]:
        """Get human-readable descriptions of satellite collections"""
        
        collection_descriptions = {
            "sentinel-2-l2a": "Sentinel-2 high-resolution optical imagery (10-60m resolution) - excellent for land cover, vegetation, and detailed surface analysis",
            "sentinel-1-grd": "Sentinel-1 synthetic aperture radar (SAR) data - can penetrate clouds, ideal for flood detection, deformation monitoring",
            "landsat-c2-l2": "Landsat optical and thermal infrared imagery (30m resolution) - long historical archive dating back to 1970s, includes thermal infrared bands for temperature analysis, great for change detection",
            "hls-l30": "Harmonized Landsat Sentinel-2 L30 (30m resolution) - analysis-ready optical data with consistent processing",
            "hls-s30": "Harmonized Landsat Sentinel-2 S30 (30m resolution) - analysis-ready optical data with consistent processing",
            "modis-14A1-061": "MODIS thermal anomalies and fire detection data - daily active fire detection and thermal hotspots",
            "modis-14A2-061": "MODIS thermal anomalies 8-day composite - active fire detection with temporal compositing",
            "modis-64A1-061": "MODIS burned area product - maps areas burned by wildfires with monthly composites",
            "naip": "NAIP very high-resolution aerial imagery (0.6-1m resolution) - US-only coverage, excellent for detailed infrastructure analysis",
            "cop-dem-glo-30": "Copernicus 30m digital elevation model - topographic analysis and terrain modeling",
            "cop-dem-glo-90": "Copernicus 90m digital elevation model - global topographic data for broad terrain analysis",
            "nasadem": "NASA DEM 30m global elevation data - high-quality topographic data for terrain analysis",
            "sentinel-1-rtc": "Sentinel-1 radiometrically terrain corrected SAR - enhanced SAR data for terrain analysis",
            "era5-pds": "ERA5 reanalysis weather data - comprehensive historical and current weather patterns",
            "daymet-daily-na": "Daymet daily weather data North America - high resolution meteorological data",
            "esa-worldcover": "ESA WorldCover global land cover classification - detailed land use and land cover mapping",
            "modis-13q1-061": "MODIS vegetation indices - NDVI and EVI for vegetation monitoring and agricultural analysis"
        }
        
        return {
            collection: collection_descriptions.get(collection, f"{collection} satellite data")
            for collection in collections
        }
    
    def _create_response_generation_prompt(self) -> str:
        """Create concise prompt template for focused response generation"""
        
        return """
        You are an Earth observation specialist. Provide a brief, conversational response (1-2 paragraphs maximum) about the satellite data found.

        Focus on:
        - Direct answer to the user's question
        - Key findings from the satellite data (dates, data quality, coverage)
        - Brief practical insight for their use case

        **STRICT FORMATTING REQUIREMENTS:**
        - Keep responses SHORT and conversational (1-2 paragraphs only)
        - NO bullet points, lists, emojis, symbols, or section headings
        - NO technical metadata details or system information
        - Focus on the main impact/finding for their specific question
        - Mention specific dates and satellite types only if directly relevant

        **USER QUERY:** {{$user_query}}
        **DATA FOUND:** {{$data_summary}}

        Generate a concise, helpful response:
        """
    
    async def _generate_response_with_sk(self, prompt_template: str, user_query: str, data_summary: Dict[str, Any]) -> str:
        """Generate response using Semantic Kernel with the prepared data"""
        
        try:
            # Create prompt template configuration
            prompt_config = PromptTemplateConfig(
                template=prompt_template,
                name="generate_response",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="user_query", description="The user's natural language query"),
                    InputVariable(name="data_summary", description="Comprehensive analysis of the STAC data found")
                ]
            )
            
            # Create function using proper SK API
            response_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_config,
                function_name="generate_response",
                plugin_name="semantic_translator"
            )
            
            # Prepare data summary as formatted text for the LLM
            formatted_data_summary = self._format_data_summary_for_llm(data_summary)
            
            # Invoke with proper arguments
            try:
                # Try newer SK API
                arguments = KernelArguments(
                    user_query=user_query,
                    data_summary=formatted_data_summary
                )
                result = await self.kernel.invoke(response_function, arguments=arguments)
            except ImportError:
                # Use older SK API if needed
                try:
                    result = await self.kernel.invoke(
                        response_function, 
                        user_query=user_query,
                        data_summary=formatted_data_summary
                    )
                except:
                    # Last resort - pass as KernelArguments
                    result = await self.kernel.invoke(response_function, arguments=KernelArguments(
                        user_query=user_query,
                        data_summary=formatted_data_summary
                    ))
            
            # Extract response content properly from Semantic Kernel result
            content = ""
            
            # First try to get the actual text content from the result
            if result and hasattr(result, 'value') and result.value:
                if hasattr(result.value, 'inner_content') and hasattr(result.value.inner_content, 'content'):
                    # ChatMessageContent with inner_content
                    content = result.value.inner_content.content
                elif hasattr(result.value, 'content'):
                    # Direct content attribute
                    content = result.value.content
                elif hasattr(result.value, 'items') and result.value.items:
                    # Items with text content
                    for item in result.value.items:
                        if hasattr(item, 'text'):
                            content = item.text
                            break
                else:
                    # Last resort - convert to string
                    content = str(result.value)
            elif result and hasattr(result, 'value'):
                content = str(result.value) if result.value else ""
            else:
                content = str(result) if result else ""
            
            # Clean up ChatMessageContent string representation if we still have it
            if content and 'ChatMessageContent' in content:
                import re
                # Try to extract from the string representation
                patterns = [
                    r"content=['\"]([^'\"]*)['\"]",
                    r"text=['\"]([^'\"]*)['\"]",
                    r"content='([^']*)'",
                    r'content="([^"]*)"',
                    r"message=ChatCompletionMessage\(content='([^']*)'",
                    r"text='([^']*)'",
                    r'text="([^"]*)"'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        content = match.group(1)
                        break
            
            # Clean and return the response
            cleaned_content = content.strip().replace('\\n', '\n').replace('\\"', '"')
            logger.info(f"Generated intelligent response: {cleaned_content[:200]}...")
            
            return cleaned_content
            
        except Exception as e:
            logger.error(f"SK response generation failed: {e}")
            raise Exception(f"Failed to generate intelligent response: {e}")
    
    def _format_data_summary_for_llm(self, data_summary: Dict[str, Any]) -> str:
        """Format the data summary into readable text for the LLM"""
        
        if not data_summary.get("has_data", False):
            return "No satellite data was found for this query. The search returned zero results."
        
        # Build formatted summary
        summary_parts = []
        
        # Basic statistics
        summary_parts.append(f"SEARCH RESULTS: Found {data_summary['total_images']} satellite images")
        
        # Collections and their descriptions
        if data_summary.get("collections"):
            summary_parts.append("SATELLITE DATA TYPES:")
            collection_details = data_summary.get("collection_details", {})
            for collection in data_summary["collections"]:
                description = collection_details.get(collection, f"{collection} data")
                summary_parts.append(f"- {collection}: {description}")
        
        # Temporal coverage
        if data_summary.get("temporal_coverage"):
            summary_parts.append(f"TIME PERIOD: {data_summary['temporal_coverage']}")
        
        # Data quality
        if data_summary.get("quality_summary"):
            summary_parts.append(f"DATA QUALITY: {data_summary['quality_summary']}")
        
        # Platforms
        if data_summary.get("platforms"):
            platforms_text = ", ".join(data_summary["platforms"])
            summary_parts.append(f"SATELLITE PLATFORMS: {platforms_text}")
        
        # Geographic coverage
        if data_summary.get("geographic_coverage"):
            summary_parts.append(f"GEOGRAPHIC COVERAGE: {data_summary['geographic_coverage']}")
        
        return "\n".join(summary_parts)


# =============================================================================
# STANDALONE WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# =============================================================================

async def process_query_with_openai(query: str) -> Dict[str, Any]:
    """
    Standalone function wrapper for processing queries with Azure OpenAI
    
    This function provides backward compatibility for code that expects
    a standalone process_query_with_openai function.
    
    Args:
        query: Natural language query to process
        
    Returns:
        Dictionary containing STAC query and extracted entities
    """
    try:
        logger.info(f"🔍 Processing standalone query: '{query}'")
        
        # Get configuration from environment
        endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        api_key = os.getenv('AZURE_OPENAI_API_KEY') 
        model = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', os.getenv('AZURE_OPENAI_MODEL_NAME', 'gpt-5'))
        
        if not endpoint or not api_key:
            logger.error("❌ Missing Azure OpenAI configuration")
            return {
                "error": "Missing Azure OpenAI configuration",
                "required_env_vars": ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"]
            }
        
        logger.info(f"✅ Using Azure OpenAI endpoint: {endpoint}")
        logger.info(f"✅ Using model: {model}")
        
        # Initialize translator and process query
        translator = SemanticQueryTranslator(endpoint, api_key, model)
        result = await translator.translate_query(query)
        
        logger.info(f"✅ Successfully processed query via standalone function")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error in standalone process_query_with_openai: {e}")
        return {
            "error": str(e),
            "query": query,
            "function": "process_query_with_openai"
        }


def process_query_with_openai_sync(query: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for the async process_query_with_openai function
    
    This allows calling the function without async/await syntax.
    
    Args:
        query: Natural language query to process
        
    Returns:
        Dictionary containing STAC query and extracted entities
    """
    try:
        logger.info(f"🔄 Running synchronous wrapper for: '{query}'")
        result = asyncio.run(process_query_with_openai(query))
        return result
    except Exception as e:
        logger.error(f"❌ Error in synchronous wrapper: {e}")
        return {
            "error": str(e),
            "query": query,
            "function": "process_query_with_openai_sync"
        }


# For module-level access without instantiation
async def create_semantic_translator() -> SemanticQueryTranslator:
    """
    Factory function to create a configured SemanticQueryTranslator instance
    
    Returns:
        Configured SemanticQueryTranslator instance
    """
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    model = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', os.getenv('AZURE_OPENAI_MODEL_NAME', 'gpt-5'))
    
    if not endpoint or not api_key:
        raise ValueError("Missing required Azure OpenAI configuration")
    
    return SemanticQueryTranslator(endpoint, api_key, model)
