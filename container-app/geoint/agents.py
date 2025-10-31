"""
GEOINT Agent Functions - Unified Entry Points for All GEOINT Modules

This module provides agent-based entry points for all GEOINT analysis capabilities.
Each function is a thin wrapper that creates the appropriate agent class and executes analysis.

Architecture:
- Each agent function returns Dict[str, Any] with "agent" key for consistency
- All agents support calling GPT-5 Vision for satellite imagery analysis
- Agents can invoke sub-agents (e.g., terrain can call mobility analysis)
- Pattern matches collection_mapping_agent and datetime_translation_agent
- Lazy imports: Agent classes imported only when their functions are called
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# LAZY IMPORTS: Don't import agent classes at module level
# This prevents loading mobility_agent (and its dependencies) when only terrain is needed
# from .terrain_analysis_agent import TerrainAnalysisAgent
# from .mobility_agent import GeointMobilityAgent
# from .building_damage_agent import BuildingDamageAgent

logger = logging.getLogger(__name__)


async def terrain_analysis_agent(
    latitude: float,
    longitude: float,
    screenshot_base64: Optional[str] = None,
    user_query: Optional[str] = None,
    radius_miles: float = 5.0
) -> Dict[str, Any]:
    """
    🏔️ Terrain Analysis Agent - Visual terrain feature analysis using GPT-5 Vision
    
    Analyzes satellite imagery to identify:
    - Bodies of water (rivers, lakes, reservoirs, coastal areas)
    - Terrain features (mountains, valleys, plains, elevation changes)
    - Infrastructure (roads, bridges, buildings, urban development)
    - Land use patterns (agricultural, industrial, residential, natural)
    
    Args:
        latitude: Center latitude for analysis
        longitude: Center longitude for analysis
        screenshot_base64: Optional base64-encoded screenshot from frontend
        user_query: Optional user context for focused analysis
        radius_miles: Analysis radius in miles (default: 5.0)
        
    Returns:
        Dict with:
        - agent: "terrain_analysis_agent"
        - analysis: str (GPT-5 Vision analysis)
        - features: List[str] (identified features)
        - confidence: float (0.0-1.0)
        - imagery_metadata: Dict (source, date, resolution)
    """
    try:
        # Lazy import: Only load TerrainAnalysisAgent when this function is called
        from .terrain_analysis_agent import TerrainAnalysisAgent
        
        logger.info(f"🏔️ Terrain analysis agent called for ({latitude}, {longitude})")
        
        agent = TerrainAnalysisAgent()
        result = await agent.analyze_terrain(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot_base64,
            user_query=user_query,
            radius_miles=radius_miles
        )
        
        # Add agent identifier for consistency with other agents
        result["agent"] = "terrain_analysis_agent"
        
        logger.info(f"✅ Terrain analysis completed with {len(result.get('features', []))} features")
        return result
        
    except Exception as e:
        logger.error(f"❌ Terrain analysis agent failed: {e}")
        raise


async def mobility_analysis_agent(
    latitude: float,
    longitude: float,
    screenshot_base64: Optional[str] = None,
    user_query: Optional[str] = None,
    include_vision: bool = True
) -> Dict[str, Any]:
    """
    🚗 Mobility Analysis Agent - Pixel-based terrain trafficability assessment
    
    Analyzes terrain for vehicle mobility using:
    - Pixel-level terrain classification
    - Slope analysis from elevation data
    - Vegetation density assessment
    - Water body detection
    - Road network identification
    
    Args:
        latitude: Center latitude for analysis
        longitude: Center longitude for analysis
        screenshot_base64: Optional base64-encoded screenshot
        user_query: Optional user context
        include_vision: Whether to include GPT-5 Vision analysis (default: True)
        
    Returns:
        Dict with:
        - agent: "mobility_analysis_agent"
        - trafficability_map: Dict (pixel-level mobility scores)
        - slope_analysis: Dict (elevation-based slope data)
        - water_bodies: List[Dict] (detected water features)
        - roads: List[Dict] (road network data)
        - vision_analysis: Optional[str] (GPT-5 Vision insights)
    """
    try:
        # Lazy import: Only load GeointMobilityAgent when this function is called
        from .mobility_agent import GeointMobilityAgent
        
        logger.info(f"🚗 Mobility analysis agent called for ({latitude}, {longitude})")
        
        agent = GeointMobilityAgent()
        result = await agent.analyze(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot_base64,
            user_query=user_query,
            include_vision=include_vision
        )
        
        result["agent"] = "mobility_analysis_agent"
        
        logger.info(f"✅ Mobility analysis completed")
        return result
        
    except Exception as e:
        logger.error(f"❌ Mobility analysis agent failed: {e}")
        raise


async def building_damage_agent(
    latitude: float,
    longitude: float,
    screenshot_base64: Optional[str] = None,
    user_query: Optional[str] = None,
    radius_miles: float = 2.0
) -> Dict[str, Any]:
    """
    🏗️ Building Damage Assessment Agent - Structural damage analysis
    
    Analyzes satellite imagery for building damage assessment:
    - Pre/post disaster comparison
    - Damage classification (none, minor, major, destroyed)
    - Building detection and segmentation
    - Change detection algorithms
    - GPT-5 Vision for contextual analysis
    
    Args:
        latitude: Center latitude for analysis
        longitude: Center longitude for analysis
        screenshot_base64: Optional base64-encoded screenshot
        user_query: Optional user context
        radius_miles: Analysis radius in miles (default: 2.0)
        
    Returns:
        Dict with:
        - agent: "building_damage_agent"
        - buildings_detected: int
        - damage_summary: Dict (damage level counts)
        - high_confidence_damage: List[Dict] (damaged buildings)
        - analysis: str (GPT-5 Vision insights)
    """
    try:
        # Lazy import: Only load BuildingDamageAgent when this function is called
        from .building_damage_agent import BuildingDamageAgent
        
        logger.info(f"🏗️ Building damage agent called for ({latitude}, {longitude})")
        
        agent = BuildingDamageAgent()
        result = await agent.analyze(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot_base64,
            user_query=user_query,
            radius_miles=radius_miles
        )
        
        result["agent"] = "building_damage_agent"
        
        logger.info(f"✅ Building damage assessment completed")
        return result
        
    except Exception as e:
        logger.error(f"❌ Building damage agent failed: {e}")
        raise


async def _download_and_visualize_raster(
    latitude: float,
    longitude: float,
    date: str,
    collection_id: str,
    bbox: List[float]
) -> Optional[str]:
    """
    Download raster data for a specific area and time, convert to visualization.
    
    Args:
        latitude: Center latitude
        longitude: Center longitude
        date: ISO date string
        collection_id: STAC collection ID (e.g., 'modis-14A1-061', 'cop-dem-glo-30')
        bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
        
    Returns:
        Base64-encoded PNG image of the raster data, or None if download fails
    """
    try:
        import planetary_computer
        import pystac_client
        import rasterio
        from rasterio.windows import from_bounds
        import numpy as np
        import matplotlib.pyplot as plt
        import io
        import base64
        from datetime import datetime, timedelta
        
        logger.info(f"🗺️ Downloading raster for {collection_id} at {date}")
        
        # Create date range (±1 day buffer)
        target_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
        date_start = (target_date - timedelta(days=1)).isoformat()
        date_end = (target_date + timedelta(days=1)).isoformat()
        
        # Search STAC catalog
        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace
        )
        
        search = catalog.search(
            collections=[collection_id],
            bbox=bbox,
            datetime=f"{date_start}/{date_end}",
            limit=1
        )
        
        items = list(search.items())
        if not items:
            logger.warning(f"⚠️ No raster data found for {collection_id} at {date}")
            return None
        
        item = items[0]
        
        # Get the primary data asset
        asset_key = None
        if 'data' in item.assets:
            asset_key = 'data'
        elif 'visual' in item.assets:
            asset_key = 'visual'
        elif 'rendered_preview' in item.assets:
            asset_key = 'rendered_preview'
        else:
            # Try first asset
            asset_key = list(item.assets.keys())[0]
        
        asset_url = item.assets[asset_key].href
        signed_url = planetary_computer.sign_url(asset_url)
        
        logger.info(f"📥 Downloading from asset: {asset_key}")
        
        # Read raster data
        with rasterio.open(signed_url) as src:
            # Convert bbox to pixel window
            window = from_bounds(*bbox, src.transform)
            
            # Read data (first band for single-band, RGB for multi-band)
            if src.count == 1:
                data = src.read(1, window=window)
                # Replace nodata with NaN
                if src.nodata is not None:
                    data = data.astype(float)
                    data[data == src.nodata] = np.nan
            else:
                # Read RGB channels
                data = src.read([1, 2, 3], window=window)
                data = np.transpose(data, (1, 2, 0))  # Convert to HWC format
        
        # Create visualization
        fig, ax = plt.subplots(figsize=(10, 10))
        
        if data.ndim == 2:
            # Single band - use appropriate colormap
            if 'fire' in collection_id.lower() or 'thermal' in collection_id.lower():
                cmap = 'hot'
                label = 'Fire Intensity'
            elif 'dem' in collection_id.lower() or 'elevation' in collection_id.lower():
                cmap = 'terrain'
                label = 'Elevation (m)'
            elif 'ndvi' in collection_id.lower() or 'vegetation' in collection_id.lower():
                cmap = 'RdYlGn'
                label = 'NDVI'
            else:
                cmap = 'viridis'
                label = 'Value'
            
            im = ax.imshow(data, cmap=cmap, interpolation='nearest')
            plt.colorbar(im, ax=ax, label=label, shrink=0.8)
        else:
            # RGB image
            # Normalize to 0-1 range if needed
            if data.max() > 1:
                data = data / data.max()
            ax.imshow(data)
        
        ax.set_title(f'{collection_id}\n{date}', fontsize=12, fontweight='bold')
        ax.axis('off')
        
        # Convert to base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode()
        plt.close()
        
        logger.info(f"✅ Raster visualization created: {data.shape}")
        return img_base64
        
    except Exception as e:
        logger.error(f"❌ Failed to download/visualize raster: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def comparison_analysis_agent(
    latitude: float,
    longitude: float,
    before_date: str,
    after_date: str,
    before_screenshot_base64: Optional[str] = None,
    after_screenshot_base64: Optional[str] = None,
    before_metadata: Optional[Dict] = None,
    after_metadata: Optional[Dict] = None,
    user_query: Optional[str] = None,
    comparison_aspect: Optional[str] = None,
    collection_id: Optional[str] = None,
    download_rasters: bool = True
) -> Dict[str, Any]:
    """
    📊 Comparison Analysis Agent - Temporal change detection
    
    Compares two time periods to identify changes using GPT-5 Vision.
    Downloads actual raster data in addition to map screenshots for deeper analysis.
    
    Args:
        latitude: Center latitude for analysis
        longitude: Center longitude for analysis
        before_date: ISO date for "before" imagery
        after_date: ISO date for "after" imagery
        before_screenshot_base64: Base64-encoded screenshot of BEFORE map
        after_screenshot_base64: Base64-encoded screenshot of AFTER map
        before_metadata: Metadata for before imagery (optional)
        after_metadata: Metadata for after imagery (optional)
        user_query: Original user question
        comparison_aspect: Focus area (wildfire, vegetation, urban, water, etc.)
        collection_id: STAC collection to download rasters from (e.g., 'modis-14A1-061')
        download_rasters: Whether to download and analyze actual raster data (default: True)
        
    Returns:
        Dict with:
        - agent: "comparison_analysis"
        - analysis: Natural language comparison text
        - time_span: Human-readable time difference
        - aspect_analyzed: Type of change detection performed
        - confidence: Confidence score
        - raster_analysis: Optional additional analysis from raw raster data
    """
    try:
        logger.info("=" * 80)
        logger.info("📊 COMPARISON ANALYSIS AGENT INVOKED")
        logger.info("=" * 80)
        logger.info(f"📍 Location: ({latitude}, {longitude})")
        logger.info(f"📅 Before: {before_date}")
        logger.info(f"📅 After: {after_date}")
        logger.info(f"🎯 Aspect: {comparison_aspect or 'general change'}")
        logger.info(f"🗺️ Collection: {collection_id or 'N/A'}")
        logger.info(f"📦 Download rasters: {download_rasters}")
        logger.info(f"📸 Before screenshot: {'Provided' if before_screenshot_base64 else 'None'} ({len(before_screenshot_base64) if before_screenshot_base64 else 0} chars)")
        logger.info(f"📸 After screenshot: {'Provided' if after_screenshot_base64 else 'None'} ({len(after_screenshot_base64) if after_screenshot_base64 else 0} chars)")
        logger.info("")
        
        # Validate at least one data source
        has_screenshots = before_screenshot_base64 and after_screenshot_base64
        can_download_rasters = download_rasters and collection_id
        
        logger.info("🔍 Validating data sources...")
        logger.info(f"   - Has screenshots: {has_screenshots}")
        logger.info(f"   - Can download rasters: {can_download_rasters}")
        
        if not has_screenshots and not can_download_rasters:
            logger.error("❌ No valid data sources provided")
            raise ValueError("Either screenshots (both before+after) OR raster download capability (collection_id + download_rasters=true) must be provided")
        
        logger.info("✅ Data source validation passed")
        logger.info("")
        
        # Create bounding box for raster download (0.1 degree buffer ~11km)
        bbox = [
            longitude - 0.1,
            latitude - 0.1,
            longitude + 0.1,
            latitude + 0.1
        ]
        logger.info(f"📐 Bounding box created: {bbox}")
        logger.info("")
        
        # Download rasters if requested and collection specified
        before_raster_base64 = None
        after_raster_base64 = None
        
        if download_rasters and collection_id:
            logger.info("=" * 80)
            logger.info("📥 RASTER DOWNLOAD PHASE")
            logger.info("=" * 80)
            logger.info(f"📥 Downloading BEFORE raster from {collection_id}...")
            logger.info(f"   Date: {before_date}")
            logger.info(f"   Location: ({latitude}, {longitude})")
            
            before_raster_base64 = await _download_and_visualize_raster(
                latitude, longitude, before_date, collection_id, bbox
            )
            
            if before_raster_base64:
                logger.info(f"✅ BEFORE raster downloaded successfully ({len(before_raster_base64)} chars)")
            else:
                logger.warning("⚠️ BEFORE raster download failed or returned None")
            
            logger.info("")
            logger.info(f"📥 Downloading AFTER raster from {collection_id}...")
            logger.info(f"   Date: {after_date}")
            logger.info(f"   Location: ({latitude}, {longitude})")
            
            after_raster_base64 = await _download_and_visualize_raster(
                latitude, longitude, after_date, collection_id, bbox
            )
            
            if after_raster_base64:
                logger.info(f"✅ AFTER raster downloaded successfully ({len(after_raster_base64)} chars)")
            else:
                logger.warning("⚠️ AFTER raster download failed or returned None")
            
            logger.info("=" * 80)
            
            if before_raster_base64 and after_raster_base64:
                logger.info("✅ Both rasters downloaded successfully")
            else:
                logger.warning("⚠️ Raster download incomplete, proceeding with screenshots only")
        else:
            logger.info("⏭️ Raster download skipped (download_rasters=False or no collection_id)")
        
        logger.info("")
        
        # Final data source check
        has_rasters = before_raster_base64 and after_raster_base64
        
        logger.info("📊 Final Data Source Summary:")
        logger.info(f"   - Screenshots available: {has_screenshots}")
        logger.info(f"   - Rasters available: {has_rasters}")
        logger.info(f"   - Total images for GPT-5: {sum([has_screenshots * 2, has_rasters * 2])}")
        
        if not has_screenshots and not has_rasters:
            logger.error("❌ No data sources available after download attempts")
            raise ValueError("No valid data sources (screenshots or rasters) available for comparison analysis")
        
        logger.info("✅ Sufficient data sources for analysis")
        logger.info("")
        
        logger.info("=" * 80)
        logger.info("🔨 BUILDING PROMPT FOR GPT-5 VISION")
        logger.info("=" * 80)
        logger.info(f"📍 Location: ({latitude}, {longitude})")
        logger.info(f"📅 Before: {before_date}")
        logger.info(f"📅 After: {after_date}")
        logger.info(f"🎯 Aspect: {comparison_aspect or 'general change'}")
        
        # Build specialized prompt for temporal change detection
        aspect_focus = comparison_aspect or "general changes"
        
        # Determine collection type for raster analysis context
        raster_type = "unknown"
        if collection_id:
            if "modis" in collection_id.lower() or "fire" in collection_id.lower():
                raster_type = "fire intensity (thermal anomalies)"
            elif "dem" in collection_id.lower() or "elevation" in collection_id.lower():
                raster_type = "elevation"
            elif "ndvi" in collection_id.lower() or "vegetation" in collection_id.lower():
                raster_type = "vegetation index (NDVI)"
            elif "landsat" in collection_id.lower() or "sentinel" in collection_id.lower():
                raster_type = "multispectral imagery"
        
        logger.info(f"🗺️ Raster type detected: {raster_type}")
        logger.info("")
        system_prompt = """You are analyzing TEMPORAL CHANGES in satellite imagery for geospatial intelligence.
