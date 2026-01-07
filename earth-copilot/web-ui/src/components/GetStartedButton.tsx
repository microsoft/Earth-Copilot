// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import './GetStartedButton.css';

interface ExampleQuery {
  query: string;
  description: string;
  dataset: string;
  pc_link?: string;
}

interface QueryCategory {
  category: string;
  icon: string;
  examples: ExampleQuery[];
}

interface GetStartedButtonProps {
  onQuerySelect?: (query: string) => void;
}

const GetStartedButton: React.FC<GetStartedButtonProps> = ({ onQuerySelect }) => {
  const [showModal, setShowModal] = useState(false);

  const exampleQueries: QueryCategory[] = [
    {
      category: "🌍 High-Resolution Imagery",
      icon: "🛰️",
      examples: [
        {
          query: "Show Harmonized Landsat Sentinel-2 imagery of Athens",
          description: "30m resolution harmonized imagery combining Landsat-8/9 and Sentinel-2",
          dataset: "HLS S30",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=23.5861%2C38.0986&z=9.81&v=2&d=hls2-s30&m=Most+recent+%28low+cloud%29&r=Natural+color&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show Harmonized Landsat Sentinel-2 (HLS) Version 2.0 images of Moscow",
          description: "30m resolution harmonized imagery combining Landsat-8/9 and Sentinel-2",
          dataset: "HLS S30",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=37.6296%2C55.7497&z=11.88&v=2&d=sentinel-2&m=Most+recent+%28low+cloud%29&r=Natural+color&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show HLS images of Washington DC on January 1st 2026",
          description: "30m resolution harmonized imagery combining Landsat-8/9 and Sentinel-2",
          dataset: "HLS S30",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-76.9717%2C38.9445&z=10.07&v=2&d=hls2-s30&s=false%3A%3A100%3A%3Atrue&ae=0&sr=desc&m=Most+recent+%28low+cloud%29&r=Natural+color"
        }
      ]
    },
    {
      category: "🔥 Fire Detection & Monitoring",
      icon: "🔥",
      examples: [
        {
          query: "Show wildfire MODIS data for California",
          description: "1km thermal anomalies and fire detection, daily updates. Note: Zoom level 10+ required.",
          dataset: "MODIS 14A1",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-116.7265%2C32.4538&z=9.44&v=2&d=modis-14A1-061&m=Most+recent&r=Confidence+of+fire%2C+daily&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show fire modis thermal anomalies daily activity for Australia from June 2025",
          description: "1km thermal anomalies and fire locations, 8-day composite. Note: Zoom level 10+ required.",
          dataset: "MODIS 14A2",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=143.7962%2C-15.0196&z=7.84&v=2&d=modis-14A2-061&m=Most+recent&r=Confidence+of+fire+8-day&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show MTBS burn severity for California in 2017",
          description: "30m burn severity assessment for large fires (1984-2018)",
          dataset: "MTBS",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-120.1414%2C37.5345&z=7.00&v=2&d=mtbs&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0&m=2017&r=Burn+severity"
        }
      ]
    },
    {
      category: "🌊 Water & Surface Reflectance",
      icon: "💧",
      examples: [
        {
          query: "Display JRC Global Surface Water in Bangladesh",
          description: "30m water occurrence mapping from 1984-2021",
          dataset: "JRC Global Surface Water",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=90.8176%2C23.6238&z=7.48&v=2&d=jrc-gsw&m=Most+recent&r=Water+occurrence&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show modis snow cover daily for Quebec for January 2025",
          description: "500m snow cover and NDSI, daily updates",
          dataset: "MODIS 10A1",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-68.9402%2C50.1979&z=6.60&v=2&d=modis-10A1-061&m=Most+recent&r=Normalized+difference+snow+index+%28NDSI%29+daily&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show me Sea Surface Temperature near Madagascar",
          description: "0.25° resolution daily sea surface temperature (PC collection missing)",
          dataset: "NOAA CDR Sea Surface Temperature",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=45.4423%2C-18.9211&z=8.39&v=2&d=noaa-cdr-sea-surface-temperature-whoi&m=Most+recent&r=Sea+surface+temperature&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        }
      ]
    },
    {
      category: "🌲 Vegetation & Agriculture",
      icon: "🌿",
      examples: [
        {
          query: "Show modis net primary production for San Jose",
          description: "500m net primary productivity, yearly composite",
          dataset: "MODIS 17A3HGF",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-121.8004%2C37.0229&z=8.41&v=2&d=modis-17A3HGF-061&m=Most+recent&r=Net+primary+productivity+gap-filled+yearly+%28kgC%2Fm%C2%B2%29&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show me chloris biomass for the Amazon rainforest",
          description: "30m aboveground woody biomass estimates",
          dataset: "Chloris Biomass",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-59.7980%2C-5.0908&z=4.89&v=2&d=chloris-biomass&m=All+years&r=Aboveground+Biomass+%28tonnes%29&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show modis vedgetation indices for Ukraine",
          description: "250m NDVI and EVI vegetation indices, 16-day composite",
          dataset: "MODIS 13Q1",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=31.9567%2C49.4227&z=9.82&v=2&d=modis-13Q1-061&m=Most+recent&r=Normalized+difference+vegetation+index+%28NDVI%29+16-day&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show USDA Cropland Data Layers (CDLs) for Florida",
          description: "30m crop-specific land cover classification",
          dataset: "USDA CDL",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-85.1998%2C31.2059&z=10.11&v=2&d=usda-cdl&m=Most+recent+cropland&r=Default&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show recent modis nadir BDRF adjusted reflectance for Mexico",
          description: "500m nadir BRDF-adjusted reflectance, daily",
          dataset: "MODIS 43A4",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-95.5417%2C26.5068&z=6.84&v=2&d=modis-43A4-061&m=Most+recent&r=Natural+color&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        }
      ]
    },
    {
      category: "🏔️ Elevation & Buildings",
      icon: "⛰️",
      examples: [
        {
          query: "Show elevation map of Grand Canyon",
          description: "30m Copernicus Digital Elevation Model",
          dataset: "COP-DEM GLO-30"
        },
        {
          query: "Show ALOS World 3D-30m of Tomas de Berlanga",
          description: "30m ALOS World 3D digital surface model",
          dataset: "ALOS World 3D-30m",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-91.0202%2C-0.8630&z=14.22&v=2&d=alos-dem&m=Most+recent&r=Hillshade&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show USGS 3DEP Lidar Height above Ground for New Orleans",
          description: "High-resolution lidar-derived height above ground",
          dataset: "USGS 3DEP Lidar HAG",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-90.0715%2C29.9511&z=12.83&v=2&d=3dep-lidar-hag&m=Most+recent&r=Height+Above+Ground&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show USGS 3DEP Lidar Height above Ground for Denver, Colorado",
          description: "High-resolution lidar-derived height above ground",
          dataset: "USGS 3DEP Lidar HAG",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-104.9903%2C39.7392&z=12.70&v=2&d=3dep-lidar-hag&m=Most+recent&r=Height+Above+Ground&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        }
      ]
    },
    {
      category: "📡 Radar & Reflectance",
      icon: "⛰️",
      examples: [
        {
          query: "Show Sentinel 1 RTC for Baltimore",
          description: "10m SAR backscatter radiometrically terrain corrected",
          dataset: "Sentinel-1 RTC",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-76.6287%2C39.2547&z=12.18&v=2&d=sentinel-1-rtc&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0&m=Most+recent+-+VV%2C+VH&r=VV%2C+VH+False-color+composite"
        },
        {
          query: "Show ALOS PALSAR Annual for Ecuador",
          description: "25m L-band SAR annual mosaic",
          dataset: "ALOS PALSAR Annual Mosaic",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=-78.3799%2C-1.4259&z=9.04&v=2&d=alos-palsar-mosaic&m=All+years&r=False-color+composite&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        },
        {
          query: "Show Sentinel 1 Radiometrically Terrain Corrected (RTC) for Philipines",
          description: "10m SAR backscatter radiometrically terrain corrected",
          dataset: "Sentinel-1 RTC",
          pc_link: "https://planetarycomputer.microsoft.com/explore?c=124.1929%2C9.9849&z=7.94&v=2&d=sentinel-1-rtc&m=Most+recent+-+VV%2C+VH&r=VV%2C+VH+False-color+composite&s=false%3A%3A100%3A%3Atrue&sr=desc&ae=0"
        }
      ]
    }
  ];

  const handleExampleClick = (query: string) => {
    console.log('🚀 GetStartedButton: Example clicked:', query);
    
    // Close the modal
    setShowModal(false);
    
    // If onQuerySelect callback provided (from Landing Page), use it
    if (onQuerySelect) {
      console.log('✅ GetStartedButton: Using onQuerySelect callback');
      onQuerySelect(query);
      return;
    }
    
    // Otherwise, dispatch event for Chat component (when already in app)
    setTimeout(() => {
      console.log('📤 GetStartedButton: Dispatching earthcopilot-query event');
      const event = new CustomEvent('earthcopilot-query', { 
        detail: { query },
        bubbles: true,
        composed: true
      });
      window.dispatchEvent(event);
    }, 150);
  };

  return (
    <>
      <div
        onClick={() => setShowModal(true)}
        className="get-started-button"
        title="Get Started Guide"
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
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>
        <span className="get-started-button-label">Get Started</span>
      </div>

      {showModal && (
        <div className="get-started-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="get-started-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="get-started-modal-header">
              <h2>🚀 Get Started with Earth Copilot</h2>
              <button 
                onClick={() => setShowModal(false)} 
                className="get-started-modal-close"
                title="Close"
              >
                ×
              </button>
            </div>

            <div className="get-started-modal-body">
              {/* Introduction */}
              <section className="get-started-section">
                <h3>💡 What is Earth Copilot?</h3>
                <p>
                  Earth Copilot is your AI-powered assistant for exploring geospatial data from Microsoft's 
                  Planetary Computer. Simply ask questions in natural language, and Earth Copilot will 
                  automatically search, process, and visualize satellite imagery and Earth observation data on an interactive map.
                </p>
              </section>

              {/* Example Queries */}
              <section className="get-started-section">
                <h3>📝 Try These Example Queries</h3>
                <p className="examples-subtitle">
                  Click any example to copy it to your clipboard, then paste it into the search box on the main page.
                </p>
                
                {/* Pro Tip */}
                <div className="zoom-tip" style={{ marginBottom: '20px' }}>
                  <span className="zoom-tip-icon">🔍</span>
                  <div className="zoom-tip-content">
                    <strong>Pro Tip:</strong> Some satellite collections (especially MODIS fire data) only display tiles at deeper zoom levels. 
                    Try zooming to <strong>level 10+</strong> and panning around the map to see all available tiles.
                  </div>
                </div>

                {exampleQueries.map((category) => (
                  <div key={category.category} className="example-category">
                    <h4 className="category-title">{category.category}</h4>
                    
                    <div className="examples-grid">
                      {category.examples.map((example, index) => (
                        <div key={index} className="example-card">
                          <div className="example-query">
                            <strong>"{example.query}"</strong>
                          </div>
                          <div className="example-description">
                            {example.description}
                          </div>
                          <div className="example-meta">
                            <span className="example-dataset">📊 {example.dataset}</span>
                            <div className="example-buttons">
                              <button
                                className="copy-query-btn"
                                onClick={() => handleExampleClick(example.query)}
                                title="Run this query in Earth Copilot"
                              >
                                ▶️ Go
                              </button>
                              {example.pc_link && (
                                <button
                                  className="pc-explorer-btn"
                                  onClick={() => window.open(example.pc_link, '_blank')}
                                  title="View in Planetary Computer Explorer"
                                >
                                  🌍 PC Explorer
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </section>

              {/* Learn More */}
              <section className="get-started-section learn-more-section">
                <h3>📚 Want to Learn More?</h3>
                <div className="learn-more-grid">
                  <div className="learn-more-card">
                    <div className="learn-more-icon">📊</div>
                    <h4>Browse STAC Collections</h4>
                    <p>
                      Explore all 68 available datasets, their parameters, and visualization options
                    </p>
                    <button 
                      className="learn-more-btn"
                      onClick={() => {
                        setShowModal(false);
                        // Trigger the STAC Data button click
                        setTimeout(() => {
                          const stacButton = document.querySelector('.stac-info-button') as HTMLButtonElement;
                          if (stacButton) stacButton.click();
                        }, 100);
                      }}
                    >
                      View STAC Collections →
                    </button>
                  </div>

                  <div className="learn-more-card">
                    <div className="learn-more-icon">💚</div>
                    <h4>Check System Health</h4>
                    <p>
                      Monitor backend connectivity, API status, and service availability
                    </p>
                    <button 
                      className="learn-more-btn"
                      onClick={() => {
                        setShowModal(false);
                        setTimeout(() => {
                          const healthButton = document.querySelector('.health-button') as HTMLButtonElement;
                          if (healthButton) healthButton.click();
                        }, 100);
                      }}
                    >
                      View System Status →
                    </button>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default GetStartedButton;
