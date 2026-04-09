/**
 * GEOINT Overlay Component for Earth-Copilot
 * 
 * This component provides visualization for geospatial intelligence analysis including:
 * - Terrain analysis (slope, aspect, hillshade)
 * - Mobility classification overlays
 * - Line-of-sight analysis visualization
 * - Elevation profile displays
 * 
 * Integrates with Azure Maps and processes GEOINT service responses.
 */

import React, { useEffect, useState, useRef } from 'react';
import { Dataset } from '../services/api';

// Declare global atlas for TypeScript
declare global {
  interface Window {
    atlas: any;
  }
}

interface GeointOverlayProps {
  map: any; // Azure Maps instance
  geointData: GeointAnalysisResult | null;
  isVisible: boolean;
  onVisibilityToggle: (visible: boolean) => void;
}

interface GeointAnalysisResult {
  service_type: string;
  analysis_type: string;
  bbox: number[] | null;
  terrain_analysis?: TerrainAnalysisData;
  mobility_analysis?: MobilityAnalysisData;
  line_of_sight?: LineOfSightData;
  elevation_profile?: ElevationProfileData;
}

interface TerrainAnalysisData {
  slope?: {
    data: number[][];
    statistics: any;
    classification: any;
  };
  aspect?: {
    data: number[][];
    statistics: any;
  };
  hillshade?: {
    data: number[][];
  };
  roughness?: {
    data: number[][];
    statistics: any;
  };
}

interface MobilityAnalysisData {
  mobility_grid: string[][];
  statistics: {
    go_percentage: number;
    slow_go_percentage: number;
    no_go_percentage: number;
  };
  corridors: Array<{
    id: number;
    size_pixels: number;
    centroid: { x: number; y: number };
  }>;
  recommendations: string[];
}

interface LineOfSightData {
  is_visible: boolean;
  observer_point: number[];
  target_point: number[];
  visibility_angle: number;
  obstruction?: {
    distance_from_observer: number;
    elevation: number;
    coordinates: number[];
  };
  viewshed_sample?: any;
}

interface ElevationProfileData {
  distances: number[];
  elevations: number[];
  slope_profile: number[];
  statistics: any;
  features: Array<{
    type: string;
    distance: number;
    elevation: number;
    description: string;
  }>;
}

