// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect, useRef } from 'react';
import './ModelSelector.css';
import { authenticatedFetch } from '../services/authHelper';

interface ModelOption {
  id: string;
  name: string;
  isDefault?: boolean;
  isAvailable?: boolean;
}

interface ModelSelectorProps {
  onModelChange?: (modelId: string) => void;
  selectedModel?: string;
  apiBaseUrl?: string;
}

const DEFAULT_MODELS: ModelOption[] = [
  {
    id: 'gpt-5',
    name: 'GPT-5',
    isDefault: true,
    isAvailable: true
  }
];

const ModelSelector: React.FC<ModelSelectorProps> = ({ onModelChange, selectedModel, apiBaseUrl = '' }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [models, setModels] = useState<ModelOption[]>(DEFAULT_MODELS);
  const [currentModel, setCurrentModel] = useState<string>(
    selectedModel || DEFAULT_MODELS.find(m => m.isDefault)?.id || 'gpt-5'
  );
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch available models from health endpoint
  useEffect(() => {
    const fetchAvailableModels = async () => {
      try {
        const response = await authenticatedFetch(`${apiBaseUrl}/api/health`);
        const data = await response.json();
        // Backend returns 'checks' (not 'connectivity_tests'), and doesn't include available_models list.
        // If the OpenAI service is configured/connected, mark gpt-5 as available.
        const openaiStatus = data.checks?.azure_openai?.status || data.connectivity_tests?.azure_openai?.status;
        const isOpenAiOk = ['connected', 'configured', 'healthy', 'ok'].includes(openaiStatus?.toLowerCase() || '');
        
        if (isOpenAiOk) {
          // Mark gpt-5 as available since OpenAI is configured
          setModels(prevModels => 
            prevModels.map(model => ({
              ...model,
              isAvailable: model.id === 'gpt-5' ? true : model.isAvailable ?? false
            }))
          );
        }
      } catch (err) {
        console.error('Failed to fetch model availability:', err);
      }
    };

    fetchAvailableModels();
    // Refresh every 30 seconds
    const interval = setInterval(fetchAvailableModels, 30000);
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Store model preference in localStorage
  useEffect(() => {
    localStorage.setItem('earthcopilot-model', currentModel);
  }, [currentModel]);

  // Load model preference from localStorage on mount
  useEffect(() => {
    const savedModel = localStorage.getItem('earthcopilot-model');
    if (savedModel && models.find(m => m.id === savedModel)) {
      setCurrentModel(savedModel);
      onModelChange?.(savedModel);
    }
  }, []);

  const handleModelSelect = (modelId: string) => {
    const model = models.find(m => m.id === modelId);
    // Only allow selecting available models
    if (model?.isAvailable) {
      setCurrentModel(modelId);
      setIsOpen(false);
      onModelChange?.(modelId);
    }
  };

  const currentModelInfo = models.find(m => m.id === currentModel);

  return (
    <div className="model-selector" ref={dropdownRef}>
      <div 
        className="model-selector-button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        title="Select AI Model"
      >
        <span className="model-selector-label">Models</span>
      </div>
      
      {isOpen && (
        <div className="model-dropdown">
          <ul className="model-list" role="listbox">
            {models.map((model) => (
              <li
                key={model.id}
                className={`model-option ${currentModel === model.id ? 'selected' : ''} ${!model.isAvailable ? 'unavailable' : ''}`}
                onClick={() => handleModelSelect(model.id)}
                role="option"
                aria-selected={currentModel === model.id}
                aria-disabled={!model.isAvailable}
                style={{ opacity: model.isAvailable ? 1 : 0.5 }}
              >
                <span className="model-option-name">{model.name}</span>
                <span 
                  className="model-availability-dot"
                  style={{ 
                    backgroundColor: model.isAvailable ? '#4CAF50' : '#F44336',
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    marginLeft: '8px',
                    display: 'inline-block'
                  }}
                  title={model.isAvailable ? 'Available' : 'Not Deployed'}
                />
                {currentModel === model.id && <span className="check-mark">✓</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default ModelSelector;
