/**
 * COMPREHENSIVE AZURE MAPS + STAC DEBUGGING SYSTEM
 * 
 * This will inject deep debugging into MapView.tsx to trace:
 * 1. Exactly what coordinates are being calculated
 * 2. What tile URLs are being generated
 * 3. What the Azure Maps SDK is doing
 * 4. Real-time tile load success/failure tracking
 */

// ============================================================================
// COORDINATE DEBUGGING UTILITIES
// ============================================================================

window.MapDebugger = {
    enabled: true,
    logLevel: 'ALL', // 'ERROR', 'WARN', 'INFO', 'DEBUG', 'ALL'
    tileRequests: new Map(),
    coordinateTransforms: [],
    stacResults: null,
    azureMapsLayers: [],
    
    log(level, category, message, data = null) {
        if (!this.enabled) return;
        
        const levels = ['ERROR', 'WARN', 'INFO', 'DEBUG', 'ALL'];
        const currentLevelIndex = levels.indexOf(this.logLevel);
        const messageLevelIndex = levels.indexOf(level);
        
        if (messageLevelIndex <= currentLevelIndex) {
            const timestamp = new Date().toISOString().split('T')[1];
            const prefix = `[MAP] [${timestamp}] [${level}] [${category}]`;
            
            console.group(prefix + ' ' + message);
            if (data) {
                console.log('Data:', data);
            }
            console.trace('Stack trace');
            console.groupEnd();
            
            // Store for analysis
            if (!window.debugLogs) window.debugLogs = [];
            window.debugLogs.push({
                timestamp: new Date(),
                level,
                category,
                message,
                data
            });
        }
    },
    
    // Geographic coordinate utilities (matching our Python test)
    deg2num(lat, lon, zoom) {
        const latRad = lat * Math.PI / 180;
        const n = Math.pow(2, zoom);
        const x = Math.floor((lon + 180) / 360 * n);
        const y = Math.floor((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2 * n);
        return { x, y };
    },
    
    num2deg(x, y, zoom) {
        const n = Math.pow(2, zoom);
        const lon = x / n * 360 - 180;
        const latRad = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n)));
        const lat = latRad * 180 / Math.PI;
        return { lat, lon };
    },
    
    // Validate tile coordinates against feature bbox
    validateTileCoordinates(tileX, tileY, zoom, featureBbox) {
        this.log('DEBUG', 'TILE_VALIDATION', `Validating tile ${tileX},${tileY} at zoom ${zoom}`, {
            tile: { x: tileX, y: tileY, z: zoom },
            bbox: featureBbox
        });
        
        // Calculate tile bounds
        const topLeft = this.num2deg(tileX, tileY, zoom);
        const bottomRight = this.num2deg(tileX + 1, tileY + 1, zoom);
        
        const tileBounds = [
            topLeft.lon,     // west
            bottomRight.lat, // south  
            bottomRight.lon, // east
            topLeft.lat      // north
        ];
        
        this.log('DEBUG', 'TILE_BOUNDS', 'Calculated tile bounds', {
            tileBounds,
            featureBbox,
            topLeft,
            bottomRight
        });
        
        // Check overlap
        const overlap = !(
            tileBounds[2] < featureBbox[0] || // tile east < bbox west
            tileBounds[0] > featureBbox[2] || // tile west > bbox east  
            tileBounds[3] < featureBbox[1] || // tile north < bbox south
            tileBounds[1] > featureBbox[3]    // tile south > bbox north
        );
        
        this.log(overlap ? 'INFO' : 'ERROR', 'TILE_OVERLAP', 
            `Tile ${overlap ? 'OVERLAPS' : 'DOES NOT OVERLAP'} with feature`, {
                overlap,
                tileBounds,
                featureBbox
            });
        
        return { overlap, tileBounds };
    },
    
    // Calculate correct tile coordinates for a feature
    calculateCorrectTiles(feature, zoom) {
        const bbox = feature.bbox;
        const center = [
            (bbox[0] + bbox[2]) / 2, // lon
            (bbox[1] + bbox[3]) / 2  // lat
        ];
        
        this.log('INFO', 'TILE_CALCULATION', 'Calculating tiles for feature', {
            featureId: feature.id,
            bbox,
            center,
            zoom
        });
        
        // Calculate center tile
        const centerTile = this.deg2num(center[1], center[0], zoom);
        
        // Calculate bbox tile range
        const minTile = this.deg2num(bbox[1], bbox[0], zoom); // south-west
        const maxTile = this.deg2num(bbox[3], bbox[2], zoom); // north-east
        
        const result = {
            center: centerTile,
            bbox: {
                min: minTile,
                max: maxTile,
                width: maxTile.x - minTile.x + 1,
                height: maxTile.y - minTile.y + 1
            },
            recommended: centerTile,
            alternatives: [
                centerTile,
                minTile,
                maxTile,
                { x: Math.floor((minTile.x + maxTile.x) / 2), y: Math.floor((minTile.y + maxTile.y) / 2) }
            ]
        };
        
        this.log('INFO', 'TILE_CALCULATION_RESULT', 'Calculated tile coordinates', result);
        
        return result;
    },
    
    // Test a tile URL directly
    async testTileUrl(url, tileInfo = {}) {
        const requestId = Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        this.tileRequests.set(requestId, {
            url,
            tileInfo,
            startTime: Date.now(),
            status: 'pending'
        });
        
        this.log('DEBUG', 'TILE_REQUEST', `Testing tile URL [${requestId}]`, {
            url,
            tileInfo,
            requestId
        });
        
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'image/png,image/*,*/*',
                    'Cache-Control': 'no-cache'
                }
            });
            
            const duration = Date.now() - this.tileRequests.get(requestId).startTime;
            const success = response.status === 200;
            
            this.tileRequests.set(requestId, {
                ...this.tileRequests.get(requestId),
                status: success ? 'success' : 'failed',
                response: {
                    status: response.status,
                    statusText: response.statusText,
                    headers: Object.fromEntries(response.headers.entries()),
                    contentType: response.headers.get('content-type'),
                    contentLength: response.headers.get('content-length')
                },
                duration
            });
            
            if (success) {
                this.log('INFO', 'TILE_SUCCESS', `[OK] Tile loaded successfully [${requestId}]`, {
                    duration: `${duration}ms`,
                    status: response.status,
                    contentLength: response.headers.get('content-length'),
                    url: url.substring(0, 100) + '...'
                });
            } else {
                const errorText = await response.text();
                this.log('ERROR', 'TILE_FAILED', `[FAIL] Tile failed [${requestId}]`, {
                    duration: `${duration}ms`,
                    status: response.status,
                    statusText: response.statusText,
                    error: errorText,
                    url: url.substring(0, 100) + '...'
                });
            }
            
            return { success, response, requestId, duration };
            
        } catch (error) {
            const duration = Date.now() - this.tileRequests.get(requestId).startTime;
            
            this.tileRequests.set(requestId, {
                ...this.tileRequests.get(requestId),
                status: 'error',
                error: error.message,
                duration
            });
            
            this.log('ERROR', 'TILE_ERROR', `[FAIL] Tile request error [${requestId}]`, {
                duration: `${duration}ms`,
                error: error.message,
                url: url.substring(0, 100) + '...'
            });
            
            return { success: false, error, requestId, duration };
        }
    },
    
    // Monitor Azure Maps layer additions
    monitorAzureMapsLayers(map) {
        if (!map) return;
        
        this.log('INFO', 'AZURE_MAPS', 'Starting Azure Maps layer monitoring', { map });
        
        // Override map.layers.add
        const originalAdd = map.layers.add.bind(map.layers);
        map.layers.add = (layer, before) => {
            this.log('INFO', 'LAYER_ADD', 'Azure Maps layer being added', {
                layer,
                before,
                layerType: layer.constructor.name,
                layerId: layer.getId ? layer.getId() : 'unknown'
            });
            
            this.azureMapsLayers.push({
                layer,
                addedAt: new Date(),
                layerType: layer.constructor.name
            });
            
            return originalAdd(layer, before);
        };
        
        // Override map.layers.remove  
        const originalRemove = map.layers.remove.bind(map.layers);
        map.layers.remove = (layer) => {
            this.log('INFO', 'LAYER_REMOVE', 'Azure Maps layer being removed', {
                layer,
                layerType: layer.constructor.name
            });
            
            return originalRemove(layer);
        };
    },
    
    // Generate debugging report
    generateReport() {
        const report = {
            timestamp: new Date().toISOString(),
            summary: {
                totalTileRequests: this.tileRequests.size,
                successfulTiles: Array.from(this.tileRequests.values()).filter(r => r.status === 'success').length,
                failedTiles: Array.from(this.tileRequests.values()).filter(r => r.status === 'failed').length,
                errorTiles: Array.from(this.tileRequests.values()).filter(r => r.status === 'error').length,
                coordinateTransforms: this.coordinateTransforms.length,
                azureMapsLayers: this.azureMapsLayers.length
            },
            tileRequests: Object.fromEntries(this.tileRequests.entries()),
            coordinateTransforms: this.coordinateTransforms,
            stacResults: this.stacResults,
            azureMapsLayers: this.azureMapsLayers.map(l => ({
                layerType: l.layerType,
                addedAt: l.addedAt
            })),
            logs: window.debugLogs || []
        };
        
        console.group('[MAP] MAP DEBUGGING REPORT');
        console.log('Report:', report);
        console.groupEnd();
        
        // Save to localStorage for persistence
        localStorage.setItem('mapDebuggingReport', JSON.stringify(report, null, 2));
        
        return report;
    },
    
    // Clear debugging data
    clear() {
        this.tileRequests.clear();
        this.coordinateTransforms = [];
        this.stacResults = null;
        this.azureMapsLayers = [];
        window.debugLogs = [];
        localStorage.removeItem('mapDebuggingReport');
        this.log('INFO', 'DEBUG', 'Debugging data cleared');
    }
};

