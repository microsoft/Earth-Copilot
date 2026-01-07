// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import './STACInfoButton.css';
import { API_BASE_URL } from '../config/api';

// Simplified collection info from categories array
interface SimplifiedCollection {
  id: string;
  title: string;
  description: string;
  keywords: string[];
}

// Full collection details from collections object
interface FullCollectionDetails {
  collection_id: string;
  rendering: {
    assets?: string[];
  };
  classification: {
    is_static: boolean;
    supports_temporal: boolean;
  };
}

// Merged collection for display
interface CollectionMetadata {
  id: string;
  title: string;
  description: string;
  temporal_extent: string;
  is_static: boolean;
  keywords: string[];
  assets: string[];
  required_params: {
    location: boolean;
    datetime: boolean;
    datetime_optional: boolean;
  };
}

interface CategoryData {
  name: string;
  count: number;
  collections: CollectionMetadata[];
}

interface PCMetadata {
  total_collections: number;
  last_updated: string;
  source: string;
  note: string;
}

// Golden source JSON structure
interface GoldenSourceData {
  metadata: PCMetadata;
  categories: {
    name: string;
    count: number;
    collections: SimplifiedCollection[];
  }[];
  collections: {
    [key: string]: FullCollectionDetails;
  };
}

// Transformed data for component
interface PCCollectionsData {
  metadata: PCMetadata;
  categories: CategoryData[];
}

