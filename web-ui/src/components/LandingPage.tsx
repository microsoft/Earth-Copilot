// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import HealthCheckInfo from './HealthCheckInfo';
import STACInfoButton from './STACInfoButton';
import { API_BASE_URL } from '../config/api';

interface LandingPageProps {
  onEnter: (target: string, query?: string) => void;
}

const LandingPage: React.FC<LandingPageProps> = ({ onEnter }) => {
  const [query, setQuery] = useState('');

  const handleVedaClick = () => {
    window.open('http://localhost:3000', '_blank');
  };

  const handleLogoClick = () => {
    // Since we're already on the landing page, just refresh
    window.location.reload();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onEnter('all', query.trim());
    }
  };

  const handleChatWithMap = () => {
    // Navigate to map page with empty chat (no initial query)
    onEnter('map');
  };

  return (
    <div className="landing">
      <div className="landing-bg" />
      <div className="landing-content">
        <div className="landing-top-left">
          <div className="landing-title" 
               style={{cursor:'pointer', transition:'opacity 0.2s ease'}} 
               onClick={handleLogoClick}
               onMouseEnter={(e) => (e.target as HTMLElement).style.opacity = '0.8'}
               onMouseLeave={(e) => (e.target as HTMLElement).style.opacity = '1'}>
            <svg width="28" height="28" viewBox="0 0 22 22" aria-label="Microsoft logo" role="img">
              <rect x="0" y="0" width="10" height="10" fill="#F25022" />
              <rect x="12" y="0" width="10" height="10" fill="#7FBA00" />
              <rect x="0" y="12" width="10" height="10" fill="#00A4EF" />
              <rect x="12" y="12" width="10" height="10" fill="#FFB900" />
            </svg>
            <span>Microsoft | Earth Copilot</span>
          </div>
        </div>
        <div className="landing-top-right">
          <STACInfoButton />
          <HealthCheckInfo apiBaseUrl={API_BASE_URL} />
        </div>
        <div className="landing-center">
          <div className="landing-prompt-box">
            <div className="landing-prompt">
              What would you like to search?
            </div>
          </div>
          <form onSubmit={handleSubmit} className="search-form">
            <div className="search-input-container" style={{ display: 'flex', gap: '6px', width: '100%', maxWidth: '900px', margin: '0 auto' }}>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder=""
                className="search-input"
                style={{
                  flex: 1,
                  minWidth: 0,
                  padding: '12px 16px',
                  fontSize: '16px',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px',
                  outline: 'none'
                }}
              />
              <button 
                type="submit" 
                className="search-button"
                style={{
                  padding: '12px 32px',
                  fontSize: '16px',
                  fontWeight: 500,
                  color: 'white',
                  background: 'linear-gradient(135deg, #60A5FA 0%, #3B82F6 100%)',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 2px 8px rgba(59, 130, 246, 0.3)',
                  whiteSpace: 'nowrap',
                  flexShrink: 0
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(59, 130, 246, 0.4)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, #60A5FA 0%, #3B82F6 100%)';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(59, 130, 246, 0.3)';
                }}
              >
                Send
              </button>
              <button 
                type="button"
                onClick={handleChatWithMap}
                style={{
                  padding: '12px 16px',
                  fontSize: '20px',
                  fontWeight: 500,
                  color: '#374151',
                  background: 'linear-gradient(135deg, #E5E7EB 0%, #D1D5DB 100%)',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, #D1D5DB 0%, #9CA3AF 100%)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(135deg, #E5E7EB 0%, #D1D5DB 100%)';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.1)';
                }}
                title="Go to Map"
              >
                <svg 
                  width="22" 
                  height="22" 
                  viewBox="0 0 24 24" 
                  fill="currentColor"
                >
                  <path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/>
                </svg>
              </button>
            </div>
          </form>
        </div>
        <div style={{height: 40}}></div>
      </div>
    </div>
  );
};

export default LandingPage;
