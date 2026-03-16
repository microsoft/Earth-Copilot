// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { apiService } from '../services/api';
import STACInfoButton from './STACInfoButton';

interface IntelligentLandingPageProps {
  onRouteResult?: (result: any) => void;
}

const IntelligentLandingPage: React.FC<IntelligentLandingPageProps> = ({ onRouteResult }) => {
  const [query, setQuery] = useState('');
  const [routingResult, setRoutingResult] = useState<any>(null);

  const routingMutation = useMutation({
    mutationFn: async (query: string) => {
      console.log('Routing mutation starting with query:', query);
      try {
        const result = await apiService.routeQuery(query);
        console.log('Routing mutation API response:', result);
        return result;
      } catch (error) {
        console.error('Routing mutation API error:', error);
        throw error;
      }
    },
    onSuccess: (result) => {
      console.log('Routing mutation onSuccess called with result:', result);
      setRoutingResult(result);
      
      // Notify parent component if callback provided
      if (onRouteResult) {
        onRouteResult(result);
      }
      
      // Auto-redirect after showing the result for a moment
      setTimeout(() => {
        window.location.href = result.redirect_url;
      }, 2000);
    },
    onError: (error) => {
      console.error('Routing mutation onError called with error:', error);
      // Fallback: redirect to general copilot
      setTimeout(() => {
        window.location.href = `/geocopilot?source=planetary_computer&query=${encodeURIComponent(query)}`;
      }, 1000);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    routingMutation.mutate(query);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  const exampleQueries = [
    {
      text: "Show me recent wildfire data in California",
      icon: "",
      expectedSource: "fire_events"
    },
    {
      text: "Find Landsat imagery for forest change analysis",
      icon: "",
      expectedSource: "planetary_computer"
    },
    {
      text: "Access NASA climate data for the Arctic region",
      icon: "",
      expectedSource: "veda"
    },
    {
      text: "Search our internal geospatial datasets",
      icon: "",
      expectedSource: "azure_search"
    }
  ];

  return (
    <div style={{ 
      minHeight: '100vh', 
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem'
    }}>
      <div style={{
        background: 'white',
        borderRadius: '1rem',
        padding: '3rem',
        maxWidth: '800px',
        width: '100%',
        boxShadow: '0 20px 40px rgba(0,0,0,0.1)'
      }}>
        
        {/* Header */}
        <div style={{ position: 'relative', textAlign: 'center', marginBottom: '3rem' }}>
          {/* STAC Info Button - positioned in top right */}
          <div style={{ position: 'absolute', top: 0, right: 0 }}>
            <STACInfoButton />
          </div>
          
          <h1 style={{ 
            fontSize: '3rem', 
            margin: 0, 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            fontWeight: 'bold'
          }}>
            Earth Copilot
          </h1>
          <p style={{ 
            fontSize: '1.2rem', 
            color: '#666', 
            margin: '1rem 0 0 0',
            lineHeight: 1.6
          }}>
            Ask me anything about Earth science data. I'll intelligently route you to the best data source and interface.
          </p>
        </div>

        {!routingResult && !routingMutation.isPending && (
          <>
            {/* Main Query Input */}
            <form onSubmit={handleSubmit} style={{ marginBottom: '2rem' }}>
              <div style={{ position: 'relative' }}>
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="What Earth science data are you looking for? e.g., 'Show me satellite imagery of Amazon deforestation' or 'Find active wildfires in my area'"
                  style={{
                    width: '100%',
                    padding: '1.5rem',
                    fontSize: '1.1rem',
                    border: '2px solid #e0e0e0',
                    borderRadius: '1rem',
                    resize: 'none',
                    minHeight: '4rem',
                    fontFamily: 'inherit',
                    boxSizing: 'border-box',
                    transition: 'border-color 0.3s ease'
                  }}
                  disabled={routingMutation.isPending}
                />
                <button
                  type="submit"
                  disabled={!query.trim() || routingMutation.isPending}
                  style={{
                    position: 'absolute',
                    right: '1rem',
                    bottom: '1rem',
                    padding: '0.75rem 1.5rem',
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '0.5rem',
                    cursor: query.trim() && !routingMutation.isPending ? 'pointer' : 'not-allowed',
                    opacity: query.trim() && !routingMutation.isPending ? 1 : 0.6,
                    fontSize: '1rem',
                    fontWeight: 'bold',
                    transition: 'opacity 0.3s ease'
                  }}
                >
                  Analyze →
                </button>
              </div>
            </form>

            {/* Example Queries */}
            <div>
              <h3 style={{ color: '#333', marginBottom: '1rem' }}>
                Try these examples:
              </h3>
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                gap: '1rem'
              }}>
                {exampleQueries.map((example, index) => (
                  <button
                    key={index}
                    onClick={() => setQuery(example.text)}
                    style={{
                      padding: '1rem',
                      border: '1px solid #e0e0e0',
                      borderRadius: '0.5rem',
                      background: 'white',
                      textAlign: 'left',
                      cursor: 'pointer',
                      transition: 'all 0.3s ease'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '1.5rem' }}>{example.icon}</span>
                      <span style={{ fontSize: '0.9rem', color: '#333' }}>
                        {example.text}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {/* Loading State */}
        {routingMutation.isPending && (
          <div style={{ textAlign: 'center', padding: '3rem' }}>
            <div style={{ 
              fontSize: '3rem', 
              marginBottom: '1rem',
              animation: 'spin 2s linear infinite'
            }}>
              
            </div>
            <h3 style={{ color: '#333', marginBottom: '0.5rem' }}>
              Analyzing your query...
            </h3>
            <p style={{ color: '#666' }}>
              Using intelligent routing to find the best data source for you
            </p>
          </div>
        )}

        {/* Routing Result */}
        {routingResult && (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>
              ✓
            </div>
            <h3 style={{ color: '#333', marginBottom: '1rem' }}>
              Perfect! I found the right data source for you
            </h3>
            <div style={{
              background: '#f8f9fa',
              padding: '1.5rem',
              borderRadius: '0.5rem',
              marginBottom: '1.5rem',
              textAlign: 'left'
            }}>
              <p><strong>Data Source:</strong> {routingResult.primary_source}</p>
              <p><strong>Confidence:</strong> {Math.round(routingResult.confidence * 100)}%</p>
              <p><strong>Reasoning:</strong> {routingResult.reasoning}</p>
            </div>
            <p style={{ color: '#666', marginBottom: '1rem' }}>
              Redirecting you to the specialized Copilot interface...
            </p>
            <div style={{ 
              display: 'inline-block',
              padding: '0.5rem 1rem',
              background: '#667eea',
              color: 'white',
              borderRadius: '0.25rem',
              fontSize: '0.9rem'
            }}>
              Loading Copilot...
            </div>
          </div>
        )}
      </div>

      <style>
        {`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}
      </style>
    </div>
  );
};

export default IntelligentLandingPage;