// ============================================================================
// SPECIFIC STAC DEBUGGING
// ============================================================================

window.STACDebugger = {
    // Store STAC query and response for analysis
    captureSTACQuery(query, response) {
        window.MapDebugger.stacResults = {
            query,
            response,
            capturedAt: new Date(),
            featuresCount: response.features ? response.features.length : 0
        };
        
        window.MapDebugger.log('INFO', 'STAC_CAPTURE', 'STAC query and response captured', {
            query,
            featuresCount: response.features ? response.features.length : 0,
            firstFeature: response.features ? response.features[0] : null
        });
        
        // Analyze each feature for tile potential
        if (response.features) {
            response.features.forEach((feature, index) => {
                this.analyzeFeatureForTiles(feature, index);
            });
        }
    },
    
    // Analyze a feature for its tile potential
    analyzeFeatureForTiles(feature, index = 0) {
        window.MapDebugger.log('DEBUG', 'FEATURE_ANALYSIS', `Analyzing feature ${index}`, {
            featureId: feature.id,
            collection: feature.collection,
            bbox: feature.bbox,
            assets: Object.keys(feature.assets || {})
        });
        
        // Check for tilejson asset
        const assets = feature.assets || {};
        if (assets.tilejson) {
            window.MapDebugger.log('INFO', 'TILEJSON_FOUND', `Feature ${index} has tilejson asset`, {
                tilejsonUrl: assets.tilejson.href,
                assetType: assets.tilejson.type
            });
            
            // Test tilejson URL
            this.testTilejsonAsset(assets.tilejson.href, feature, index);
        } else {
            window.MapDebugger.log('WARN', 'NO_TILEJSON', `Feature ${index} has no tilejson asset`, {
                availableAssets: Object.keys(assets)
            });
        }
    },
    
    // Test tilejson asset
    async testTilejsonAsset(tilejsonUrl, feature, featureIndex) {
        try {
            window.MapDebugger.log('DEBUG', 'TILEJSON_TEST', `Testing tilejson URL for feature ${featureIndex}`, {
                url: tilejsonUrl
            });
            
            const response = await fetch(tilejsonUrl);
            
            if (response.ok) {
                const tilejsonData = await response.json();
                
                window.MapDebugger.log('INFO', 'TILEJSON_SUCCESS', `Tilejson loaded for feature ${featureIndex}`, {
                    bounds: tilejsonData.bounds,
                    center: tilejsonData.center,
                    minZoom: tilejsonData.minzoom,
                    maxZoom: tilejsonData.maxzoom,
                    tiles: tilejsonData.tiles
                });
                
                // Test actual tiles from this tilejson
                if (tilejsonData.tiles && tilejsonData.tiles.length > 0) {
                    await this.testTilesFromTilejson(tilejsonData, feature, featureIndex);
                }
                
            } else {
                window.MapDebugger.log('ERROR', 'TILEJSON_FAILED', `Tilejson failed for feature ${featureIndex}`, {
                    status: response.status,
                    statusText: response.statusText
                });
            }
            
        } catch (error) {
            window.MapDebugger.log('ERROR', 'TILEJSON_ERROR', `Tilejson error for feature ${featureIndex}`, {
                error: error.message
            });
        }
    },
    
    // Test tiles from tilejson using correct coordinates
    async testTilesFromTilejson(tilejsonData, feature, featureIndex) {
        const tileTemplate = tilejsonData.tiles[0];
        const testZooms = [8, 10, 12]; // Test multiple zoom levels
        
        window.MapDebugger.log('DEBUG', 'TILE_TESTING', `Testing tiles for feature ${featureIndex}`, {
            tileTemplate,
            testZooms,
            featureBbox: feature.bbox
        });
        
        for (const zoom of testZooms) {
            // Calculate correct tile coordinates using our debugger
            const tileCalc = window.MapDebugger.calculateCorrectTiles(feature, zoom);
            
            // Test the recommended tile
            const { x, y } = tileCalc.recommended;
            const tileUrl = tileTemplate
                .replace('{z}', zoom.toString())
                .replace('{x}', x.toString()) 
                .replace('{y}', y.toString());
            
            const result = await window.MapDebugger.testTileUrl(tileUrl, {
                zoom,
                x,
                y,
                featureIndex,
                featureId: feature.id,
                tileType: 'recommended'
            });
            
            if (result.success) {
                window.MapDebugger.log('INFO', 'WORKING_TILE_FOUND', `[OK] Found working tile for feature ${featureIndex}`, {
                    zoom,
                    x,
                    y,
                    url: tileUrl.substring(0, 100) + '...',
                    duration: result.duration
                });
                
                // Stop testing if we found a working tile
                break;
            }
        }
    }
};