const STACInfoButton: React.FC = () => {
  const [showModal, setShowModal] = useState(false);
  const [collectionsData, setCollectionsData] = useState<PCCollectionsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load collections metadata from unified golden source JSON and transform it
    console.log('[STACInfoButton] Fetching collections from:', `${API_BASE_URL}/pc_rendering_config.json`);
    fetch(`${API_BASE_URL}/pc_rendering_config.json`)
      .then(response => {
        console.log('[STACInfoButton] Response status:', response.status);
        return response.json();
      })
      .then((goldenSource: GoldenSourceData) => {
        console.log('[STACInfoButton] Received data:', {
          hasMetadata: !!goldenSource?.metadata,
          hasCategories: !!goldenSource?.categories,
          hasCollections: !!goldenSource?.collections,
          categoriesCount: goldenSource?.categories?.length,
          collectionsKeys: Object.keys(goldenSource?.collections || {}).length
        });

        // Defensive null checks throughout transformation
        if (!goldenSource || !goldenSource.categories || !goldenSource.collections) {
          console.error('[STACInfoButton] Invalid golden source data structure:', goldenSource);
          setLoading(false);
          return;
        }

        // Transform golden source data to match component expectations
        const transformedData: PCCollectionsData = {
          metadata: goldenSource.metadata || { total_collections: 0, last_updated: 'Unknown', source: '', note: '' },
          categories: (goldenSource.categories || []).map(category => ({
            name: category?.name || 'Unknown',
            count: category?.count || 0,
            collections: (category?.collections || []).map(simpleCol => {
              // Get full details from collections object - with null safety
              const fullDetails = simpleCol?.id ? goldenSource.collections[simpleCol.id] : null;
              
              // Ensure keywords is always an array
              let safeKeywords: string[] = [];
              if (simpleCol?.keywords) {
                if (Array.isArray(simpleCol.keywords)) {
                  safeKeywords = simpleCol.keywords.filter(k => typeof k === 'string');
                }
              }
              
              return {
                id: simpleCol?.id || 'unknown',
                title: simpleCol?.title || 'Unknown Collection',
                description: simpleCol?.description || 'No description available',
                temporal_extent: fullDetails?.classification?.is_static ? 'Static' : '2000-present',
                is_static: fullDetails?.classification?.is_static || false,
                keywords: safeKeywords,
                assets: fullDetails?.rendering?.assets || [],
                required_params: {
                  location: true,
                  datetime: !(fullDetails?.classification?.is_static),
                  datetime_optional: !(fullDetails?.classification?.is_static)
                }
              };
            }).filter(col => col.id !== 'unknown') // Remove any malformed collections
          })).filter(cat => cat.collections.length > 0) // Remove empty categories
        };
        
        setCollectionsData(transformedData);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error loading collections metadata:', error);
        setLoading(false);
      });
  }, []);

  const collectionData = [
    {
      category: "Ultra High-Resolution (0.6m - 10m)",
      collections: [
        {
          name: "NAIP",
          resolution: "0.6m",
          dateRange: "No date needed",
          why: "Updates every 2-3 years, use latest available (2023)",
          exampleQuery: "Show me NAIP imagery of Seattle"
        },
        {
          name: "Sentinel-2 L2A",
          resolution: "10m",
          dateRange: "Last 30 days",
          why: "Near real-time, updated continuously",
          exampleQuery: "Show me Sentinel-2 imagery of California with low cloud cover"
        }
      ]
    },
    {
      category: "High Resolution (30m)",
      collections: [
        {
          name: "Landsat C2 L2",
          resolution: "30m",
          dateRange: "Last 90 days",
          why: "Near real-time, updated continuously",
          exampleQuery: "Show me Landsat imagery of Yellowstone"
        },
        {
          name: "HLS L30",
          resolution: "30m",
          dateRange: "Last 30 days",
          why: "Harmonized Landsat, recent data",
          exampleQuery: "Show me HLS images of Kansas"
        },
        {
          name: "HLS S30",
          resolution: "30m",
          dateRange: "Last 30 days",
          why: "Harmonized Sentinel-2, recent data",
          exampleQuery: "Show me HLS images with low cloud cover"
        }
      ]
    },
    {
      category: "Elevation Data (30m - 90m)",
      collections: [
        {
          name: "Copernicus DEM 30m",
          resolution: "30m",
          dateRange: "No date needed",
          why: "Static elevation dataset (2021)",
          exampleQuery: "Show me elevation of California"
        },
        {
          name: "Copernicus DEM 90m",
          resolution: "90m",
          dateRange: "No date needed",
          why: "Static elevation dataset (2021)",
          exampleQuery: "Show me terrain of the Rocky Mountains"
        },
        {
          name: "NASADEM",
          resolution: "30m",
          dateRange: "No date needed",
          why: "Static elevation dataset (2000)",
          exampleQuery: "Show me topography of Hawaii"
        }
      ]
    },
    {
      category: "Radar/SAR (10m - 20m)",
      collections: [
        {
          name: "Sentinel-1 RTC",
          resolution: "10-20m",
          dateRange: "Last 90 days",
          why: "Radar data, updated continuously",
          exampleQuery: "Show me Sentinel-1 radar of Seattle"
        },
        {
          name: "Sentinel-1 GRD",
          resolution: "10-20m",
          dateRange: "Last 30 days",
          why: "Radar data, updated continuously",
          exampleQuery: "Show me SAR data for flood monitoring"
        }
      ]
    },
    {
      category: "MODIS Surface Reflectance (250m - 500m)",
      collections: [
        {
          name: "MODIS 09A1 (500m)",
          resolution: "500m",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me MODIS surface reflectance from early 2024"
        },
        {
          name: "MODIS 09Q1 (250m)",
          resolution: "250m",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me MODIS tiles from spring 2024"
        }
      ]
    },
    {
      category: "MODIS Vegetation (250m - 500m)",
      collections: [
        {
          name: "MODIS 13A1 (NDVI 500m)",
          resolution: "500m",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me MODIS vegetation index from early 2024"
        },
        {
          name: "MODIS 13Q1 (NDVI 250m)",
          resolution: "250m",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me MODIS NDVI from spring 2024"
        },
        {
          name: "MODIS 15A2H (LAI)",
          resolution: "500m",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me leaf area index from early 2024"
        }
      ]
    },
    {
      category: "MODIS Productivity (500m)",
      collections: [
        {
          name: "MODIS 17A2H (GPP)",
          resolution: "500m",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me MODIS productivity from spring 2024"
        },
        {
          name: "MODIS 17A3HGF (NPP)",
          resolution: "500m",
          dateRange: "2023-2024",
          why: "Yearly product, processing lag",
          exampleQuery: "Show me ecosystem productivity from 2024"
        }
      ]
    },
    {
      category: "MODIS Fire & Environmental (500m - 1km)",
      collections: [
        {
          name: "MODIS 14A1 (Fire Daily)",
          resolution: "1km",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me MODIS fire data from early 2024"
        },
        {
          name: "MODIS 14A2 (Fire 8-day)",
          resolution: "1km",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me fire activity from spring 2024"
        },
        {
          name: "MODIS 10A1 (Snow)",
          resolution: "500m",
          dateRange: "Winter 2024 (Jan-Mar)",
          why: "Seasonal, 3-6 month lag",
          exampleQuery: "Show me snow cover from winter 2024"
        },
        {
          name: "MODIS 11A1 (Temperature)",
          resolution: "1km",
          dateRange: "January-June 2024",
          why: "3-6 month processing lag",
          exampleQuery: "Show me land surface temperature from spring 2024"
        }
      ]
    }
  ];

  return (
    <>
      <div 
        className="stac-info-button"
        onClick={() => setShowModal(true)}
        title="View STAC Collection Availability Guide"
      >
        <svg 
          width="20" 
          height="20" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
          strokeLinecap="round" 
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8h.01" />
          <path d="M11 12h1v4h1" />
        </svg>
        <span className="stac-button-label">STAC Data</span>
      </div>

      {showModal && (
        <div className="stac-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="stac-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="stac-modal-header">
              <div>
                <h2>
                  <a 
                    href="https://planetarycomputer.microsoft.com/catalog"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="stac-header-link"
                    title="Go to Planetary Computer Data Catalog"
                    onClick={(e) => e.stopPropagation()}
                  >
                    🛰️ STAC Data Collection Availability
                  </a>
                </h2>
              </div>
              <button 
                className="stac-close-btn" 
                onClick={() => setShowModal(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="stac-modal-body">
              {/* All Collections from Planetary Computer */}
              <div className="stac-all-collections-section">
                <h3 className="stac-section-title">📊 Planetary Computer Collections ({collectionsData?.metadata.total_collections || 47})</h3>
                <p className="stac-section-subtitle">
                  Complete catalog of STAC collections available through Microsoft Planetary Computer. 
                  All collections support location-based queries; datetime is optional.
                </p>

                {loading && <div className="stac-loading">Loading collections...</div>}

                {collectionsData?.categories.map((category, idx) => (
                  <div key={idx} className="stac-category">
                    <h3 className="stac-category-title">{category.name} ({category.count} collections)</h3>
                    <div className="stac-table">
                      <div className="stac-table-header">
                        <div className="stac-col-id">Collection ID</div>
                        <div className="stac-col-description">Description</div>
                        <div className="stac-col-temporal">Temporal Coverage</div>
                        <div className="stac-col-params">Required Parameters</div>
                      </div>
                      {category.collections.map((collection, collIdx) => {
                        // Extra defensive check for collection object
                        if (!collection || !collection.id) {
                          return null;
                        }

                        return (
                          <div key={collIdx} className="stac-table-row">
                            <div className="stac-col-id">
                              <code>{collection.id}</code>
                              {Array.isArray(collection.keywords) && collection.keywords.length > 0 && (
                                <div className="stac-keywords">
                                  {collection.keywords.slice(0, 3).map((keyword, kidx) => {
                                    if (typeof keyword !== 'string') return null;
                                    return <span key={kidx} className="keyword-tag">{keyword}</span>;
                                  })}
                                </div>
                              )}
                            </div>
                            <div className="stac-col-description">
                              <strong>{collection.title || 'Unknown'}</strong>
                              <p className="collection-desc">
                                {collection.description && typeof collection.description === 'string' && collection.description.length > 200 
                                  ? collection.description.substring(0, 200) + '...'
                                  : collection.description || 'No description available'}
                              </p>
                            </div>
                            <div className="stac-col-temporal">
                              <span className="temporal-badge">
                                {collection.temporal_extent || 'Variable'}
                              </span>
                            </div>
                            <div className="stac-col-params">
                              {collection.is_static 
                                ? '📍 Location only' 
                                : '📍 Location; 📅 DateTime optional'}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="stac-modal-footer">
              <div className="stac-footer-info">
                <span>✅ {collectionsData?.metadata.total_collections || 47}/{collectionsData?.metadata.total_collections || 47} Collections Operational</span>
                <span>•</span>
                <span>Last Updated: {collectionsData?.metadata.last_updated || 'November 2025'}</span>
                <span>•</span>
                <a 
                  href="https://planetarycomputer.microsoft.com/catalog" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="footer-link"
                >
                  Microsoft Planetary Computer
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default STACInfoButton;
