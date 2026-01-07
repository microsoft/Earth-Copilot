// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';
import { Dataset } from '../services/api';

interface DatasetDetailPanelProps {
  dataset: Dataset | null;
  onClose: () => void;
}

const DatasetDetailPanel: React.FC<DatasetDetailPanelProps> = ({ dataset, onClose }) => {
  if (!dataset) return null;

  const getDatasetMetadata = (dataset: Dataset) => {
    const metadata: Record<string, any> = {
      'landsat-c2-l2': {
        provider: 'USGS',
        spatialResolution: '30m',
        temporalResolution: '16 days',
        spectralBands: 'Visible, NIR, SWIR, Thermal',
        coverage: 'Global',
        startDate: '1972-07-23',
        updateFrequency: 'Continuous',
        license: 'Public Domain',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Land cover classification', 'Change detection', 'Environmental monitoring'],
        documentation: 'https://www.usgs.gov/landsat-missions/landsat-collection-2'
      },
      'sentinel-2-l2a': {
        provider: 'ESA',
        spatialResolution: '10m, 20m, 60m',
        temporalResolution: '5 days',
        spectralBands: '13 bands (443nm to 2190nm)',
        coverage: 'Global land surface',
        startDate: '2015-06-23',
        updateFrequency: 'Continuous',
        license: 'Open Data',
        dataFormat: 'Cloud Optimized GeoTIFF',
        applications: ['Agriculture monitoring', 'Forest management', 'Disaster response'],
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
        applications: ['Topographic analysis', 'Flood modeling', 'Viewshed analysis'],
        documentation: 'https://lpdaac.usgs.gov/products/nasadem_hgtv001/'
      },
      'goes-cmi': {
        provider: 'NOAA',
        spatialResolution: '0.5-2km',
        temporalResolution: '5-15 minutes',
        spectralBands: '16 bands (visible to infrared)',
        coverage: 'Americas',
        startDate: '2017-05-24',
        updateFrequency: 'Real-time',
        license: 'Public Domain',
        dataFormat: 'NetCDF',
        applications: ['Weather monitoring', 'Hurricane tracking', 'Fire detection'],
        documentation: 'https://www.goes-r.gov/'
      },
      'terraclimate': {
        provider: 'University of Idaho',
        spatialResolution: '4km',
        temporalResolution: 'Monthly',
        spectralBands: 'Climate variables',
        coverage: 'Global terrestrial',
        startDate: '1958-01-01',
        updateFrequency: 'Annual',
        license: 'Public Domain',
        dataFormat: 'NetCDF',
        applications: ['Climate research', 'Drought monitoring', 'Water resources'],
        documentation: 'https://www.climatologylab.org/terraclimate.html'
      },
      'gbif': {
        provider: 'GBIF',
        spatialResolution: 'Point data',
        temporalResolution: 'Variable',
        spectralBands: 'Species occurrence',
        coverage: 'Global',
        startDate: '1758-01-01',
        updateFrequency: 'Continuous',
        license: 'Various (CC licenses)',
        dataFormat: 'Parquet',
        applications: ['Biodiversity research', 'Species distribution modeling', 'Conservation'],
        documentation: 'https://www.gbif.org/'
      },
      'aster-l1t': {
        provider: 'NASA/METI',
        spatialResolution: '15m, 30m, 90m',
        temporalResolution: '16 days',
        spectralBands: '14 bands (visible to thermal)',
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

    return metadata[dataset.id] || {
      provider: 'Microsoft Planetary Computer',
      spatialResolution: 'Variable',
      temporalResolution: 'Variable',
      coverage: 'Variable',
      license: 'Variable',
      applications: ['Earth observation', 'Environmental monitoring']
    };
  };

  const metadata = getDatasetMetadata(dataset);

  return (
    <div className="dataset-detail-panel">
      <div className="detail-header">
        <h2>{dataset.title}</h2>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
      
      <div className="detail-content">
        <div className="detail-section">
          <h3>Overview</h3>
          <p>{dataset.description}</p>
        </div>

        <div className="detail-section">
          <h3>Technical Specifications</h3>
          <div className="spec-grid">
            <div className="spec-item">
              <strong>Provider:</strong> {metadata.provider}
            </div>
            <div className="spec-item">
              <strong>Spatial Resolution:</strong> {metadata.spatialResolution}
            </div>
            <div className="spec-item">
              <strong>Temporal Resolution:</strong> {metadata.temporalResolution}
            </div>
            <div className="spec-item">
              <strong>Coverage:</strong> {metadata.coverage}
            </div>
            {metadata.spectralBands && (
              <div className="spec-item">
                <strong>Spectral Information:</strong> {metadata.spectralBands}
              </div>
            )}
            <div className="spec-item">
              <strong>Data Format:</strong> {metadata.dataFormat}
            </div>
            <div className="spec-item">
              <strong>License:</strong> {metadata.license}
            </div>
            {metadata.startDate && (
              <div className="spec-item">
                <strong>Start Date:</strong> {metadata.startDate}
              </div>
            )}
            <div className="spec-item">
              <strong>Update Frequency:</strong> {metadata.updateFrequency}
            </div>
          </div>
        </div>

        {metadata.applications && (
          <div className="detail-section">
            <h3>Common Applications</h3>
            <ul className="applications-list">
              {metadata.applications.map((app: string, index: number) => (
                <li key={index}>{app}</li>
              ))}
            </ul>
          </div>
        )}

        {metadata.documentation && (
          <div className="detail-section">
            <h3>Documentation</h3>
            <a 
              href={metadata.documentation} 
              target="_blank" 
              rel="noopener noreferrer"
              className="doc-link"
            >
              View official documentation →
            </a>
          </div>
        )}

        <div className="detail-section">
          <h3>Data Access</h3>
          <p>This dataset is available through Microsoft Planetary Computer's STAC API. You can query and analyze this data using the chat interface below.</p>
          <div className="access-buttons">
            <button className="btn primary">Query with AI</button>
            <button className="btn secondary">View Sample Code</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DatasetDetailPanel;
