// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiService, Dataset } from '../services/api';
import Sidebar from './Sidebar';
import Chat from './Chat';
import MapView from './MapView';
import ResizablePanel from './ResizablePanel';
import { AppState } from '../App';

interface MainAppProps {
  appState: AppState;
  onDatasetSelect: (dataset: Dataset) => void;
  onReturnToLanding: () => void;
}

const MainApp: React.FC<MainAppProps> = ({ appState, onDatasetSelect, onReturnToLanding }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastChatResponse, setLastChatResponse] = useState<any>(null);
  const [chatPanelWidth, setChatPanelWidth] = useState(420);
  const [privateSearchTrigger, setPrivateSearchTrigger] = useState<any>(null);

  // Handle chat responses for map integration
  const handleChatResponse = (responseData: any) => {
    console.log('MainApp: Received chat response for map integration:', responseData);
    setLastChatResponse(responseData);
  };

  // Handle chat panel width changes
  const handleChatPanelWidthChange = (width: number) => {
    setChatPanelWidth(width);
    // Update CSS custom property for dynamic grid layout
    document.documentElement.style.setProperty('--chat-panel-width', `${width}px`);
  };

  // Fetch datasets
  const { data: myDatasets = [], isLoading: loadingMyData } = useQuery({
    queryKey: ['myDatasets'],
    queryFn: apiService.getMyDatasets,
  });

  const { data: vedaDatasets = [], isLoading: loadingVeda } = useQuery({
    queryKey: ['vedaDatasets'],
    queryFn: apiService.getVedaDatasets,
  });

  const { data: publicDatasets = [], isLoading: loadingPublic } = useQuery({
    queryKey: ['publicDatasets'],
    queryFn: apiService.getPublicDatasets,
  });

  const { data: planetaryComputerDatasets = [], isLoading: loadingPC } = useQuery({
    queryKey: ['planetaryComputerDatasets'],
    queryFn: apiService.getPlanetaryComputerDatasets,
    enabled: true, // Always load planetary computer datasets
  });

  const isLoading = loadingMyData || loadingVeda || loadingPublic || loadingPC;

  // Update CSS variable for sidebar and chat panel
  useEffect(() => {
    const root = document.documentElement;
    if (sidebarOpen) {
      root.style.setProperty('--side-left', 'var(--side)');
    } else {
      root.style.setProperty('--side-left', '0px');
    }
    // Initialize chat panel width
    root.style.setProperty('--chat-panel-width', `${chatPanelWidth}px`);
  }, [sidebarOpen, chatPanelWidth]);

  const handleToggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const handleDatasetClick = (dataset: Dataset) => {
    onDatasetSelect(dataset);
  };

  const handlePrivateSearch = (query: string, collection?: Dataset) => {
    console.log('MainApp: Private search initiated:', { query, collection });
    
    // Format the query for private data search
    let searchQuery = query;
    if (collection) {
      searchQuery = `Search ${collection.title}: ${query}`;
    }
    
    // Trigger private search in chat component
    setPrivateSearchTrigger({
      isPrivateQuery: true,
      query: searchQuery,
      collection: collection,
      source: 'veda_ai_search',
      timestamp: Date.now() // Ensure it's unique to trigger useEffect
    });
  };

  return (
    <div className="app">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={handleToggleSidebar}
        myDatasets={myDatasets}
        vedaDatasets={vedaDatasets}
        publicDatasets={publicDatasets}
        planetaryComputerDatasets={planetaryComputerDatasets}
        isLoading={isLoading}
        onDatasetSelect={handleDatasetClick}
        selectedDataset={appState.selectedDataset}
        entryTarget={appState.entryTarget}
        onPrivateSearch={handlePrivateSearch}
      />

      <div className="center">
        <MapView
          selectedDataset={appState.selectedDataset}
          lastChatResponse={lastChatResponse}
        />
      </div>

      <ResizablePanel
        defaultWidth={420}
        minWidth={300}
        maxWidth={800}
        onWidthChange={handleChatPanelWidthChange}
        className="chat-panel"
      >
        <Chat
          key={appState.sessionKey} // Force re-render on session restart
          selectedDataset={appState.selectedDataset}
          chatMode={appState.chatMode}
          initialQuery={appState.initialQuery}
          onResponseReceived={handleChatResponse}
          privateSearchTrigger={privateSearchTrigger}
        />
      </ResizablePanel>
    </div>
  );
};

export default MainApp;