const GeointOverlay: React.FC<GeointOverlayProps> = ({
  map,
  geointData,
  isVisible,
  onVisibilityToggle
}) => {
  const [overlayLayers, setOverlayLayers] = useState<any[]>([]);
  const [activeAnalysis, setActiveAnalysis] = useState<string | null>(null);
  const [showControls, setShowControls] = useState(false);
  const [selectedVisualization, setSelectedVisualization] = useState<string>('slope');
  const overlayRef = useRef<HTMLDivElement>(null);

  // Initialize GEOINT overlay when data is available
  useEffect(() => {
    if (!map || !geointData || !isVisible) {
      clearOverlays();
      return;
    }

    console.log('Initializing GEOINT overlay:', geointData.analysis_type);
    setActiveAnalysis(geointData.analysis_type);
    
    // Render appropriate visualization based on analysis type
    switch (geointData.analysis_type) {
      case 'terrain_analysis':
        renderTerrainAnalysis(geointData.terrain_analysis);
        break;
      case 'mobility_analysis':
        renderMobilityAnalysis(geointData.mobility_analysis);
        break;
      case 'line_of_sight':
        renderLineOfSight(geointData.line_of_sight);
        break;
      case 'elevation_profile':
        renderElevationProfile(geointData.elevation_profile);
        break;
      default:
        console.warn('Unknown GEOINT analysis type:', geointData.analysis_type);
    }

    setShowControls(true);
  }, [map, geointData, isVisible]);

  // Clear overlays when component unmounts or becomes invisible
  useEffect(() => {
    if (!isVisible) {
      clearOverlays();
      setShowControls(false);
    }
  }, [isVisible]);

  const clearOverlays = () => {
    if (map && overlayLayers.length > 0) {
      overlayLayers.forEach(layer => {
        try {
          map.layers.remove(layer);
        } catch (e) {
          console.warn('Error removing overlay layer:', e);
        }
      });
      setOverlayLayers([]);
    }
  };

  const renderTerrainAnalysis = (terrainData?: TerrainAnalysisData) => {
    if (!terrainData || !map) return;

    console.log('Rendering terrain analysis overlay');
    
    // Create terrain visualization based on selected type
    const visualizationType = selectedVisualization;
    const analysisData = terrainData[visualizationType as keyof TerrainAnalysisData];
    
    if (!analysisData) {
      console.warn(`No data available for ${visualizationType}`);
      return;
    }

    try {
      // Create raster overlay for terrain data
      const terrainLayer = createRasterOverlay(
        analysisData.data,
        geointData?.bbox || [-180, -90, 180, 90],
        getTerrainColorScale(visualizationType)
      );

      if (terrainLayer) {
        map.layers.add(terrainLayer);
        setOverlayLayers(prev => [...prev, terrainLayer]);
      }
    } catch (error) {
      console.error('Error rendering terrain analysis:', error);
    }
  };

  const renderMobilityAnalysis = (mobilityData?: MobilityAnalysisData) => {
    if (!mobilityData || !map) return;

    console.log('Rendering mobility analysis overlay');

    try {
      // Create mobility classification overlay
      const mobilityLayer = createMobilityOverlay(
        mobilityData.mobility_grid,
        geointData?.bbox || [-180, -90, 180, 90]
      );

      if (mobilityLayer) {
        map.layers.add(mobilityLayer);
        setOverlayLayers(prev => [...prev, mobilityLayer]);
      }
    } catch (error) {
      console.error('Error rendering mobility analysis:', error);
    }
  };

  const renderLineOfSight = (losData?: LineOfSightData) => {
    if (!losData || !map) return;

    console.log('Rendering line-of-sight analysis');

    try {
      // Create line-of-sight line
      const losLine = createLineOfSightLine(
        losData.observer_point,
        losData.target_point,
        losData.is_visible
      );

      if (losLine) {
        map.layers.add(losLine);
        setOverlayLayers(prev => [...prev, losLine]);
      }

      // Add observer and target markers
      const observerMarker = createObserverMarker(losData.observer_point);
      const targetMarker = createTargetMarker(losData.target_point, losData.is_visible);

      if (observerMarker) {
        map.layers.add(observerMarker);
        setOverlayLayers(prev => [...prev, observerMarker]);
      }

      if (targetMarker) {
        map.layers.add(targetMarker);
        setOverlayLayers(prev => [...prev, targetMarker]);
      }
    } catch (error) {
      console.error('Error rendering line-of-sight:', error);
    }
  };

  const renderElevationProfile = (profileData?: ElevationProfileData) => {
    if (!profileData || !map) return;

    console.log('Rendering elevation profile');
    // This would typically render a chart or profile view
    // For now, just log the data
    console.log('Profile data:', profileData);
  };

  // Helper functions for creating different overlay types
  const createRasterOverlay = (data: number[][], bbox: number[], colorScale: any) => {
    if (!window.atlas) return null;

    try {
      // This is a simplified implementation
      // In production, you would convert the data array to a proper image or use a tile service
      const imageLayer = new window.atlas.layer.ImageLayer({
        url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
        coordinates: [
          [bbox[0], bbox[3]], // NW
          [bbox[2], bbox[3]], // NE
          [bbox[2], bbox[1]], // SE
          [bbox[0], bbox[1]]  // SW
        ],
        opacity: 0.7
      });

      return imageLayer;
    } catch (error) {
      console.error('Error creating raster overlay:', error);
      return null;
    }
  };

  const createMobilityOverlay = (mobilityGrid: string[][], bbox: number[]) => {
    if (!window.atlas) return null;

    try {
      const imageLayer = new window.atlas.layer.ImageLayer({
        url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
        coordinates: [
          [bbox[0], bbox[3]], // NW
          [bbox[2], bbox[3]], // NE
          [bbox[2], bbox[1]], // SE
          [bbox[0], bbox[1]]  // SW
        ],
        opacity: 0.6
      });

      return imageLayer;
    } catch (error) {
      console.error('Error creating mobility overlay:', error);
      return null;
    }
  };

  const createLineOfSightLine = (observerPoint: number[], targetPoint: number[], isVisible: boolean) => {
    if (!window.atlas) return null;

    try {
      const lineData = new window.atlas.data.LineString([
        observerPoint,
        targetPoint
      ]);

      const dataSource = new window.atlas.source.DataSource();
      dataSource.add(lineData);

      const lineLayer = new window.atlas.layer.LineLayer(dataSource, undefined, {
        strokeColor: isVisible ? '#00FF00' : '#FF0000',
        strokeWidth: 3,
        strokeDashArray: isVisible ? [] : [5, 5]
      });

      return lineLayer;
    } catch (error) {
      console.error('Error creating line-of-sight line:', error);
      return null;
    }
  };

  const createObserverMarker = (observerPoint: number[]) => {
    if (!window.atlas) return null;

    try {
      const marker = new window.atlas.data.Point(observerPoint);
      const dataSource = new window.atlas.source.DataSource();
      dataSource.add(marker);

      const symbolLayer = new window.atlas.layer.SymbolLayer(dataSource, undefined, {
        iconOptions: {
          image: 'pin-blue',
          size: 1.5
        },
        textOptions: {
          textField: 'Observer',
          offset: [0, -2],
          color: '#000000'
        }
      });

      return symbolLayer;
    } catch (error) {
      console.error('Error creating observer marker:', error);
      return null;
    }
  };

  const createTargetMarker = (targetPoint: number[], isVisible: boolean) => {
    if (!window.atlas) return null;

    try {
      const marker = new window.atlas.data.Point(targetPoint);
      const dataSource = new window.atlas.source.DataSource();
      dataSource.add(marker);

      const symbolLayer = new window.atlas.layer.SymbolLayer(dataSource, undefined, {
        iconOptions: {
          image: isVisible ? 'pin-green' : 'pin-red',
          size: 1.5
        },
        textOptions: {
          textField: isVisible ? 'Target (Visible)' : 'Target (Hidden)',
          offset: [0, -2],
          color: '#000000'
        }
      });

      return symbolLayer;
    } catch (error) {
      console.error('Error creating target marker:', error);
      return null;
    }
  };

  // Utility functions
  const getTerrainColorScale = (visualizationType: string) => {
    const colorScales = {
      slope: {
        0: '#00FF00',    // Flat - Green
        15: '#FFFF00',   // Moderate - Yellow
        30: '#FF8000',   // Steep - Orange
        45: '#FF0000'    // Very steep - Red
      },
      aspect: {
        0: '#FF0000',    // North - Red
        90: '#00FF00',   // East - Green
        180: '#0000FF',  // South - Blue
        270: '#FFFF00'   // West - Yellow
      },
      elevation: {
        0: '#0000FF',    // Sea level - Blue
        500: '#00FF00',  // Low - Green
        1000: '#FFFF00', // Medium - Yellow
        2000: '#FF0000'  // High - Red
      }
    };

    return colorScales[visualizationType as keyof typeof colorScales] || colorScales.slope;
  };

  // Render controls and UI
  const renderGeointControls = () => {
    if (!showControls || !geointData) return null;

    return (
      <div className="geoint-controls" ref={overlayRef}>
        <div className="geoint-header">
          <h3>GEOINT Analysis</h3>
          <button 
            className="close-button"
            onClick={() => onVisibilityToggle(false)}
            title="Close GEOINT overlay"
          >
            ×
          </button>
        </div>
        
        <div className="geoint-content">
          <div className="analysis-info">
            <p><strong>Analysis Type:</strong> {geointData.analysis_type.replace('_', ' ').toUpperCase()}</p>
            
            {geointData.analysis_type === 'terrain_analysis' && (
              <div className="terrain-controls">
                <label>Visualization:</label>
                <select 
                  value={selectedVisualization} 
                  onChange={(e) => setSelectedVisualization(e.target.value)}
                >
                  <option value="slope">Slope Analysis</option>
                  <option value="aspect">Aspect (Direction)</option>
                  <option value="hillshade">Hillshade</option>
                  <option value="roughness">Terrain Roughness</option>
                </select>
              </div>
            )}
            
            {geointData.analysis_type === 'mobility_analysis' && geointData.mobility_analysis && (
              <div className="mobility-stats">
                <div className="stat-item">
                  <span className="go-indicator">*</span>
                  <span>Passable: {geointData.mobility_analysis.statistics.go_percentage.toFixed(1)}%</span>
                </div>
                <div className="stat-item">
                  <span className="slow-go-indicator">*</span>
                  <span>Slow: {geointData.mobility_analysis.statistics.slow_go_percentage.toFixed(1)}%</span>
                </div>
                <div className="stat-item">
                  <span className="no-go-indicator">*</span>
                  <span>Impassable: {geointData.mobility_analysis.statistics.no_go_percentage.toFixed(1)}%</span>
                </div>
              </div>
            )}
            
            {geointData.analysis_type === 'line_of_sight' && geointData.line_of_sight && (
              <div className="los-info">
                <p className={`visibility-status ${geointData.line_of_sight.is_visible ? 'visible' : 'blocked'}`}>
                  <strong>Status:</strong> {geointData.line_of_sight.is_visible ? 'VISIBLE' : 'BLOCKED'}
                </p>
                {geointData.line_of_sight.visibility_angle && (
                  <p><strong>Angle:</strong> {geointData.line_of_sight.visibility_angle.toFixed(2)}°</p>
                )}
                {geointData.line_of_sight.obstruction && (
                  <p><strong>Obstruction:</strong> {geointData.line_of_sight.obstruction.distance_from_observer.toFixed(0)}m from observer</p>
                )}
              </div>
            )}
          </div>
          
          <div className="geoint-legend">
            {renderGeointLegend()}
          </div>
        </div>
      </div>
    );
  };

  const renderGeointLegend = () => {
    if (!geointData) return null;

    switch (geointData.analysis_type) {
      case 'terrain_analysis':
        return (
          <div className="terrain-legend">
            <h4>{selectedVisualization.toUpperCase()} Legend</h4>
            <div className="legend-items">
              {selectedVisualization === 'slope' && (
                <>
                  <div className="legend-item"><span className="color-box" style={{backgroundColor: '#00FF00'}}></span>Flat (0-15°)</div>
                  <div className="legend-item"><span className="color-box" style={{backgroundColor: '#FFFF00'}}></span>Moderate (15-30°)</div>
                  <div className="legend-item"><span className="color-box" style={{backgroundColor: '#FF8000'}}></span>Steep (30-45°)</div>
                  <div className="legend-item"><span className="color-box" style={{backgroundColor: '#FF0000'}}></span>Very Steep (45°+)</div>
                </>
              )}
            </div>
          </div>
        );
        
      case 'mobility_analysis':
        return (
          <div className="mobility-legend">
            <h4>MOBILITY Legend</h4>
            <div className="legend-items">
              <div className="legend-item"><span className="color-box go-color"></span>Passable</div>
              <div className="legend-item"><span className="color-box slow-go-color"></span>Reduced Speed</div>
              <div className="legend-item"><span className="color-box no-go-color"></span>Impassable</div>
            </div>
          </div>
        );
        
      default:
        return null;
    }
  };

  return (
    <>
      {isVisible && renderGeointControls()}
    </>
  );
};

export default GeointOverlay;