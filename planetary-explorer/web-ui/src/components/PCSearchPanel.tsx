// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import './PCSearchPanel.css';
import { API_BASE_URL } from '../config/api';
import { authenticatedFetch } from '../services/authHelper';
import { apiService, Dataset } from '../services/api';

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

export interface StructuredSearchParams {
  collection: string;
  location: string;
  datetime?: string;          // Single date in MM/DD/YYYY format
  datetime_start?: string;    // Range start
  datetime_end?: string;      // Range end
  stacMode?: 'public' | 'pro'; // Routing hint: public PC vs MPC Pro
}

interface PCSearchPanelProps {
  onSearch: (params: StructuredSearchParams) => void;
  /**
   * The current ambient STAC mode (driven by the global toggle in the header).
   * Used as the *default* selection inside this panel — the user can still
   * override per-search via the Public/Private radio.
   */
  ambientStacMode?: 'public' | 'pro';
  /**
   * When the user clicks Public/Private in this panel, propagate the change
   * up so the global header toggle and the chat `stac_mode` stay aligned.
   * There is exactly one source of truth: the global mode.
   */
  onStacModeChange?: (mode: 'public' | 'pro') => void;
}

const PCSearchPanel: React.FC<PCSearchPanelProps> = ({ onSearch, ambientStacMode, onStacModeChange }) => {
  const [mode, setMode] = useState<'public' | 'pro'>(ambientStacMode || 'public');
  const [publicDatasets, setPublicDatasets] = useState<CollectionData[]>([]);
  const [proCollections, setProCollections] = useState<Dataset[]>([]);
  const [proLoaded, setProLoaded] = useState<boolean>(false);
  const [proConfigured, setProConfigured] = useState<boolean>(false);
  const [proError, setProError] = useState<string | null>(null);
  const [proRefreshing, setProRefreshing] = useState<boolean>(false);

  const [selectedCollection, setSelectedCollection] = useState<string>('');
  const [location, setLocation] = useState<string>('');
  const [useDateRange, setUseDateRange] = useState<boolean>(false);
  const [singleDate, setSingleDate] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Keep mode in sync with the ambient global toggle (best-effort default).
  useEffect(() => {
    if (ambientStacMode) setMode(ambientStacMode);
  }, [ambientStacMode]);

  // Load public PC dataset catalog (static config bundled with the app).
  useEffect(() => {
    authenticatedFetch(`${API_BASE_URL}/pc_rendering_config.json`)
      .then((response) => response.json())
      .then((config: RenderingConfig) => {
        const arr = Object.values(config.collections);
        setPublicDatasets(arr);
      })
      .catch((error) => {
        console.error('Failed to load PC rendering config:', error);
      });
  }, []);

  // Load private (MPC Pro / GeoCatalog) collections from the backend.
  // Exposed as a memoized callback so the user can retry on demand
  // (e.g. after refreshing their AAD token) without remounting.
  const loadProCollections = useCallback(async () => {
    setProRefreshing(true);
    try {
      const res = await apiService.getProCollections();
      setProCollections(res.collections);
      setProConfigured(res.configured);
      setProError(res.error || null);
    } catch {
      setProCollections([]);
      setProConfigured(false);
      setProError('Unexpected client error');
    } finally {
      setProLoaded(true);
      setProRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadProCollections();
  }, [loadProCollections]);

  // Default selection when the mode flips (so the dropdown isn't blank).
  useEffect(() => {
    if (mode === 'public') {
      if (publicDatasets.length > 0 && !publicDatasets.some((d) => d.collection_id === selectedCollection)) {
        setSelectedCollection(publicDatasets[0].collection_id);
      }
    } else {
      if (proCollections.length > 0 && !proCollections.some((c) => c.id === selectedCollection)) {
        setSelectedCollection(proCollections[0].id);
      } else if (proCollections.length === 0) {
        setSelectedCollection('');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, publicDatasets, proCollections]);

  const groupedPublic = useMemo(
    () =>
      publicDatasets.reduce((acc, dataset) => {
        const category = dataset.category || 'Other';
        if (!acc[category]) acc[category] = [];
        acc[category].push(dataset);
        return acc;
      }, {} as Record<string, CollectionData[]>),
    [publicDatasets]
  );

  const handleSearch = () => {
    if (!selectedCollection || !location) {
      alert('Please select a collection and enter a location');
      return;
    }
    setIsLoading(true);
    const params: StructuredSearchParams = {
      collection: selectedCollection,
      location: location.trim(),
      stacMode: mode,
    };
    if (useDateRange) {
      if (startDate) params.datetime_start = startDate;
      if (endDate) params.datetime_end = endDate;
    } else {
      if (singleDate) params.datetime = singleDate;
    }
    onSearch(params);
    setTimeout(() => setIsLoading(false), 1000);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isLoading) handleSearch();
  };

  const proEmpty = proLoaded && proCollections.length === 0;

  return (
    <div className="pc-search-panel">
      <div className="pc-search-header">
        <h3>Microsoft Planetary Computer</h3>
        <p className="pc-search-subtitle">Pick a collection, location, and time to search.</p>
      </div>

      <div className="pc-search-body">
        {/* Public / Private mode toggle — single segmented pill.
            Two halves visually live inside one rounded container so it
            reads as "one button" with two states. Clicking "Private"
            flips the panel to show the live MPC Pro collection list
            (fetched from /api/pro/collections). */}
        <div
          className="pc-search-field"
          role="radiogroup"
          aria-label="STAC source"
        >
          <div
            style={{
              display: 'flex',
              position: 'relative',
              padding: 3,
              borderRadius: 999,
              border: '1px solid #e5e7eb',
              background: '#f3f4f6',
            }}
          >
            {/* Sliding active indicator */}
            <div
              aria-hidden
              style={{
                position: 'absolute',
                top: 3,
                bottom: 3,
                left: mode === 'public' ? 3 : 'calc(50% + 0px)',
                width: 'calc(50% - 3px)',
                borderRadius: 999,
                background: 'rgba(59,130,246,0.18)',
                border: '1px solid #93c5fd',
                transition: 'left 0.18s ease',
                pointerEvents: 'none',
              }}
            />
            <button
              type="button"
              role="radio"
              aria-checked={mode === 'public'}
              onClick={() => { setMode('public'); onStacModeChange?.('public'); }}
              style={{
                flex: 1,
                position: 'relative',
                padding: '6px 10px',
                borderRadius: 999,
                border: 'none',
                background: 'transparent',
                color: mode === 'public' ? '#1f2937' : '#6b7280',
                fontWeight: mode === 'public' ? 600 : 500,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Public
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={mode === 'pro'}
              onClick={() => {
                setMode('pro');
                onStacModeChange?.('pro');
                // Re-fetch every time the user clicks Private so an
                // expired/stale token (which silently returns []) can
                // recover without the user having to reload the page.
                void loadProCollections();
              }}
              title={
                proError
                  ? `Failed to load private collections: ${proError}`
                  : proEmpty
                  ? 'No private MPC Pro collections configured for this deployment.'
                  : 'Search the private MPC Pro (GeoCatalog) instance.'
              }
              style={{
                flex: 1,
                position: 'relative',
                padding: '6px 10px',
                borderRadius: 999,
                border: 'none',
                background: 'transparent',
                color: mode === 'pro' ? '#1f2937' : '#6b7280',
                fontWeight: mode === 'pro' ? 600 : 500,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Private{proCollections.length > 0 ? ` (${proCollections.length})` : proError ? ' (!)' : proEmpty ? ' (none)' : ''}
            </button>
          </div>
        </div>

        {/* Collection dropdown — content depends on mode */}
        <div className="pc-search-field">
          <label htmlFor="dataset-select">Collection</label>
          {mode === 'public' ? (
            <select
              id="dataset-select"
              value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}
              className="pc-search-select"
            >
              <option value="">-- Select a collection --</option>
              {Object.entries(groupedPublic).map(([category, categoryDatasets]) => (
                <optgroup key={category} label={category}>
                  {categoryDatasets.map((dataset) => {
                    const desc = dataset.metadata?.description || '';
                    const shortDesc =
                      typeof desc === 'string' && desc.length > 60
                        ? desc.substring(0, 60) + '...'
                        : desc;
                    return (
                      <option key={dataset.collection_id} value={dataset.collection_id}>
                        {dataset.collection_id}
                        {shortDesc ? ` — ${shortDesc}` : ''}
                      </option>
                    );
                  })}
                </optgroup>
              ))}
            </select>
          ) : proEmpty ? (
            <div
              style={{
                padding: '8px 10px',
                fontSize: 12,
                color: '#94a3b8',
                background: 'rgba(255,255,255,0.02)',
                border: '1px dashed rgba(100,116,139,0.4)',
                borderRadius: 6,
              }}
            >
              {proError ? (
                <>
                  <div style={{ color: '#fca5a5', marginBottom: 6 }}>
                    Couldn't load private collections.
                  </div>
                  <div style={{ fontSize: 11, marginBottom: 8 }}>{proError}</div>
                  {proError.includes('401') || proError.toLowerCase().includes('token') ? (
                    <div style={{ fontSize: 11, marginBottom: 8 }}>
                      Your sign-in session may have expired. Try refreshing
                      the page (or sign out and back in), then click Retry.
                    </div>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void loadProCollections()}
                    disabled={proRefreshing}
                    style={{
                      padding: '4px 10px',
                      fontSize: 11,
                      borderRadius: 4,
                      border: '1px solid rgba(100,116,139,0.5)',
                      background: 'rgba(59,130,246,0.18)',
                      color: '#e2e8f0',
                      cursor: proRefreshing ? 'wait' : 'pointer',
                    }}
                  >
                    {proRefreshing ? 'Retrying…' : 'Retry'}
                  </button>
                </>
              ) : !proConfigured ? (
                <>
                  No private collections configured.
                  <br />
                  Set <code>MPC_PRO_STAC_URL</code> on the backend to enable.
                </>
              ) : (
                <>
                  Pro endpoint is configured but returned 0 collections.
                  <button
                    type="button"
                    onClick={() => void loadProCollections()}
                    disabled={proRefreshing}
                    style={{
                      marginLeft: 8,
                      padding: '2px 8px',
                      fontSize: 11,
                      borderRadius: 4,
                      border: '1px solid rgba(100,116,139,0.5)',
                      background: 'transparent',
                      color: '#e2e8f0',
                      cursor: proRefreshing ? 'wait' : 'pointer',
                    }}
                  >
                    {proRefreshing ? '…' : 'Refresh'}
                  </button>
                </>
              )}
            </div>
          ) : (
            <select
              id="dataset-select"
              value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}
              className="pc-search-select"
            >
              <option value="">-- Select a private collection --</option>
              {proCollections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                  {c.description ? ` — ${c.description.substring(0, 60)}` : ''}
                </option>
              ))}
            </select>
          )}
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
            Place name, city, state, country, or lat,lon coordinates.
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
              {useDateRange ? 'Range' : 'Single'}
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
              ? 'Enter a date range, or leave blank for most recent.'
              : 'Enter a date, or leave blank for most recent.'}
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
              Search {mode === 'pro' ? 'private' : 'public'}
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default PCSearchPanel;
