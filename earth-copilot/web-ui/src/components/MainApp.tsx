// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect, useCallback } from 'react';
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
  onRestartSession: () => void;
  geointMode: boolean; // Deprecated - will be removed
  onGeointToggle: (enabled: boolean) => void; // Deprecated - will be removed
}

const MainApp: React.FC<MainAppProps> = ({ appState, onDatasetSelect, onReturnToLanding, onRestartSession, geointMode, onGeointToggle }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastChatResponse, setLastChatResponse] = useState<any>(null);
  const [chatPanelWidth, setChatPanelWidth] = useState(420);
  const [privateSearchTrigger, setPrivateSearchTrigger] = useState<any>(null);
  const [currentPin, setCurrentPin] = useState<{ lat: number; lng: number } | null>(null);
  const [mobilityAnalysisResult, setMobilityAnalysisResult] = useState<any>(null); // New state for mobility results
  const [selectedModule, setSelectedModule] = useState<string | null>(null); // Selected GEOINT module
  const [mapContext, setMapContext] = useState<any>(null); // Map context for Chat Vision
  const [systemMessage, setSystemMessage] = useState<string | null>(null); // System messages for workflow
  const [comparisonUserQuery, setComparisonUserQuery] = useState<string | null>(null); // User's comparison query
  const [awaitingComparisonQuery, setAwaitingComparisonQuery] = useState(false); // Flag to intercept next message
  const [terrainSession, setTerrainSession] = useState<{ sessionId: string | null; lat: number; lng: number } | null>(null); // Terrain session for multi-turn chat
  const [comparisonResult, setComparisonResult] = useState<any>(null); // Comparison analysis result (before/after data)

  // Handle comparison result from Chat component
  const handleComparisonResult = useCallback((result: any) => {
    console.log('📊 MainApp: Comparison result received:', result);
    setComparisonResult(result);
  }, []);

  // Handle modules menu opening
  const handleModulesMenuOpen = () => {
    console.log('MainApp: Modules menu opened');
    setSystemMessage('Please select the geointelligence module for analysis.');
  };

  // Handle module selection OR deselection (toggle off)
  const handleModuleSelected = (module: string | null) => {
    console.log('MainApp: Module changed:', module);
    setSelectedModule(module);
    
    // ✅ DESELECTION: If module is null, reset to regular chat mode
    if (module === null) {
      console.log('🔄 MainApp: Module deselected - resetting to regular chat mode');
      onGeointToggle(false);
      setCurrentPin(null);
      setMobilityAnalysisResult(null);
      setSystemMessage(null);
      setComparisonUserQuery(null);
      setAwaitingComparisonQuery(false);
      setComparisonResult(null);
      clearTerrainSession();
      return;
    }
    
    // ✅ SELECTION: Enable GEOINT MODE when ANY module is selected
    console.log('🎖️ MainApp: GEOINT MODE automatically enabled for module:', module);
    onGeointToggle(true);
    
    // Set appropriate message based on module
    let message = '';
    if (module === 'terrain') {
      message = 'Please click on the map to drop a pin on the location you want to perform terrain analysis.';
    } else if (module === 'mobility') {
      message = 'Please click on the map to drop a pin for mobility analysis.';
    } else if (module === 'building_damage') {
      message = 'Please ensure you are zoomed in and you drop a pin over the building to trigger the analysis.';
    } else if (module === 'comparison') {
      message = 'Please click on the map to drop a pin for change detection analysis.';
    } else if (module === 'timeseries') {
      message = 'Please click on the map to drop a pin for time series animation.';
    } else if (module === 'vision') {
      message = 'Please click on the map to drop a pin for vision analysis.';
    }
    
    setSystemMessage(message);
  };

  // Handle pin changes from MapView
  const handlePinChange = (pin: { lat: number; lng: number } | null) => {
    console.log('MainApp: Pin changed:', pin);
    setCurrentPin(pin);
  };
  
  // Handle map context changes from MapView (for Chat Vision)
  // Wrapped in useCallback to prevent infinite loop in MapView's useEffect
  const handleMapContextChange = useCallback((context: any) => {
    setMapContext(context); // Remove noisy log
  }, []);
  
  // Handle terrain session changes from MapView (for multi-turn terrain chat)
  const handleTerrainSessionChange = useCallback((session: { sessionId: string | null; lat: number; lng: number } | null) => {
    console.log('🌍 MainApp: Terrain session changed:', session);
    setTerrainSession(session);
  }, []);
  
  // Clear terrain session (called when exiting terrain mode)
  const clearTerrainSession = useCallback(() => {
    console.log('🗑️ MainApp: Clearing terrain session');
    setTerrainSession(null);
  }, []);
  
  // Handle mobility analysis result (when pin is dropped and analysis completes)
  const handleMobilityAnalysisResult = (result: any) => {
    console.log('📊 MainApp: Geoint analysis event received', result);
    
    // Extract selected module if provided
    if (result.selectedModule) {
      setSelectedModule(result.selectedModule);
    }
    
    // Check if comparison module is asking for user query
    if (result.type === 'assistant' && result.message && result.message.includes('Comparison Analysis')) {
      console.log('📊 MainApp: Comparison module activated - awaiting user query');
      setAwaitingComparisonQuery(true);
    }
    
    if (result.type === 'pin_dropped') {
      // Pin was dropped - show the notification message
      setMobilityAnalysisResult({ 
        type: 'pin_dropped', 
        message: result.message,
        coordinates: result.coordinates 
      });
    } else if (result.type === 'complete') {
      // Analysis completed
      setMobilityAnalysisResult({ type: 'complete', data: result });
    } else if (result.type === 'pending') {
      // Analysis in progress
      setMobilityAnalysisResult({ type: 'pending', message: result.message });
    } else if (result.type === 'thinking') {
      // Show "Thinking..." indicator while GPT-5 analyzes
      setMobilityAnalysisResult({ type: 'thinking', message: result.message });
    } else if (result.type === 'assistant') {
      // Display terrain analysis results
      setMobilityAnalysisResult({ type: 'assistant', message: result.message });
    } else if (result.type === 'error') {
      // Display error message
      setMobilityAnalysisResult({ type: 'error', message: result.message });
    } else if (result.type === 'info') {
      // Display informational messages (e.g., "Please select a module")
      setMobilityAnalysisResult({ type: 'info', message: result.message });
    } else if (result.type === 'vision_ready') {
      // Vision mode: pin dropped, waiting for user question
      // Show message to user and update chat placeholder
      setMobilityAnalysisResult({ type: 'info', message: result.message });
      console.log('👁️ MainApp: Vision mode ready - awaiting user question in chat');
    } else if (result.type === 'module_selected') {
      // Module was selected - show instructional message
      setMobilityAnalysisResult({ type: 'info', message: result.message });
    }
  };

  // Handle user message submission (for comparison query interception)
  const handleUserMessage = (message: string) => {
    console.log('💬 MainApp: User message:', message);
    
    // If awaiting comparison query, forward to MapView
    if (awaitingComparisonQuery) {
      console.log('📊 MainApp: Forwarding comparison query to MapView');
      setComparisonUserQuery(message);
      setAwaitingComparisonQuery(false);
      return true; // Indicate message was intercepted
    }
    
    return false; // Message not intercepted, proceed normally
  };

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
    queryFn: () => apiService.getMyDatasets(),
    initialData: [],
    staleTime: 60000, // Cache for 1 minute
  });

  const { data: vedaDatasets = [], isLoading: loadingVeda } = useQuery({
    queryKey: ['vedaDatasets'],
    queryFn: () => apiService.getVedaDatasets(),
    initialData: [],
    staleTime: 60000,
  });

  const { data: publicDatasets = [], isLoading: loadingPublic } = useQuery({
    queryKey: ['publicDatasets'],
    queryFn: () => apiService.getPublicDatasets(),
    initialData: [],
    staleTime: 60000,
  });

  const { data: planetaryComputerDatasets = [], isLoading: loadingPC } = useQuery({
    queryKey: ['planetaryComputerDatasets'],
    queryFn: () => apiService.getPlanetaryComputerDatasets(),
    initialData: [],
    enabled: true, // Always load planetary computer datasets
    staleTime: 60000,
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

  const handlePCSearch = async (params: { collection: string; location: string; datetime?: string; datetime_start?: string; datetime_end?: string }) => {
    console.log('MainApp: PC Structured Search initiated:', params);
    
    // Trigger structured search via Chat component
    // The Chat component will receive this and call the /api/structured-search endpoint
    setPrivateSearchTrigger({
      isPrivateQuery: false,
      isPCStructuredSearch: true,
      pcSearchParams: params,
      query: `Planetary Computer: ${params.collection} for ${params.location}`,
      source: 'pc_structured_search',
      timestamp: Date.now()
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
        onPCSearch={handlePCSearch}
      />

      <div className="center">
        <MapView
          selectedDataset={appState.selectedDataset}
          lastChatResponse={lastChatResponse}
          onPinChange={handlePinChange}
          onGeointAnalysis={handleMobilityAnalysisResult}
          onMapContextChange={handleMapContextChange}
          onModulesMenuOpen={handleModulesMenuOpen}
          onModuleSelected={handleModuleSelected}
          onToggleSidebar={handleToggleSidebar}
          sidebarOpen={sidebarOpen}
          comparisonUserQuery={comparisonUserQuery}
          onTerrainSessionChange={handleTerrainSessionChange}
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
          onRestartSession={onRestartSession}
          privateSearchTrigger={privateSearchTrigger}
          currentPin={currentPin}
          geointMode={geointMode}
          mobilityAnalysisResult={mobilityAnalysisResult}
          selectedModule={selectedModule || undefined}
          mapContext={mapContext}
          systemMessage={systemMessage}
          onUserMessage={handleUserMessage}
          terrainSession={terrainSession}
          onClearTerrainSession={clearTerrainSession}
          onComparisonResult={handleComparisonResult}
        />
      </ResizablePanel>
    </div>
  );
};

export default MainApp;
