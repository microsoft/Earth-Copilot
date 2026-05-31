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
  selectedModel?: string;
  stacMode?: 'public' | 'pro';
  onStacModeChange?: (mode: 'public' | 'pro') => void;
}

const MainApp: React.FC<MainAppProps> = ({ appState, onDatasetSelect, onReturnToLanding, onRestartSession, geointMode, onGeointToggle, selectedModel, stacMode, onStacModeChange }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastChatResponse, setLastChatResponse] = useState<any>(null);
  const [chatPanelWidth, setChatPanelWidth] = useState(420);
  const [privateSearchTrigger, setPrivateSearchTrigger] = useState<any>(null);
  const [currentPin, setCurrentPin] = useState<{ lat: number; lng: number } | null>(null);
  const [mobilityAnalysisResult, setMobilityAnalysisResult] = useState<any>(null); // New state for mobility results
  const [mobilityPinCoords, setMobilityPinCoords] = useState<{ pinA: { lat: number; lng: number }; pinB: { lat: number; lng: number } } | null>(null); // Pin A/B coordinates for mobility
  const [selectedModule, setSelectedModule] = useState<string | null>(null); // Selected GEOINT module
  const [mapContext, setMapContext] = useState<any>(null); // Map context for Chat Vision
  const [systemMessage, setSystemMessage] = useState<string | null>(null); // System messages for workflow
  const [comparisonUserQuery, setComparisonUserQuery] = useState<string | null>(null); // User's comparison query
  const [awaitingComparisonQuery, setAwaitingComparisonQuery] = useState(false); // Flag to intercept next message
  const [terrainSession, setTerrainSession] = useState<{ sessionId: string | null; lat: number; lng: number } | null>(null); // Terrain session for multi-turn chat
  const [comparisonResult, setComparisonResult] = useState<any>(null); // Comparison analysis result (before/after data)

  // Handle comparison result from Chat component
  const handleComparisonResult = useCallback((result: any) => {
    console.log('MainApp: Comparison result received:', result);
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

    // UI gate: Comparison is not yet production-ready. The backend agent
    // (geoint/comparison_agent.py) and the /api/geoint/comparison endpoint
    // remain available for direct/dev access, but no UI surface activates
    // it. Building Damage is now shipping again (NAIP aerial assessment).
    // Remove this guard when Comparison is ready to ship.
    const DISABLED_MODULES = new Set(['comparison']);
    if (module !== null && DISABLED_MODULES.has(module)) {
      console.warn(
        `[UI] MainApp: module "${module}" is disabled in the UI; ignoring.`
      );
      return;
    }

    setSelectedModule(module);
    
    // DESELECTION: If module is null, reset to regular chat mode
    if (module === null) {
      console.log('[SYNC] MainApp: Module deselected - resetting to regular chat mode');
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
    
    // SELECTION: Enable GEOINT MODE when ANY module is selected
    console.log('[MEDAL] MainApp: GEOINT MODE automatically enabled for module:', module);
    onGeointToggle(true);

    // NOTE: do NOT setSystemMessage(<module> selected) here. MapView.handleModuleSelect
    // already publishes a bolded "**<Module> selected.**" notice through
    // onGeointAnalysis({type:'module_selected'}) which Chat renders. Duplicating
    // the message here produced two back-to-back "Vision selected." bubbles
    // (one plain, one bold). Resilience is the one exception: it's selected
    // from the sidebar, not via MapView, so it gets its own systemMessage
    // below.
    if (module === 'resilience') {
      setSystemMessage('Resilience selected.');
    } else {
      // Clear any stale system message left over from a previous module so
      // we don't replay it when the next selection happens.
      setSystemMessage(null);
    }
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
    console.log('MainApp: Terrain session changed:', session);
    setTerrainSession(session);
  }, []);
  
  // Clear terrain session (called when exiting terrain mode)
  const clearTerrainSession = useCallback(() => {
    console.log('[DEL] MainApp: Clearing terrain session');
    setTerrainSession(null);
  }, []);
  
  // Clear ALL GEOINT sessions (called when starting a new STAC search)
  //
  // NOTE: Resilience is intentionally NOT cleared here. It's a region-scoped
  // module (no pin, no STAC dependency) so navigating the map / running a
  // STAC search shouldn't silently deactivate it. Previously this reset
  // selectedModule to null while leaving the "Resilience module active"
  // banner on screen — the next chat message would then fall through to
  // /api/query instead of /api/resilience/assess and produce a generic
  // clarifier response. Anyone clearing Resilience must do it explicitly.
  const clearAllGeointSessions = useCallback(() => {
    console.log('[DEL] MainApp: Clearing ALL GEOINT sessions for new STAC search');
    // Clear terrain session
    setTerrainSession(null);
    // Clear pin
    setCurrentPin(null);
    setMobilityAnalysisResult(null);
    setComparisonUserQuery(null);
    setAwaitingComparisonQuery(false);
    setComparisonResult(null);
    // Resilience survives map-nav / STAC searches; everything else gets
    // cleared. Use the functional form so we read the latest module value
    // even if multiple events fire in the same React batch.
    setSelectedModule(prev => {
      if (prev === 'resilience') {
        return prev;
      }
      onGeointToggle(false);
      setSystemMessage(null);
      return null;
    });
  }, [onGeointToggle]);
  
  // Listen for STAC query events from GetStartedButton (clears all sessions)
  useEffect(() => {
    const handleStacQueryEvent = (event: CustomEvent<{ query: string; clearSessions: boolean }>) => {
      if (event.detail.clearSessions) {
        console.log('[SYNC] MainApp: Received STAC query event - clearing all GEOINT sessions');
        clearAllGeointSessions();
      }
    };

    // Listen for comparison query events from GetStartedButton
    const handleComparisonQueryEvent = (event: CustomEvent<{ query: string }>) => {
      // UI gate: comparison module is disabled in the UI. The Get Started
      // entry points were removed and `handleModuleSelected('comparison')`
      // is gated, so this listener is dormant — but kept for when the
      // module is re-enabled.
      console.warn(
        'MainApp: comparison-query event ignored — comparison module is UI-disabled.',
        event.detail.query
      );
      return;
    };

    window.addEventListener('planetaryexplorer-stac-query' as any, handleStacQueryEvent as any);
    window.addEventListener('planetaryexplorer-comparison-query' as any, handleComparisonQueryEvent as any);
    return () => {
      window.removeEventListener('planetaryexplorer-stac-query' as any, handleStacQueryEvent as any);
      window.removeEventListener('planetaryexplorer-comparison-query' as any, handleComparisonQueryEvent as any);
    };
  }, [clearAllGeointSessions]);
  
  // Handle mobility analysis result (when pin is dropped and analysis completes)
  const handleMobilityAnalysisResult = (result: any) => {
    console.log('MainApp: Geoint analysis event received', result);
    
    // Extract selected module if provided
    if (result.selectedModule) {
      setSelectedModule(result.selectedModule);
    }
    
    // Check if comparison module is asking for user query
    if (result.type === 'assistant' && result.message && result.message.includes('Comparison Analysis')) {
      console.log('MainApp: Comparison module activated - awaiting user query');
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
      console.log('MainApp: Vision mode ready - awaiting user question in chat');
    } else if (result.type === 'terrain_ready') {
      // Terrain mode: pin dropped and screenshot captured, waiting for user question
      setMobilityAnalysisResult({ type: 'info', message: result.message });
      console.log('MainApp: Terrain pin placed - awaiting user question in chat');
    } else if (result.type === 'mobility_ready') {
      // Mobility: both pins placed, waiting for user question
      setMobilityPinCoords({
        pinA: result.coordinates,
        pinB: result.coordinatesB
      });
      setMobilityAnalysisResult({ type: 'info', message: result.message });
      console.log('[CAR] MainApp: Mobility pins placed - awaiting user question in chat');
    } else if (result.type === 'extreme_weather_ready') {
      // Extreme weather: pin dropped, waiting for user climate question
      setMobilityAnalysisResult({ type: 'info', message: result.message });
      console.log('MainApp: Extreme weather pin placed - awaiting user question in chat');
    } else if (result.type === 'building_damage_ready') {
      // Building damage: pin dropped on building, waiting for user question
      setMobilityAnalysisResult({ type: 'info', message: result.message });
      console.log('MainApp: Building damage pin placed - awaiting user question in chat');
    } else if (result.type === 'module_selected') {
      // Module was selected - show instructional message
      setMobilityAnalysisResult({ type: 'info', message: result.message });
    }
  };

  // Handle user message submission (for comparison query interception)
  const handleUserMessage = (message: string) => {
    console.log('[MSG] MainApp: User message:', message);
    
    // If comparison module is selected OR awaiting comparison query,
    // always route through MapView's comparisonUserQuery flow.
    // This ensures the same pipeline (MapView -> /api/geoint/comparison -> comparisonState)
    // is used whether the query came from Get Started button or typed in chat.
    if (selectedModule === 'comparison' || awaitingComparisonQuery) {
      console.log('MainApp: Forwarding comparison query to MapView (selectedModule=comparison)');
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
        stacMode={stacMode}
        onStacModeChange={onStacModeChange}
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
        maxWidth={1200}
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
          mobilityPinCoords={mobilityPinCoords}
          selectedModule={selectedModule || undefined}
          mapContext={mapContext}
          systemMessage={systemMessage}
          onUserMessage={handleUserMessage}
          terrainSession={terrainSession}
          onTerrainSessionChange={handleTerrainSessionChange}
          onClearTerrainSession={clearTerrainSession}
          onComparisonResult={handleComparisonResult}
          selectedModel={selectedModel}
          stacMode={stacMode}
        />
      </ResizablePanel>
    </div>
  );
};

export default MainApp;