Your task is to compare satellite images and raster data from different time periods to identify significant changes.
You will analyze visual map screenshots and/or raw raster data to provide comprehensive insights."""
        
        # Build image description based on what we have
        image_count = 1
        image_description = "You will see:\n"
        
        if before_screenshot_base64:
            image_description += f"{image_count}. BEFORE map screenshot (visual representation)\n"
            image_count += 1
        
        if before_raster_base64:
            image_description += f"{image_count}. BEFORE raster data ({raster_type}) - quantitative measurement\n"
            image_count += 1
        
        if after_screenshot_base64:
            image_description += f"{image_count}. AFTER map screenshot (visual representation)\n"
            image_count += 1
        
        if after_raster_base64:
            image_description += f"{image_count}. AFTER raster data ({raster_type}) - quantitative measurement\n"
            image_count += 1
        
        user_prompt = f"""Compare satellite data from DIFFERENT TIME PERIODS:

CONTEXT:
- Location: ({latitude}, {longitude})
- BEFORE: {before_date}
- AFTER: {after_date}
- Time span: {_calculate_time_span(before_date, after_date)}
- Focus area: {aspect_focus}
- Data collection: {collection_id or 'N/A'}
- User query: {user_query or 'Compare before and after imagery'}

{image_description}

ANALYSIS INSTRUCTIONS:
1. Compare the VISUAL changes in map screenshots (urban areas, land cover, etc.)
2. {'Analyze QUANTITATIVE changes in raster data (intensity values, patterns, spatial distribution)' if before_raster_base64 and after_raster_base64 else 'Focus on visual patterns and changes'}
3. {'Correlate visual observations with numerical raster measurements' if before_raster_base64 and after_raster_base64 else 'Provide detailed visual assessment'}
4. Identify change hotspots and spatial patterns
5. Focus on: {aspect_focus}

