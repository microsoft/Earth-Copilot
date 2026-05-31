// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';
import { Dataset } from '../services/api';
import PCSearchPanel, { StructuredSearchParams } from './PCSearchPanel';
import FabricConnect from './FabricConnect';

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;

  // Kept for back-compat with callers/state higher up. The Sidebar no longer
  // renders separate VEDA / public PC dropdowns — those rolled into PCSearchPanel.
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
  /** Ambient STAC mode driven by the global toggle in the header. */
  stacMode?: 'public' | 'pro';
  /** Setter so PCSearchPanel's Public/Private buttons can update the global mode. */
  onStacModeChange?: (mode: 'public' | 'pro') => void;
}

/**
 * Data Catalog sidebar — layout:
 *
 *   1. Microsoft Planetary Computer (PCSearchPanel)
 *        • Public / Private radio (synced with the header StacModeToggle)
 *        • Collection dropdown (Public → bundled PC list; Private → live MPC Pro)
 *        • Location + Time
 *        • Search button → triggers a STAC search routed through chat
 *
 * The previous standalone "Private / My Data (MPC Pro)" box was removed —
 * it duplicated the Private mode inside PCSearchPanel. There is now a single
 * Public/Private control whose state mirrors the header's Pro toggle, so
 * every chat call and every STAC search routes through one `stacMode`.
 */
const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  isLoading,
  onPCSearch,
  stacMode,
  onStacModeChange,
}) => {
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
              marginBottom: '16px',
            }}
            onClick={onToggle}
          >
            Data Catalog
          </div>

          {isLoading ? (
            <div className="loading">Loading datasets...</div>
          ) : (
            <>
              {/* Microsoft Planetary Computer — search panel (Public/Private mode) */}
              {onPCSearch && (
                <PCSearchPanel
                  onSearch={onPCSearch}
                  ambientStacMode={stacMode}
                  onStacModeChange={onStacModeChange}
                />
              )}

              {/* Microsoft Fabric — connect to a workspace + Lakehouse */}
              <FabricConnect />
            </>
          )}
        </>
      )}
    </div>
  );
};

export default Sidebar;
