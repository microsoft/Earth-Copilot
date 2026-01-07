// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import './PCSearchPanel.css';
import { API_BASE_URL } from '../config/api';

interface CollectionData {
  collection_id: string;
  category: string;
  metadata?: {
    description?: string;
    title?: string;
    keywords?: string[];
  };
  rendering?: {
    assets?: string[];
    rescale?: number[] | null;
    colormap_name?: string | null;
  };
}

interface RenderingConfig {
  metadata: {
    total_collections: number;
    last_updated: string;
    source: string;
  };
  collections: Record<string, CollectionData>;
}

interface PCSearchPanelProps {
  onSearch: (params: StructuredSearchParams) => void;
}

export interface StructuredSearchParams {
  collection: string;
  location: string;
  datetime?: string; // Single date in MM/DD/YYYY format
  datetime_start?: string; // Range start
  datetime_end?: string; // Range end
}

const PCSearchPanel: React.FC<PCSearchPanelProps> = ({ onSearch }) => {
  const [datasets, setDatasets] = useState<CollectionData[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string>('');
  const [location, setLocation] = useState<string>('');
  const [useDateRange, setUseDateRange] = useState<boolean>(false);
  const [singleDate, setSingleDate] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Load datasets from unified rendering config
  useEffect(() => {
    fetch(`${API_BASE_URL}/pc_rendering_config.json`)
      .then(response => response.json())
      .then((config: RenderingConfig) => {
        // Convert collections object to array
        const collectionsArray = Object.values(config.collections);
        setDatasets(collectionsArray);
        // Set first collection as default
        if (collectionsArray.length > 0) {
          setSelectedCollection(collectionsArray[0].collection_id);
        }
      })
      .catch(error => {
        console.error('Failed to load PC rendering config:', error);
      });
  }, []);

  const handleSearch = () => {
    if (!selectedCollection || !location) {
      alert('Please select a dataset and enter a location');
      return;
    }

    setIsLoading(true);

    const params: StructuredSearchParams = {
      collection: selectedCollection,
      location: location.trim(),
    };

    if (useDateRange) {
      if (startDate) params.datetime_start = startDate;
      if (endDate) params.datetime_end = endDate;
    } else {
      if (singleDate) params.datetime = singleDate;
    }

    onSearch(params);

    // Reset loading state after a short delay
    setTimeout(() => setIsLoading(false), 1000);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isLoading) {
      handleSearch();
    }
  };

  // Group datasets by category
  const groupedDatasets = datasets.reduce((acc, dataset) => {
    const category = dataset.category || 'Other';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(dataset);
    return acc;
  }, {} as Record<string, CollectionData[]>);

  return (
    <div className="pc-search-panel">
      <div className="pc-search-header">
        <h3>🌍 Planetary Computer Search</h3>
        <p className="pc-search-subtitle">Search STAC API with structured parameters</p>
      </div>

      <div className="pc-search-body">
        {/* Dataset Dropdown */}
        <div className="pc-search-field">
          <label htmlFor="dataset-select">Dataset</label>
          <select
            id="dataset-select"
            value={selectedCollection}
            onChange={(e) => setSelectedCollection(e.target.value)}
            className="pc-search-select"
          >
            <option value="">-- Select a dataset --</option>
            {Object.entries(groupedDatasets).map(([category, categoryDatasets]) => (
              <optgroup key={category} label={category}>
                {categoryDatasets.map((dataset) => {
                  const desc = dataset.metadata?.description || 'No description';
                  const shortDesc = typeof desc === 'string' && desc.length > 60 
                    ? desc.substring(0, 60) + '...' 
                    : desc;
                  
                  return (
                    <option key={dataset.collection_id} value={dataset.collection_id}>
                      {dataset.collection_id} - {shortDesc}
                    </option>
                  );
                })}
              </optgroup>
            ))}
          </select>
        </div>

        {/* Location Input */}
        <div className="pc-search-field">
          <label htmlFor="location-input">Location</label>
          <input
            id="location-input"
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="e.g., California, New York City, 40.7,-74.0"
            className="pc-search-input"
          />
          <small className="pc-search-hint">
            Enter a place name, city, state, or coordinates (lat,lon)
          </small>
        </div>

        {/* Time Section */}
        <div className="pc-search-field">
          <div className="pc-search-time-header">
            <label>Time</label>
            <button
              className={`pc-search-range-toggle ${useDateRange ? 'active' : ''}`}
              onClick={() => setUseDateRange(!useDateRange)}
              title={useDateRange ? 'Switch to single date' : 'Switch to date range'}
            >
              {useDateRange ? '📅 Range' : '📆 Single'}
            </button>
          </div>

          {useDateRange ? (
            <div className="pc-search-date-range">
              <input
                type="text"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="MM/DD/YYYY"
                className="pc-search-input pc-search-date-input"
              />
              <span className="pc-search-date-separator">to</span>
              <input
                type="text"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="MM/DD/YYYY"
                className="pc-search-input pc-search-date-input"
              />
            </div>
          ) : (
            <input
              type="text"
              value={singleDate}
              onChange={(e) => setSingleDate(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="MM/DD/YYYY (optional)"
              className="pc-search-input"
            />
          )}
          <small className="pc-search-hint">
            {useDateRange
              ? 'Enter date range or leave blank for most recent'
              : 'Enter a date or leave blank for most recent'}
          </small>
        </div>

        {/* Search Button */}
        <button
          className="pc-search-button"
          onClick={handleSearch}
          disabled={isLoading || !selectedCollection || !location}
        >
          {isLoading ? (
            <>
              <span className="pc-search-spinner"></span>
              Searching...
            </>
          ) : (
            <>
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="11" cy="11" r="8"></circle>
                <path d="m21 21-4.35-4.35"></path>
              </svg>
              Search
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default PCSearchPanel;
