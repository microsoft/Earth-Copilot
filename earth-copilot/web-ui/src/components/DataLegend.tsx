// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useEffect, useState } from 'react';

interface DataLegendProps {
  collection: string;
  isVisible: boolean;
  min?: number;
  max?: number;
}

interface ColormapData {
  colormap_name: string;
  css_gradient: string;
  success: boolean;
}

const DataLegend: React.FC<DataLegendProps> = ({ 
  collection, 
  isVisible, 
  min = -100, 
  max = 8848 // Mt. Everest height
}) => {
  const [colormapData, setColormapData] = useState<ColormapData | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch colormap from API when collection changes
  useEffect(() => {
    const fetchColormap = async () => {
      try {
        setLoading(true);
        
        // Skip colormap fetch for RGB optical collections (they don't need colormaps)
        const rgbCollections = [
          'sentinel-2-l2a',
          'sentinel-2-l1c', 
          'landsat-c2-l2',
          'landsat-8-c2-l2',
          'landsat-9-c2-l2',
          'hls',
          'naip'
        ];
        
        if (rgbCollections.some(rgb => collection.toLowerCase().includes(rgb))) {
          console.log(`ℹ️ Skipping colormap fetch for RGB collection '${collection}' (not needed for optical imagery)`);
          setColormapData(null);
          setLoading(false);
          return; // Don't fetch colormap for RGB collections
        }
        
        const response = await fetch(`/api/colormaps/collection/${collection}`);
        const data = await response.json();
        
        if (data.success && data.css_gradient) {
          setColormapData({
            colormap_name: data.colormap_name,
            css_gradient: data.css_gradient,
            success: true
          });
          console.log(`Loaded TiTiler colormap '${data.colormap_name}' for collection '${collection}'`);
        } else {
          console.warn(`Failed to load colormap for '${collection}', using fallback`);
          setColormapData(null);
        }
      } catch (error) {
        console.error(`Error fetching colormap for '${collection}':`, error);
        setColormapData(null);
      } finally {
        setLoading(false);
      }
    };

    if (isVisible && collection) {
      fetchColormap();
    }
  }, [collection, isVisible]);

  if (!isVisible) return null;
  if (loading) {
    return (
      <div className="absolute bottom-8 left-4 z-[500] bg-white rounded-lg shadow-lg p-4 min-w-[200px]">
        <div className="text-sm text-gray-600">Loading colormap...</div>
      </div>
    );
  }

  // Define gradient colors and scales based on data type
  const getDataGradient = (collection: string) => {
    const lowerCollection = collection.toLowerCase();
    
    // [+] NEW: If we have TiTiler colormap data, use it!
    if (colormapData && colormapData.css_gradient) {
      // For DEM/elevation data
      if (lowerCollection.includes('dem') || lowerCollection.includes('elevation') || lowerCollection.includes('srtm') || lowerCollection.includes('cop-dem')) {
        return {
          title: 'Terrain Elevation',
          gradientColors: colormapData.css_gradient,
          labels: [
            { position: 0, value: `${min}m`, description: min < 0 ? 'Below Sea Level' : 'Valleys' },
            { position: 25, value: `${Math.round(min + (max - min) * 0.25)}m`, description: 'Foothills' },
            { position: 50, value: `${Math.round(min + (max - min) * 0.5)}m`, description: 'Mountains' },
            { position: 75, value: `${Math.round(min + (max - min) * 0.75)}m`, description: 'High Peaks' },
            { position: 100, value: `${max}m`, description: max > 4000 ? 'Snow/Ice' : 'Summit' }
          ],
          isTiTiler: true  // Flag to show we're using TiTiler colormap
        };
      }
      
      // For vegetation indices
      if (lowerCollection.includes('ndvi') || lowerCollection.includes('13q1') || lowerCollection.includes('13a1')) {
        return {
          title: `Vegetation Index (${colormapData.colormap_name})`,
          gradientColors: colormapData.css_gradient,
          labels: [
            { position: 0, value: '-1.0', description: 'Water/No Veg' },
            { position: 25, value: '-0.5', description: 'Bare Soil' },
            { position: 50, value: '0.0', description: 'Sparse Veg' },
            { position: 75, value: '+0.5', description: 'Moderate Veg' },
            { position: 100, value: '+1.0', description: 'Dense Veg' }
          ],
          isTiTiler: true
        };
      }
    }
    
    // Elevation/Terrain Data (FALLBACK - only shown if TiTiler colormap fetch fails)
    if (lowerCollection.includes('dem') || lowerCollection.includes('elevation') || lowerCollection.includes('srtm') || lowerCollection.includes('cop-dem')) {
      return {
        title: 'Terrain Elevation',
        // Match the matplotlib 'terrain' colormap that TiTiler uses: Green (valleys) -> Yellow/Tan -> Brown (mountains) -> White (peaks)
        gradientColors: 'linear-gradient(to top, #2E7D32 0%, #4DB560 15%, #8BC34A 30%, #D4B86A 45%, #C49A6C 60%, #8B6F47 75%, #6D4C3D 88%, #FFFFFF 100%)',
        labels: [
          { position: 0, value: 'Low', description: 'Valleys' },
          { position: 25, value: 'Low-Mid', description: 'Foothills' },
          { position: 50, value: 'Mid', description: 'Mountains' },
          { position: 75, value: 'High', description: 'High Peaks' },
          { position: 100, value: 'Highest', description: 'Snow/Ice' }
        ]
      };
    }
    
    // SAR Data
    if (lowerCollection.includes('sentinel-1') || lowerCollection.includes('sar')) {
      return {
        title: 'SAR Backscatter',
        gradientColors: 'linear-gradient(to top, #000000 0%, #333333 25%, #666666 50%, #999999 75%, #FFFFFF 100%)',
        labels: [
          { position: 0, value: '-25 dB', description: 'Water/Smooth' },
          { position: 25, value: '-20 dB', description: 'Calm Water' },
          { position: 50, value: '-15 dB', description: 'Vegetation' },
          { position: 75, value: '-10 dB', description: 'Urban/Forest' },
          { position: 100, value: '0 dB', description: 'Metal/Buildings' }
        ]
      };
    }
    
    // Fire/Thermal Data
    if (lowerCollection.includes('fire') || lowerCollection.includes('thermal') || lowerCollection.includes('modis-fire') || lowerCollection.includes('goes-glm') || lowerCollection.includes('modis-14a') || lowerCollection.includes('modis-64a')) {
      return {
        title: 'Fire Intensity',
        gradientColors: 'linear-gradient(to top, #000080 0%, #0000FF 20%, #FFFF00 40%, #FF8000 70%, #FF0000 100%)',
        labels: [
          { position: 0, value: 'No Fire', description: 'Normal' },
          { position: 20, value: 'Low', description: 'Heat Source' },
          { position: 40, value: 'Medium', description: 'Small Fire' },
          { position: 70, value: 'High', description: 'Active Fire' },
          { position: 100, value: 'Extreme', description: 'Intense Fire' }
        ]
      };
    }
    
    // Leaf Area Index
    if (lowerCollection.includes('15a2h') || lowerCollection.includes('lai')) {
      return {
        title: 'Leaf Area Index',
        gradientColors: 'linear-gradient(to top, #440154 0%, #414487 25%, #2a788e 50%, #22a884 75%, #7ad151 100%)',
        labels: [
          { position: 0, value: '0.0', description: 'No Vegetation' },
          { position: 25, value: '2.0', description: 'Sparse Leaves' },
          { position: 50, value: '4.0', description: 'Moderate Density' },
          { position: 75, value: '6.0', description: 'Dense Canopy' },
          { position: 100, value: '10.0', description: 'Very Dense' }
        ]
      };
    }

    // Gross Primary Productivity
    if (lowerCollection.includes('17a2h') || lowerCollection.includes('gpp')) {
      return {
        title: 'Gross Primary Productivity',
        gradientColors: 'linear-gradient(to top, #0d0887 0%, #7e03a8 25%, #cc4778 50%, #f89441 75%, #f0f921 100%)',
        labels: [
          { position: 0, value: '0', description: 'No Productivity' },
          { position: 25, value: '7500', description: 'Low' },
          { position: 50, value: '15000', description: 'Moderate' },
          { position: 75, value: '22500', description: 'High' },
          { position: 100, value: '30000', description: 'Very High' }
        ]
      };
    }

    // Net Primary Productivity
    if (lowerCollection.includes('17a3h') || lowerCollection.includes('npp')) {
      return {
        title: 'Net Primary Productivity',
        gradientColors: 'linear-gradient(to top, #0d0887 0%, #7e03a8 25%, #cc4778 50%, #f89441 75%, #f0f921 100%)',
        labels: [
          { position: 0, value: '0', description: 'No Productivity' },
          { position: 25, value: '8175', description: 'Low' },
          { position: 50, value: '16350', description: 'Moderate' },
          { position: 75, value: '24525', description: 'High' },
          { position: 100, value: '32700', description: 'Very High' }
        ]
      };
    }

    // Vegetation Indices (NDVI, etc.)
    if (lowerCollection.includes('ndvi') || lowerCollection.includes('vegetation') || lowerCollection.includes('modis-ndvi')) {
      return {
        title: 'Vegetation Index',
        gradientColors: 'linear-gradient(to top, #8B4513 0%, #D2B48C 20%, #FFFF99 40%, #90EE90 70%, #006400 100%)',
        labels: [
          { position: 0, value: '-1.0', description: 'Water/Rock' },
          { position: 20, value: '-0.1', description: 'Bare Soil' },
          { position: 40, value: '0.2', description: 'Sparse Veg' },
          { position: 70, value: '0.5', description: 'Moderate Veg' },
          { position: 100, value: '1.0', description: 'Dense Veg' }
        ]
      };
    }
    
    // Snow Cover
    if (lowerCollection.includes('snow') || lowerCollection.includes('modis-snow')) {
      return {
        title: 'Snow Cover',
        gradientColors: 'linear-gradient(to top, #8B4513 0%, #32CD32 25%, #87CEEB 50%, #E0E0E0 75%, #FFFFFF 100%)',
        labels: [
          { position: 0, value: '0%', description: 'No Snow' },
          { position: 25, value: '25%', description: 'Partial' },
          { position: 50, value: '50%', description: 'Mixed' },
          { position: 75, value: '75%', description: 'Heavy' },
          { position: 100, value: '100%', description: 'Full Cover' }
        ]
      };
    }
    
    // Ocean/Sea Surface Temperature
    if (lowerCollection.includes('ocean') || lowerCollection.includes('sst') || lowerCollection.includes('sea-surface')) {
      return {
        title: 'Sea Surface Temp',
        gradientColors: 'linear-gradient(to top, #000080 0%, #0066CC 25%, #00CCCC 50%, #FFFF00 75%, #FF0000 100%)',
        labels: [
          { position: 0, value: '-2°C', description: 'Ice Cold' },
          { position: 25, value: '10°C', description: 'Cold' },
          { position: 50, value: '20°C', description: 'Moderate' },
          { position: 75, value: '25°C', description: 'Warm' },
          { position: 100, value: '30°C+', description: 'Hot' }
        ]
      };
    }
    
    // Climate/Weather Data
    if (lowerCollection.includes('climate') || lowerCollection.includes('precipitation') || lowerCollection.includes('temperature')) {
      return {
        title: 'Climate Data',
        gradientColors: 'linear-gradient(to top, #800080 0%, #0000FF 25%, #00FFFF 50%, #FFFF00 75%, #FF0000 100%)',
        labels: [
          { position: 0, value: 'Very Low', description: 'Minimal' },
          { position: 25, value: 'Low', description: 'Below Avg' },
          { position: 50, value: 'Medium', description: 'Average' },
          { position: 75, value: 'High', description: 'Above Avg' },
          { position: 100, value: 'Very High', description: 'Extreme' }
        ]
      };
    }
    
    // Return null for unknown collections - no hardcoded legend
    return null;
  };

  const gradient = getDataGradient(collection);

  // Don't show legend if no gradient data available
  if (!gradient) {
    return null;
  }

  return (
    <div style={{
      position: 'absolute',
      bottom: '20px',
      right: '20px',
      background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.85) 0%, rgba(248, 250, 252, 0.75) 50%, rgba(241, 245, 249, 0.85) 100%)',
      padding: '12px',
      borderRadius: '8px',
      boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
      backdropFilter: 'blur(8px)',
      minWidth: '180px',
      fontSize: '12px',
      zIndex: 10, // Lowered from 500 to 10 - only needs to be above map tiles, not modals
      border: '1px solid rgba(0, 0, 0, 0.1)'
    }}>
      <div style={{
        fontWeight: '600',
        marginBottom: '12px',
        fontSize: '13px',
        color: '#374151',
        textAlign: 'center',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        letterSpacing: '0.025em'
      }}>
        {gradient.title}
        {gradient.isTiTiler && (
          <div style={{
            fontSize: '9px',
            fontWeight: '400',
            color: '#10b981',
            marginTop: '4px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '4px'
          }}>
            <span>✓</span>
            <span>TiTiler Colormap</span>
          </div>
        )}
      </div>
      
      {/* Gradient Bar */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: '8px',
        marginBottom: '8px' 
      }}>
        <div style={{
          width: '20px',
          height: '120px',
          background: gradient.gradientColors,
          border: '1px solid rgba(0, 0, 0, 0.3)',
          borderRadius: '3px',
          position: 'relative'
        }}>
          {/* Tick marks on the gradient */}
          {gradient.labels.map((label, index) => (
            <div key={index} style={{
              position: 'absolute',
              left: '22px',
              bottom: `${label.position}%`,
              transform: 'translateY(50%)',
              width: '4px',
              height: '1px',
              backgroundColor: '#333',
            }} />
          ))}
        </div>
        
        {/* Labels */}
        <div style={{ position: 'relative', height: '120px', flex: 1 }}>
          {gradient.labels.map((label, index) => (
            <div key={index} style={{
              position: 'absolute',
              bottom: `${label.position}%`,
              transform: 'translateY(50%)',
              fontSize: '11px',
              color: '#374151',
              whiteSpace: 'nowrap',
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: '6px',
              background: 'rgba(255, 255, 255, 0.95)',
              padding: '3px 6px',
              borderRadius: '4px',
              border: '1px solid rgba(0, 0, 0, 0.08)',
              boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
              fontFamily: 'system-ui, -apple-system, sans-serif'
            }}>
              <span style={{ fontWeight: '600', color: '#111827' }}>{label.value}</span>
              <span style={{ fontSize: '10px', color: '#6B7280' }}>{label.description}</span>
            </div>
          ))}
        </div>
      </div>
      
    </div>
  );
};

export default DataLegend;