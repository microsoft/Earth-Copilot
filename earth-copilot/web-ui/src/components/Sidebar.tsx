// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import { Dataset } from '../services/api';
import DatasetDropdown from './DatasetDropdown';
import PCSearchPanel, { StructuredSearchParams } from './PCSearchPanel';

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  myDatasets: Dataset[];
  vedaDatasets: Dataset[];
  publicDatasets: Dataset[];
  planetaryComputerDatasets: Dataset[];
  isLoading: boolean;
  onDatasetSelect: (dataset: Dataset) => void;
  selectedDataset: Dataset | null;
  entryTarget: string | null;
  onPrivateSearch?: (query: string, collection?: Dataset) => void;
  onPCSearch?: (params: StructuredSearchParams) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  myDatasets,
  vedaDatasets,
  publicDatasets,
  planetaryComputerDatasets,
  isLoading,
  onDatasetSelect,
  selectedDataset,
  entryTarget,
  onPrivateSearch,
  onPCSearch
}) => {
  const [dropdownSelectedDataset, setDropdownSelectedDataset] = useState<Dataset | null>(null);
  const [vedaSelectedDataset, setVedaSelectedDataset] = useState<Dataset | null>(null);

  // Always show 3 data sources (removed APIs section)
  const shouldShowMyData = true;
  const shouldShowPlanetaryComputer = true;
  const shouldShowVeda = true;

  const handleDropdownSelect = (dataset: Dataset) => {
    setDropdownSelectedDataset(dataset);
    onDatasetSelect(dataset);
  };

  const handleVedaSelect = (dataset: Dataset) => {
    setVedaSelectedDataset(dataset);
    onDatasetSelect(dataset);
  };

  const getDatasetMetadata = (dataset: Dataset) => {
    const metadata = {
      'landsat-c2-l2': {
        provider: 'USGS',
        spatialResolution: '30m',
        temporalResolution: '16 days',
        spectralBands: '11 bands (443-2200nm)',
        coverage: 'Global',
        startDate: '1972-07-23',
        updateFrequency: 'Daily',
        license: 'Public Domain',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Land use mapping', 'Agriculture monitoring', 'Forest management'],
        documentation: 'https://www.usgs.gov/landsat-missions'
      },
      'sentinel-2-l2a': {
        provider: 'ESA',
        spatialResolution: '10-60m',
        temporalResolution: '5 days',
        spectralBands: '13 bands (443-2190nm)',
        coverage: 'Global',
        startDate: '2015-06-23',
        updateFrequency: 'Continuous',
        license: 'Open Data',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Agriculture', 'Forestry', 'Land cover mapping'],
        documentation: 'https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2'
      },
      'sentinel-1-rtc': {
        provider: 'ESA',
        spatialResolution: '10m',
        temporalResolution: '6-12 days',
        spectralBands: 'C-band SAR (5.405 GHz)',
        coverage: 'Global',
        startDate: '2014-04-03',
        updateFrequency: 'Continuous',
        license: 'Open Data',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Flood mapping', 'Ship detection', 'Land cover mapping'],
        documentation: 'https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-1'
      },
      'modis': {
        provider: 'NASA',
        spatialResolution: '250m, 500m, 1km',
        temporalResolution: '1-2 days',
        spectralBands: '36 bands (405nm to 14385nm)',
        coverage: 'Global',
        startDate: '2000-02-24',
        updateFrequency: 'Daily',
        license: 'Public Domain',
        dataFormat: 'HDF, NetCDF',
        applications: ['Climate monitoring', 'Fire detection', 'Ocean color'],
        documentation: 'https://modis.gsfc.nasa.gov/'
      },
      'daymet-daily-na': {
        provider: 'NASA',
        spatialResolution: '1km',
        temporalResolution: 'Daily',
        spectralBands: 'Weather variables',
        coverage: 'North America',
        startDate: '1980-01-01',
        updateFrequency: 'Annual',
        license: 'Public Domain',
        dataFormat: 'NetCDF',
        applications: ['Climate research', 'Ecological modeling', 'Agriculture'],
        documentation: 'https://daymet.ornl.gov/'
      },
      'era5-pds': {
        provider: 'ECMWF',
        spatialResolution: '31km',
        temporalResolution: 'Hourly',
        spectralBands: 'Atmospheric variables',
        coverage: 'Global',
        startDate: '1940-01-01',
        updateFrequency: 'Near real-time',
        license: 'Copernicus License',
        dataFormat: 'NetCDF, GRIB',
        applications: ['Weather forecasting', 'Climate analysis', 'Renewable energy'],
        documentation: 'https://www.ecmwf.int/en/forecasts/datasets/reanalysis-datasets/era5'
      },
      'nasadem': {
        provider: 'NASA',
        spatialResolution: '30m',
        temporalResolution: 'Static',
        spectralBands: 'Elevation',
        coverage: 'Global (60°N-56°S)',
        startDate: '2000-02-11',
        updateFrequency: 'Static',
        license: 'Public Domain',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Topography', 'Hydrology', 'Geology'],
        documentation: 'https://lpdaac.usgs.gov/products/nasadem_hgtv001/'
      },
      'goes-cmi': {
        provider: 'NOAA',
        spatialResolution: '0.5-2km',
        temporalResolution: '15 minutes',
        spectralBands: '16 channels (470-13300nm)',
        coverage: 'Americas',
        startDate: '2017-05-24',
        updateFrequency: 'Continuous',
        license: 'Public Domain',
        dataFormat: 'NetCDF',
        applications: ['Weather monitoring', 'Severe weather detection', 'Climate research'],
        documentation: 'https://www.goes-r.gov/'
      },
      'terraclimate': {
        provider: 'University of Idaho',
        spatialResolution: '4km',
        temporalResolution: 'Monthly',
        spectralBands: 'Climate variables',
        coverage: 'Global',
        startDate: '1958-01-01',
        updateFrequency: 'Monthly',
        license: 'CC BY 4.0',
        dataFormat: 'NetCDF',
        applications: ['Climate analysis', 'Drought monitoring', 'Water resources'],
        documentation: 'http://www.climatologylab.org/terraclimate.html'
      },
      'gbif': {
        provider: 'GBIF',
        spatialResolution: 'Point data',
        temporalResolution: 'Variable',
        spectralBands: 'Species occurrence data',
        coverage: 'Global',
        startDate: 'Historical',
        updateFrequency: 'Continuous',
        license: 'Various (CC0, CC BY)',
        dataFormat: 'Darwin Core',
        applications: ['Biodiversity research', 'Conservation planning', 'Species distribution modeling'],
        documentation: 'https://www.gbif.org/'
      },
      'aster-l1t': {
        provider: 'NASA',
        spatialResolution: '15-90m',
        temporalResolution: '16 days',
        spectralBands: '14 bands (520-11650nm)',
        coverage: 'Global',
        startDate: '2000-03-04',
        updateFrequency: 'Continuous',
        license: 'Public Domain',
        dataFormat: 'HDF',
        applications: ['Mineral mapping', 'Land surface temperature', 'Volcanic monitoring'],
        documentation: 'https://lpdaac.usgs.gov/products/ast_l1tv003/'
      },
      'cop-dem-glo-30': {
        provider: 'ESA',
        spatialResolution: '30m',
        temporalResolution: 'Static',
        spectralBands: 'Elevation',
        coverage: 'Global',
        startDate: '2011-12-12',
        updateFrequency: 'Static',
        license: 'Copernicus License',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Topographic mapping', 'Hydrological modeling', 'Infrastructure planning'],
        documentation: 'https://spacedata.copernicus.eu/web/cscda/dataset-details?articleId=394198'
      }
    };

    return metadata[dataset.id as keyof typeof metadata] || {
      provider: 'Microsoft Planetary Computer',
      spatialResolution: 'Variable',
      temporalResolution: 'Variable',
      spectralBands: 'Variable',
      coverage: 'Variable',
      startDate: 'Variable',
      updateFrequency: 'Variable',
      license: 'Variable',
      dataFormat: 'Variable',
      applications: ['Earth observation', 'Environmental monitoring'],
      documentation: 'https://planetarycomputer.microsoft.com/'
    };
  };

  return (
    <div className={`left ${!isOpen ? 'collapsed' : ''}`}>
      {isOpen && (
        <>
          <div
            className="data-catalog-title"
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              cursor: 'pointer',
              marginBottom: '16px'
            }}
            onClick={onToggle}
          >
            Data Catalog
            <span className="module-in-progress-badge" style={{
              position: 'relative',
              top: 'auto',
              right: 'auto',
              background: 'rgba(100, 116, 139, 0.12)',
              color: '#64748b',
              fontSize: '10px',
              fontWeight: 600,
              padding: '3px 9px',
              borderRadius: '10px',
              letterSpacing: '0.5px',
              textTransform: 'uppercase' as const,
              lineHeight: 1.4,
              backdropFilter: 'blur(4px)',
              marginLeft: '8px'
            }}>In Progress</span>
          </div>

          {isLoading ? (
            <div className="loading">Loading datasets...</div>
          ) : (
            <>
              {/* Planetary Computer Search Panel */}
              {onPCSearch && (
                <PCSearchPanel onSearch={onPCSearch} />
              )}

              {/* Private Section */}
              <div className="data-section private">
                <div className="data-section-title">
                  Private
                </div>

                {/* My Data Section */}
                {shouldShowMyData && (
                  <div style={{ marginBottom: '8px' }}>
                    <div
                      className="title"
                      style={{ fontSize: 14, marginBottom: 8, fontWeight: 'normal', cursor: 'pointer' }}
                      onClick={() => {
                        console.log('My Data clicked - loading private datasets');
                      }}
                    >
                      My Data
                    </div>
                    {myDatasets.length > 0 ? (
                      <DatasetDropdown
                        datasets={myDatasets}
                        selectedDataset={selectedDataset?.id && myDatasets.find(d => d.id === selectedDataset.id) ? selectedDataset : null}
                        onDatasetSelect={onDatasetSelect}
                        placeholder="Select a dataset..."
                      />
                    ) : (
                      <div style={{ fontSize: '12px', color: '#666', fontStyle: 'italic' }}>
                        No datasets available
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Public Section */}
              <div className="data-section public">
                <div className="data-section-title">
                  Public
                </div>

                {/* Planetary Computer Section */}
                {shouldShowPlanetaryComputer && (
                  <div style={{ marginBottom: '12px' }}>
                    <div className="title" style={{ fontSize: 14, marginBottom: 8, fontWeight: 'normal' }}>
                      Planetary Computer
                    </div>
                    {planetaryComputerDatasets.length > 0 ? (
                      <>
                        <DatasetDropdown
                          datasets={planetaryComputerDatasets}
                          selectedDataset={dropdownSelectedDataset}
                          onDatasetSelect={handleDropdownSelect}
                          placeholder="Choose a dataset..."
                        />
                      </>
                    ) : (
                      <div style={{ fontSize: '12px', color: '#666', fontStyle: 'italic' }}>
                        Loading collections...
                      </div>
                    )}
                  </div>
                )}

                {/* VEDA Section - AI Search Integration */}
                {shouldShowVeda && (
                  <div style={{ marginBottom: '12px' }}>
                    <div
                      className="title"
                      style={{
                        fontSize: 14,
                        marginBottom: 8,
                        fontWeight: 'normal',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between'
                      }}
                    >
                      VEDA
                      <span style={{ fontSize: '12px', opacity: 0.7, fontStyle: 'italic' }}>AI Search</span>
                    </div>
                    <DatasetDropdown
                      datasets={vedaDatasets}
                      selectedDataset={vedaSelectedDataset}
                      onDatasetSelect={handleVedaSelect}
                      placeholder="Choose a VEDA dataset..."
                    />
                    
                    {/* Search Button - Only show when a VEDA dataset is selected */}
                    {vedaSelectedDataset && (
                      <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'center' }}>
                        <button
                          onClick={() => {
                            if (onPrivateSearch && vedaSelectedDataset) {
                              const searchQuery = `Tell me about ${vedaSelectedDataset.title}`;
                              onPrivateSearch(searchQuery, vedaSelectedDataset);
                            }
                          }}
                          style={{
                            padding: '8px 16px',
                            backgroundColor: '#3b82f6',
                            color: 'white',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '14px',
                            cursor: 'pointer',
                            transition: 'background-color 0.2s',
                            fontWeight: '500',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                          }}
                          title={`Search ${vedaSelectedDataset.title} data`}
                          onMouseEnter={(e) => {
                            (e.target as HTMLElement).style.backgroundColor = '#2563eb';
                          }}
                          onMouseLeave={(e) => {
                            (e.target as HTMLElement).style.backgroundColor = '#3b82f6';
                          }}
                        >
                          Search
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};

interface DatasetItemProps {
  dataset: Dataset;
  isSelected: boolean;
  onClick: () => void;
}

const DatasetItem: React.FC<DatasetItemProps> = ({ dataset, isSelected, onClick }) => {
  return (
    <div
      className="dataset-item"
      style={{
        backgroundColor: isSelected ? 'rgba(14, 165, 233, 0.1)' : undefined,
        borderColor: isSelected ? 'var(--brand)' : undefined
      }}
      onClick={onClick}
    >
      <div className="dataset-title">{dataset.title}</div>
      <div className="dataset-description">
        {dataset.description && typeof dataset.description === 'string' 
          ? (dataset.description.length > 100 
              ? dataset.description.substring(0, 100) + '...' 
              : dataset.description)
          : 'No description available'}
      </div>
    </div>
  );
};

export default Sidebar;
