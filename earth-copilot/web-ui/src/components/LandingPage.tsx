// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import HealthCheckInfo from './HealthCheckInfo';
import STACInfoButton from './STACInfoButton';
import GetStartedButton from './GetStartedButton';
import ModelSelector from './ModelSelector';
import UserAccountMenu from './UserAccountMenu';
import { API_BASE_URL } from '../config/api';

interface LandingPageProps {
  onEnter: (target: string, query?: string) => void;
}

const LandingPage: React.FC<LandingPageProps> = ({ onEnter }) => {
  const [query, setQuery] = useState('');
  const [showWelcomePopup, setShowWelcomePopup] = useState(true);
  const [isPopupVisible, setIsPopupVisible] = useState(false);

  // Check for query parameter in URL on component mount
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const queryParam = urlParams.get('query');
    
    if (queryParam) {
      console.log('[LINK] URL query parameter detected:', queryParam);
      // Auto-enter the app with the query from URL
      onEnter('all', queryParam);
    }
  }, [onEnter]);

  // Show welcome popup with a slight delay for better UX
  useEffect(() => {
    const showTimer = setTimeout(() => {
      setIsPopupVisible(true);
    }, 500);

    // Auto-hide popup after 10 seconds
    const hideTimer = setTimeout(() => {
      setIsPopupVisible(false);
    }, 10500);

    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, []);

  // Dismiss welcome popup when Get Started modal opens
  useEffect(() => {
    const handleGlobalClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      // If user clicked the Get Started button or the modal opened, hide the tooltip
      if (target.closest('.get-started-button') || document.querySelector('.get-started-modal-overlay')) {
        setIsPopupVisible(false);
        setShowWelcomePopup(false);
      }
    };
    document.addEventListener('click', handleGlobalClick, true);
    return () => document.removeEventListener('click', handleGlobalClick, true);
  }, []);

  const handleDismissPopup = () => {
    setIsPopupVisible(false);
  };

  const handleCopilotIconClick = () => {
    // Navigate to map page (same as clicking "Map" button)
    onEnter('map');
  };

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
          <GetStartedButton onQuerySelect={(query) => onEnter('all', query)} />
          <ModelSelector apiBaseUrl={API_BASE_URL} />
          <STACInfoButton />
          <HealthCheckInfo apiBaseUrl={API_BASE_URL} />
          <UserAccountMenu />
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
            </div>
          </form>
        </div>
        <div style={{height: 40}}></div>
      </div>

      {/* Welcome Popup with Copilot Icon */}
      {showWelcomePopup && (
        <div 
          className="welcome-popup-container"
          style={{
            position: 'fixed',
            top: '52px',
            right: '24px',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: '12px'
          }}
        >
          {/* Tooltip pointing to Get Started */}
          <div 
            className={`welcome-tooltip ${isPopupVisible ? 'visible' : ''}`}
            style={{
              background: 'rgba(30, 58, 95, 0.15)',
              backdropFilter: 'blur(8px)',
              color: '#1e3a5f',
              padding: '14px 18px',
              borderRadius: '12px',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)',
              maxWidth: '300px',
              position: 'relative',
              opacity: isPopupVisible ? 1 : 0,
              transform: isPopupVisible ? 'translateY(0) scale(1)' : 'translateY(-10px) scale(0.95)',
              transition: 'all 0.3s ease',
              pointerEvents: isPopupVisible ? 'auto' : 'none',
              border: '1px solid rgba(96, 165, 250, 0.2)'
            }}
          >
            <button 
              onClick={handleDismissPopup}
              style={{
                position: 'absolute',
                top: '8px',
                right: '8px',
                background: 'none',
                border: 'none',
                color: 'rgba(30, 58, 95, 0.5)',
                fontSize: '16px',
                cursor: 'pointer',
                padding: '4px',
                lineHeight: 1
              }}
              title="Dismiss"
            >
              ×
            </button>
            <div style={{ marginBottom: '10px', fontSize: '14px', fontWeight: 600, color: '#1e3a5f' }}>
              Welcome to Earth Copilot!
            </div>
            <div style={{ fontSize: '12px', lineHeight: 1.5, color: 'rgba(30, 58, 95, 0.8)' }}>
              To get started, try the example queries in the{' '}
              <span 
                style={{ 
                  color: '#1e40af', 
                  fontWeight: 700,
                  cursor: 'pointer',
                  textDecoration: 'underline'
                }}
                onClick={() => {
                  const getStartedBtn = document.querySelector('.get-started-button') as HTMLElement;
                  if (getStartedBtn) {
                    getStartedBtn.click();
                    handleDismissPopup();
                  }
                }}
              >
                Get Started
              </span>{' '}
              button above.
            </div>
            {/* Arrow pointing up toward Get Started button */}
            <div 
              style={{
                position: 'absolute',
                top: '-8px',
                right: '28px',
                width: 0,
                height: 0,
                borderLeft: '8px solid transparent',
                borderRight: '8px solid transparent',
                borderBottom: '8px solid rgba(30, 58, 95, 0.15)'
              }}
            />
          </div>
        </div>
      )}

      {/* Copilot Map Icon Button - Bottom Right */}
      <div
        onClick={handleCopilotIconClick}
        style={{
          position: 'fixed',
          bottom: '32px',
          right: '32px',
          zIndex: 1000,
          width: '56px',
          height: '56px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          boxShadow: '0 4px 20px rgba(59, 130, 246, 0.5)',
          transition: 'all 0.3s ease',
          border: '3px solid rgba(255, 255, 255, 0.2)'
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'scale(1.1)';
          e.currentTarget.style.boxShadow = '0 6px 28px rgba(59, 130, 246, 0.6)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'scale(1)';
          e.currentTarget.style.boxShadow = '0 4px 20px rgba(59, 130, 246, 0.5)';
        }}
        title="Open Earth Copilot Map"
      >
        <svg 
          width="28" 
          height="28" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="white" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
      </div>
    </div>
  );
};

export default LandingPage;