// ============================================================================
// UI INTEGRATION HELPERS
// ============================================================================

// Helper to inject debugging into existing map instance
window.enableMapDebugging = function(map) {
    if (map) {
        window.MapDebugger.monitorAzureMapsLayers(map);
        window.MapDebugger.log('INFO', 'DEBUG_ENABLED', 'Map debugging enabled', { map });
    }
};

// Helper to run our known working test
window.testKnownWorkingQuery = async function() {
    window.MapDebugger.log('INFO', 'KNOWN_TEST', 'Running known working STAC query test');
    
    const testQuery = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [-122.5, 47.5, -122.3, 47.7],
        "datetime": "2024-06-01T00:00:00Z/2024-08-31T23:59:59Z",
        "limit": 10,
        "query": {
            "eo:cloud_cover": {"lt": 20}
        }
    };
    
    try {
        const response = await fetch('http://localhost:7071/api/stac_search_endpoint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(testQuery)
        });
        
        if (response.ok) {
            const data = await response.json();
            window.STACDebugger.captureSTACQuery(testQuery, data);
            window.MapDebugger.log('INFO', 'KNOWN_TEST_SUCCESS', 'Known working query succeeded', {
                featuresCount: data.features ? data.features.length : 0
            });
            return data;
        } else {
            window.MapDebugger.log('ERROR', 'KNOWN_TEST_FAILED', 'Known working query failed', {
                status: response.status
            });
        }
    } catch (error) {
        window.MapDebugger.log('ERROR', 'KNOWN_TEST_ERROR', 'Known working query error', {
            error: error.message
        });
    }
};

// Export debugging report  
window.downloadDebugReport = function() {
    const report = window.MapDebugger.generateReport();
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `map-debug-report-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
};

console.log('[MAP] MAP DEBUGGING SYSTEM LOADED');
console.log('Available functions:');
console.log('- window.MapDebugger.* - Core debugging utilities');
console.log('- window.STACDebugger.* - STAC-specific debugging');
console.log('- window.enableMapDebugging(map) - Enable debugging on map instance');
console.log('- window.testKnownWorkingQuery() - Test our proven working query');
console.log('- window.downloadDebugReport() - Download full debugging report');
