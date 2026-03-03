// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Header from './components/Header';
import LandingPage from './components/LandingPage';
import MainApp from './components/MainApp';
import { GlobalStyles } from './styles/GlobalStyles';

const queryClient = new QueryClient();

export interface AppState {
  entered: boolean;
  entryTarget: string | null;
  selectedDataset: any | null;
  chatMode: boolean;
  initialQuery?: string;
  sessionKey?: number;
}

function App() {
  const [appState, setAppState] = useState<AppState>({
    entered: false,
    entryTarget: null,
    selectedDataset: null,
    chatMode: false,
    initialQuery: undefined,
    sessionKey: 1
  });

  const [geointMode, setGeointMode] = useState<boolean>(false);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    // Load from localStorage, default to gpt-5
    return localStorage.getItem('earthcopilot-model') || 'gpt-5';
  });

  const handleModelChange = (modelId: string) => {
    console.log(' App: Model changed to:', modelId);
    setSelectedModel(modelId);
    localStorage.setItem('earthcopilot-model', modelId);
  };

  const handleEnterApp = (target: string, query?: string) => {
    setAppState(prev => ({ 
      ...prev, 
      entered: true, 
      entryTarget: target,
      initialQuery: query,
      chatMode: !!query // Enable chat mode if there's a query
    }));
  };

  const handleReturnToLanding = () => {
    setAppState({ entered: false, entryTarget: null, selectedDataset: null, chatMode: false, initialQuery: undefined });
  };

  const handleRestartSession = () => {
    // Clear chat and dataset selection but stay in the app
    // Force chat component to re-render by updating session key
    setAppState(prev => ({ 
      ...prev, 
      selectedDataset: null, 
      chatMode: false, 
      initialQuery: undefined,
      sessionKey: Date.now() // Add session key to force re-render
    }));
    //  Also reset GEOINT mode to simulate fresh page load
    setGeointMode(false);
  };

  const handleDatasetSelect = (dataset: any) => {
    setAppState(prev => ({ ...prev, selectedDataset: dataset, chatMode: true }));
  };

  return (
    <QueryClientProvider client={queryClient}>
      <GlobalStyles />
      <div className="app-container">
        {!appState.entered ? (
          <LandingPage onEnter={handleEnterApp} />
        ) : (
          <>
            <Header 
              onReturnToLanding={handleReturnToLanding}
              onRestartSession={handleRestartSession}
              onModelChange={handleModelChange}
              selectedModel={selectedModel}
            />
            <MainApp 
              appState={appState}
              onDatasetSelect={handleDatasetSelect}
              onReturnToLanding={handleReturnToLanding}
              onRestartSession={handleRestartSession}
              geointMode={geointMode}
              onGeointToggle={setGeointMode}
              selectedModel={selectedModel}
            />
          </>
        )}
      </div>
    </QueryClientProvider>
  );
}

export default App;
