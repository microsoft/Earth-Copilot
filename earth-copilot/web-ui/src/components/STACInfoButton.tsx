// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import './STACInfoButton.css';

const STACInfoButton: React.FC = () => {
  const [showModal, setShowModal] = useState(false);

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
              <div className="stac-featured-section">
                <h3 className="featured-title">⭐ Featured Collections</h3>
                <p className="featured-subtitle">
                  Production-ready, high-priority datasets optimized for Earth Copilot. Different satellite collections have different update schedules and data availability. Use the right date ranges in your queries to ensure you get results.
                </p>

                <div className="featured-collections-table">
                  <div className="featured-table-row">
                    <div className="featured-icon">🌍</div>
                    <div className="featured-content">
                      <h4>Harmonized Landsat Sentinel-2 (HLS) v2.0</h4>
                      <p>Consistent surface reflectance from Landsat 8/9 and Sentinel-2A/B/C satellites. 30m resolution, 2020-present, ~2-3 day revisit.</p>
                      <div className="featured-tags">
                        <span className="tag">Sentinel</span>
                        <span className="tag">Landsat</span>
                        <span className="tag">HLS</span>
                        <span className="tag">Global</span>
                      </div>
                    </div>
                  </div>

                  <div className="featured-table-row">
                    <div className="featured-icon">🛰️</div>
                    <div className="featured-content">
                      <h4>Landsat Collection 2</h4>
                      <p>Comprehensive 50+ year archive from 1972-present. 30m resolution (modern), 79m (historical MSS). Longest-running Earth observation program.</p>
                      <div className="featured-tags">
                        <span className="tag">Landsat</span>
                        <span className="tag">USGS</span>
                        <span className="tag">NASA</span>
                        <span className="tag">Historical</span>
                      </div>
                    </div>
                  </div>

                  <div className="featured-table-row">
                    <div className="featured-icon">🌡️</div>
                    <div className="featured-content">
                      <h4>MODIS Version 6.1 Products</h4>
                      <p>14 products covering vegetation, temperature, fire, and snow. 250m-1km resolution, 2000-present. <strong>⚠️ Use "early 2024" or "January-June 2024" dates (3-6 month lag)</strong></p>
                      <div className="featured-tags">
                        <span className="tag">MODIS</span>
                        <span className="tag">NASA</span>
                        <span className="tag">Terra</span>
                        <span className="tag">Aqua</span>
                      </div>
                    </div>
                  </div>

                  <div className="featured-table-row">
                    <div className="featured-icon">📡</div>
                    <div className="featured-content">
                      <h4>Sentinel-1 SAR</h4>
                      <p>Weather-independent C-band radar. 10m resolution, 2014-present. Works through clouds and at night. Ideal for flood mapping and ship detection.</p>
                      <div className="featured-tags">
                        <span className="tag">ESA</span>
                        <span className="tag">Copernicus</span>
                        <span className="tag">SAR</span>
                        <span className="tag">Radar</span>
                      </div>
                    </div>
                  </div>

                  <div className="featured-table-row">
                    <div className="featured-icon">🌍</div>
                    <div className="featured-content">
                      <h4>Sentinel-2 Level-2A</h4>
                      <p>13 spectral bands at 10m-60m resolution, 2015-present, ~5 day revisit. Includes red edge bands for vegetation analysis.</p>
                      <div className="featured-tags">
                        <span className="tag">Sentinel</span>
                        <span className="tag">Copernicus</span>
                        <span className="tag">ESA</span>
                        <span className="tag">Multispectral</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="stac-divider"></div>

              {collectionData.map((category, idx) => (
                <div key={idx} className="stac-category">
                  <h3 className="stac-category-title">{category.category}</h3>
                  <div className="stac-table">
                    <div className="stac-table-header">
                      <div className="stac-col-name">Collection</div>
                      <div className="stac-col-res">Resolution</div>
                      <div className="stac-col-date">Date Range</div>
                      <div className="stac-col-why">Why</div>
                    </div>
                    {category.collections.map((collection, collIdx) => (
                      <div key={collIdx} className="stac-table-row">
                        <div className="stac-col-name">
                          <strong>{collection.name}</strong>
                          <div className="stac-example-query">
                            <span className="query-icon">💬</span>
                            "{collection.exampleQuery}"
                          </div>
                        </div>
                        <div className="stac-col-res">{collection.resolution}</div>
                        <div className="stac-col-date">
                          <span className="date-badge">{collection.dateRange}</span>
                        </div>
                        <div className="stac-col-why">{collection.why}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="stac-modal-footer">
              <div className="stac-footer-info">
                <span>✅ 21/21 Collections Operational</span>
                <span>•</span>
                <span>Last Updated: October 2025</span>
                <span>•</span>
                <span>Microsoft Planetary Computer</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default STACInfoButton;
