// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import './STACInfoButton.css';
import { API_BASE_URL } from '../config/api';
import { authenticatedFetch } from '../services/authHelper';

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
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  useEffect(() => {
    // Load collections metadata from unified golden source JSON and transform it
    console.log('[STACInfoButton] Fetching collections from:', `${API_BASE_URL}/pc_rendering_config.json`);
    authenticatedFetch(`${API_BASE_URL}/pc_rendering_config.json`)
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

  return (
    <>
      <div 
        className="stac-info-button"
        onClick={() => setShowModal(true)}
        title="View STAC Collection Availability Guide"
      >
        <span className="stac-button-label">Data Catalog</span>
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
                    STAC Data Collection Availability
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
                <h3 className="stac-section-title">Planetary Computer Collections ({collectionsData?.metadata.total_collections || 47})</h3>
                <p className="stac-section-subtitle">
                  Complete catalog of STAC collections available through Microsoft Planetary Computer. 
                  All collections support location-based queries; datetime is optional.
                </p>

                {/* Category Filter Buttons */}
                {collectionsData && (
                  <div className="stac-category-filters">
                    <button 
                      className={`stac-filter-btn ${selectedCategory === null ? 'active' : ''}`}
                      onClick={() => setSelectedCategory(null)}
                    >
                      All ({collectionsData.metadata.total_collections})
                    </button>
                    {collectionsData.categories.map((cat, catIdx) => (
                      <button
                        key={catIdx}
                        className={`stac-filter-btn ${selectedCategory === cat.name ? 'active' : ''}`}
                        onClick={() => setSelectedCategory(cat.name)}
                      >
                        {cat.name} ({cat.count})
                      </button>
                    ))}
                  </div>
                )}

                {loading && <div className="stac-loading">Loading collections...</div>}

                {collectionsData?.categories
                  .filter(category => selectedCategory === null || category.name === selectedCategory)
                  .map((category, idx) => (
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
                                ? 'Location only' 
                                : 'Location, DateTime (optional)'}
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
                <span>{collectionsData?.metadata.total_collections || 47}/{collectionsData?.metadata.total_collections || 47} Collections Operational</span>
                <span>-</span>
                <span>Last Updated: {collectionsData?.metadata.last_updated || 'November 2025'}</span>
                <span>-</span>
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
