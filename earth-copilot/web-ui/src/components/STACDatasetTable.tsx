// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import './STACInfoButton.css';
import { API_BASE_URL } from '../config/api';

interface CollectionData {
  collection_id: string;
  category: string;
  description: string;
  render_params?: any;
  assets?: string[];
  rescale?: number[] | string | null;
  colormap?: string | null;
  resampling?: string;
  color_formula?: string | null;
  expression?: string | null;
  tile_scale?: number;
  render_type?: string;
  nodata?: number | null;
}

interface RenderingConfig {
  metadata: {
    total_collections: number;
    last_updated: string;
    source: string;
  };
  collections: Record<string, CollectionData>;
}

const STACDatasetTable: React.FC = () => {
  const [showModal, setShowModal] = useState(false);
  const [datasets, setDatasets] = useState<CollectionData[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  useEffect(() => {
    // Load comprehensive dataset table from unified rendering config
    console.log('[STACDatasetTable] Fetching collections from:', `${API_BASE_URL}/pc_rendering_config.json`);
    fetch(`${API_BASE_URL}/pc_rendering_config.json`)
      .then(response => {
        console.log('[STACDatasetTable] Response status:', response.status);
        return response.json();
      })
      .then((config: RenderingConfig) => {
        console.log('[STACDatasetTable] Received config:', {
          hasCollections: !!config.collections,
          collectionCount: Object.keys(config.collections || {}).length
        });

        // Convert collections object to array with defensive checks
        const collectionsArray = Object.values(config.collections || {}).filter(c => {
          if (!c || !c.collection_id) {
            console.warn('[STACDatasetTable] Invalid collection found:', c);
            return false;
          }
          if (!c.description || typeof c.description !== 'string') {
            console.warn('[STACDatasetTable] Collection missing description:', c.collection_id);
            c.description = 'No description available';
          }
          return true;
        });

        console.log('[STACDatasetTable] Loaded collections:', collectionsArray.length);
        setDatasets(collectionsArray);
        setLoading(false);
      })
      .catch(error => {
        console.error('[STACDatasetTable] Error loading PC rendering config:', error);
        setLoading(false);
      });
  }, []);

  // Get unique categories
  const categories = ['ALL', ...Array.from(new Set(datasets.map(d => d.category)))].sort();

  // Filter datasets based on search and category
  const filteredDatasets = datasets.filter(dataset => {
    const assetsStr = dataset.assets?.join(', ') || '';
    const matchesSearch = searchTerm === '' || 
      dataset.collection_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      dataset.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      assetsStr.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesCategory = selectedCategory === 'ALL' || dataset.category === selectedCategory;
    
    return matchesSearch && matchesCategory;
  });

  // Group by category for display
  const groupedDatasets = filteredDatasets.reduce((acc, dataset) => {
    if (!acc[dataset.category]) {
      acc[dataset.category] = [];
    }
    acc[dataset.category].push(dataset);
    return acc;
  }, {} as Record<string, CollectionData[]>);

  return (
    <>
      <div
        onClick={() => setShowModal(true)}
        className="stac-info-button"
        title="View STAC Collections Reference"
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
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
          <polyline points="10 9 9 9 8 9"></polyline>
        </svg>
        <span className="stac-button-label">STAC Collections</span>
      </div>

      {showModal && (
        <div className="stac-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="stac-modal-content-large" onClick={(e) => e.stopPropagation()}>
            <div className="stac-modal-header">
              <h2>�️ STAC Data Collection Availability</h2>
              <button 
                onClick={() => setShowModal(false)} 
                className="stac-modal-close"
                title="Close"
              >
                ×
              </button>
            </div>

            <div className="stac-modal-body">
              {loading ? (
                <div style={{ textAlign: 'center', padding: '40px' }}>
                  <p>Loading dataset information...</p>
                </div>
              ) : (
                <>
                  <div className="stac-filters">
                    <div className="stac-search-box">
                      <input
                        type="text"
                        placeholder="Search collections, descriptions, or assets..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="stac-search-input"
                      />
                    </div>
                    
                    <div className="stac-category-filter">
                      <label>Category:</label>
                      <select 
                        value={selectedCategory} 
                        onChange={(e) => setSelectedCategory(e.target.value)}
                        className="stac-category-select"
                      >
                        {categories.map(cat => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="stac-summary">
                    <p>
                      <strong>{filteredDatasets.length}</strong> collections available
                      {searchTerm && ` matching "${searchTerm}"`}
                      {selectedCategory !== 'ALL' && ` in ${selectedCategory}`}
                    </p>
                  </div>

                  <div className="stac-table-container">
                    {Object.entries(groupedDatasets).map(([category, categoryDatasets]) => (
                      <div key={category} className="stac-category-section">
                        <h3 className="stac-category-title">{category}</h3>
                        
                        <table className="stac-collections-table">
                          <thead>
                            <tr>
                              <th>Collection ID</th>
                              <th>Description</th>
                              <th>Temporal Range</th>
                              <th>DateTime</th>
                              <th>Location</th>
                              <th>Colormap</th>
                              <th>Assets</th>
                              <th>Zoom</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(categoryDatasets as CollectionData[]).map(dataset => {
                              // Defensive null check
                              if (!dataset || !dataset.collection_id) {
                                return null;
                              }

                              return (
                                <tr key={dataset.collection_id}>
                                  <td className="collection-id-cell">
                                    <code>{dataset.collection_id}</code>
                                  </td>
                                  <td className="description-cell" title={dataset.description || 'No description'}>
                                    {dataset.description && typeof dataset.description === 'string' && dataset.description.length > 200 
                                      ? dataset.description.substring(0, 200) + '...' 
                                      : dataset.description || 'No description available'}
                                  </td>
                                  <td className="temporal-cell">Varies by dataset</td>
                                  <td className="requirement-cell">✅</td>
                                  <td className="requirement-cell">✅</td>
                                  <td className="colormap-cell">
                                    <code>{dataset.colormap || 'N/A'}</code>
                                  </td>
                                  <td className="assets-cell">{dataset.assets?.join(', ') || 'N/A'}</td>
                                  <td className="zoom-cell">1-14</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>

                  {filteredDatasets.length === 0 && (
                    <div className="stac-no-results">
                      <p>No collections match your search criteria.</p>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="stac-modal-footer">
              <p className="stac-footer-text">
                📚 <strong>{datasets.length}</strong> total collections | 
                Data from <a href="https://planetarycomputer.microsoft.com/" target="_blank" rel="noopener noreferrer">Planetary Computer</a> STAC API
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default STACDatasetTable;