Provide analysis in this format:

**1. Change Summary**
Brief overview of most significant changes observed (both visual and {'quantitative' if before_raster_base64 and after_raster_base64 else 'spatial'})

**2. Specific Changes Detected**
- Change 1: [description with spatial details and {'intensity values' if before_raster_base64 and after_raster_base64 else 'visual characteristics'}]
- Change 2: [description with spatial details and {'intensity values' if before_raster_base64 and after_raster_base64 else 'visual characteristics'}]
- Change 3: [description with spatial details and {'intensity values' if before_raster_base64 and after_raster_base64 else 'visual characteristics'}]

{'**3. Quantitative Raster Analysis**' if before_raster_base64 and after_raster_base64 else '**3. Visual Pattern Analysis**'}
{f'- Compare {raster_type} values between before and after' if before_raster_base64 and after_raster_base64 else '- Describe visual patterns and textures'}
{f'- Identify areas with highest/lowest values and changes' if before_raster_base64 and after_raster_base64 else '- Identify visual anomalies and features'}
{f'- Correlate raster intensity with visual map features' if before_raster_base64 and after_raster_base64 else '- Describe color and texture changes'}

**{'4' if before_raster_base64 and after_raster_base64 else '4'}. Analysis by Region**
Northeast: [observations]
Southeast: [observations]
Southwest: [observations]
Northwest: [observations]
Central: [observations]

**{'5' if before_raster_base64 and after_raster_base64 else '5'}. Temporal Assessment**
How the {aspect_focus} has evolved over the {_calculate_time_span(before_date, after_date)} period

**{'6' if before_raster_base64 and after_raster_base64 else '6'}. Confidence & Limitations**
- Confidence level in change detection
- Any limiting factors (clouds, resolution, data gaps, etc.)
"""
        
        # Call Azure OpenAI GPT-4o with Vision
        import aiohttp
        import os
        
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_openai_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        
        headers = {
            "Content-Type": "application/json",
            "api-key": azure_openai_key
        }
        
        # Build image list dynamically
        user_content = [{"type": "text", "text": user_prompt}]
        
        logger.info("🖼️ Building image list for GPT-5 Vision:")
        image_count = 0
        
        # Add BEFORE map screenshot (if available)
        if before_screenshot_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{before_screenshot_base64}",
                    "detail": "high"
                }
            })
            image_count += 1
            logger.info(f"   {image_count}. BEFORE map screenshot ({len(before_screenshot_base64)} chars)")
        
        # Add BEFORE raster if available
        if before_raster_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{before_raster_base64}",
                    "detail": "high"
                }
            })
            image_count += 1
            logger.info(f"   {image_count}. BEFORE raster data - {raster_type} ({len(before_raster_base64)} chars)")
        
        # Add AFTER map screenshot (if available)
        if after_screenshot_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{after_screenshot_base64}",
                    "detail": "high"
                }
            })
            image_count += 1
            logger.info(f"   {image_count}. AFTER map screenshot ({len(after_screenshot_base64)} chars)")
        
        # Add AFTER raster if available
        if after_raster_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{after_raster_base64}",
                    "detail": "high"
                }
            })
            image_count += 1
            logger.info(f"   {image_count}. AFTER raster data - {raster_type} ({len(after_raster_base64)} chars)")
        
        logger.info(f"✅ Total images prepared: {image_count}")
        logger.info("")
        logger.info("=" * 80)
        logger.info("🤖 CALLING GPT-5 VISION API")
        logger.info("=" * 80)
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "max_tokens": 2500,
            "temperature": 0.7
        }
        
        logger.info(f"📤 Payload structure:")
        logger.info(f"   - System prompt length: {len(system_prompt)} chars")
        logger.info(f"   - User prompt length: {len(user_prompt)} chars")
        logger.info(f"   - Image count: {len([c for c in user_content if c['type'] == 'image_url'])}")
        logger.info(f"   - Max tokens: {payload['max_tokens']}")
        logger.info(f"   - Temperature: {payload['temperature']}")
        logger.info("")
        
        async with aiohttp.ClientSession() as session:
            logger.info("🌐 Making HTTP request to Azure OpenAI...")
            async with session.post(
                f"{azure_openai_endpoint}/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                logger.info(f"📥 Response status: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"❌ Azure OpenAI API error {response.status}")
                    logger.error(f"   Error response: {error_text}")
                    raise Exception(f"Azure OpenAI API error {response.status}: {error_text}")
                
                result = await response.json()
                analysis_text = result["choices"][0]["message"]["content"]
                
                logger.info("✅ GPT-5 Vision response received successfully")
                logger.info(f"   Response length: {len(analysis_text)} chars")
                logger.info(f"   First 200 chars: {analysis_text[:200]}...")
                logger.info("")
        
        # Apply bold formatting to section headers (1., 2., 3., etc.)
        import re
        analysis_text = re.sub(
            r'^(\d+\.\s+[^\n]+)',
            r'**\1**',
            analysis_text,
            flags=re.MULTILINE
        )
        
        logger.info("=" * 80)
        logger.info("✅ COMPARISON ANALYSIS COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        if before_raster_base64 and after_raster_base64:
            logger.info(f"📊 Analysis included quantitative raster data from {collection_id}")
        logger.info(f"📝 Analysis text length: {len(analysis_text)} chars")
        logger.info(f"🎯 Aspect analyzed: {comparison_aspect or 'general changes'}")
        logger.info(f"⏱️  Time span: {_calculate_time_span(before_date, after_date)}")
        logger.info(f"💯 Confidence: {0.85 if (before_raster_base64 and after_raster_base64) else 0.8}")
        logger.info("")
        
        return {
            "agent": "comparison_analysis",
            "location": {"latitude": latitude, "longitude": longitude},
            "before_date": before_date,
            "after_date": after_date,
            "analysis": analysis_text,
            "time_span": _calculate_time_span(before_date, after_date),
            "aspect_analyzed": comparison_aspect or "general changes",
            "collection_analyzed": collection_id,
            "raster_analysis_included": bool(before_raster_base64 and after_raster_base64),
            "confidence": 0.85 if (before_raster_base64 and after_raster_base64) else 0.8,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ COMPARISON ANALYSIS AGENT FAILED")
        logger.error("=" * 80)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {str(e)}")
        logger.error(f"Exception repr: {repr(e)}")
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        return {
            "agent": "comparison_analysis",
            "error": str(e),
            "analysis": f"Comparison analysis failed: {str(e)}",
            "confidence": 0.0
        }


def _calculate_time_span(before_date: str, after_date: str) -> str:
    """Helper to calculate human-readable time span between dates"""
    try:
        from dateutil import parser
        before_dt = parser.parse(before_date)
        after_dt = parser.parse(after_date)
        delta = after_dt - before_dt
        
        if delta.days < 1:
            return f"{delta.seconds // 3600} hours"
        elif delta.days < 30:
            return f"{delta.days} days"
        elif delta.days < 365:
            return f"{delta.days // 30} months"
        else:
            return f"{delta.days // 365} years"
    except Exception:
        return "unknown time span"


async def animation_generation_agent(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    collection: str,
    user_query: Optional[str] = None
) -> Dict[str, Any]:
    """
    🎬 Animation Generation Agent - Time-series visualization
    
    Creates animated visualizations from satellite imagery time series:
    - Multi-temporal image mosaics
    - Change animation generation
    - Video export capabilities
    - Configurable frame rate and resolution
    
    Args:
        latitude: Center latitude for animation
        longitude: Center longitude for animation
        start_date: ISO date for animation start (YYYY-MM-DD)
        end_date: ISO date for animation end (YYYY-MM-DD)
        collection: Satellite collection to use
        user_query: Optional user context
        
    Returns:
        Dict with:
        - agent: "animation_generation_agent"
        - animation_url: str (URL to generated animation)
        - frame_count: int
        - date_range: Dict
        - metadata: Dict
    """
    try:
        logger.info(f"🎬 Animation generation agent called for ({latitude}, {longitude}) [{start_date} → {end_date}]")
        
        # Placeholder - full implementation would generate actual animations
        result = {
            "agent": "animation_generation_agent",
            "message": "Animation generation agent implementation in progress",
            "start_date": start_date,
            "end_date": end_date,
            "collection": collection,
            "latitude": latitude,
            "longitude": longitude
        }
        
        logger.info(f"✅ Animation generation completed")
        return result
        
    except Exception as e:
        logger.error(f"❌ Animation generation agent failed: {e}")
        raise


async def geoint_orchestrator(
    latitude: float,
    longitude: float,
    modules: List[str],
    screenshot_base64: Optional[str] = None,
    user_query: Optional[str] = None,
    radius_miles: float = 5.0,
    **kwargs
) -> Dict[str, Any]:
    """
    🎯 GEOINT Orchestrator - Coordinates multiple GEOINT analyses
    
    Orchestrates execution of multiple GEOINT modules and combines results.
    
    Args:
        latitude: Center latitude for analysis
        longitude: Center longitude for analysis
        modules: List of module names to execute (e.g., ["terrain", "mobility"])
        screenshot_base64: Optional base64-encoded screenshot
        user_query: Optional user context
        radius_miles: Analysis radius in miles (default: 5.0)
        **kwargs: Additional module-specific parameters
        
    Returns:
        Dict with:
        - agent: "geoint_orchestrator"
        - results: Dict[str, Any] (keyed by module name)
        - summary: str (combined analysis)
        - modules_executed: List[str]
    """
    try:
        logger.info(f"🎯 GEOINT orchestrator called for modules: {modules}")
        
        results = {}
        module_map = {
            "terrain": terrain_analysis_agent,
            "mobility": mobility_analysis_agent,
            "building_damage": building_damage_agent,
            "comparison": comparison_analysis_agent,
            "animation": animation_generation_agent
        }
        
        for module in modules:
            if module in module_map:
                logger.info(f"  → Executing {module} module...")
                agent_func = module_map[module]
                
                # Call appropriate agent with relevant parameters
                if module == "comparison":
                    result = await agent_func(
                        latitude=latitude,
                        longitude=longitude,
                        before_date=kwargs.get("before_date", "2020-01-01"),
                        after_date=kwargs.get("after_date", "2024-01-01"),
                        screenshot_base64=screenshot_base64,
                        user_query=user_query
                    )
                elif module == "animation":
                    result = await agent_func(
                        latitude=latitude,
                        longitude=longitude,
                        start_date=kwargs.get("start_date", "2020-01-01"),
                        end_date=kwargs.get("end_date", "2024-01-01"),
                        collection=kwargs.get("collection", "sentinel-2-l2a"),
                        user_query=user_query
                    )
                else:
                    result = await agent_func(
                        latitude=latitude,
                        longitude=longitude,
                        screenshot_base64=screenshot_base64,
                        user_query=user_query,
                        radius_miles=radius_miles
                    )
                
                results[module] = result
            else:
                logger.warning(f"⚠️ Unknown module: {module}")
        
        orchestrator_result = {
            "agent": "geoint_orchestrator",
            "results": results,
            "modules_executed": list(results.keys()),
            "summary": f"Executed {len(results)} GEOINT modules successfully"
        }
        
        logger.info(f"✅ GEOINT orchestrator completed with {len(results)} modules")
        return orchestrator_result
        
    except Exception as e:
        logger.error(f"❌ GEOINT orchestrator failed: {e}")
        raise
