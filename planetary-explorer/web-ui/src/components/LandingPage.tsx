// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import HealthCheckInfo from './HealthCheckInfo';
import STACInfoButton from './STACInfoButton';
import GetStartedButton from './GetStartedButton';
import ModelSelector from './ModelSelector';
import UserAccountMenu from './UserAccountMenu';
import StacModeToggle, { StacMode } from './StacModeToggle';
import { API_BASE_URL } from '../config/api';

interface LandingPageProps {
  onEnter: (target: string, query?: string) => void;
  // Optional so existing call sites that don't care about STAC routing
  // (e.g. tests, storybook) still compile; App.tsx always passes these.
  stacMode?: StacMode;
  onStacModeChange?: (next: StacMode) => void;
  /** Surfaced from /api/config.features.mpcPro. When false the toggle renders
   *  in a locked state with a "How to enable" link. */
  proEnabled?: boolean;
}

const LandingPage: React.FC<LandingPageProps> = ({ onEnter, stacMode, onStacModeChange, proEnabled }) => {
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
            {/* Brand mark: satellite-earth icon only. The Microsoft 4-color
                square overlay was removed per product direction so the
                brand reads as "Planetary Explorer" rather than a Microsoft
                sub-brand. */}
            <span style={{ display: 'inline-block', width: 38, height: 38 }}>
              <img
                src="/icon.png"
                alt="Planetary Explorer"
                width={38}
                height={38}
                style={{ display: 'block', background: 'transparent' }}
              />
            </span>
            <span>Planetary Explorer</span>
          </div>
        </div>
        <div className="landing-top-right">
          <GetStartedButton onQuerySelect={(query) => onEnter('all', query)} />
          <ModelSelector apiBaseUrl={API_BASE_URL} />
          {stacMode && onStacModeChange && (
            <StacModeToggle mode={stacMode} onChange={onStacModeChange} proEnabled={proEnabled} />
          )}
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
              {/*
                Map button: skip the prompt and jump straight to the
                chat/map page with no initial query. Same color treatment
                as Send so they read as a paired action, but rendered as
                an icon-only square button so the affordance is visually
                obvious (a folded-map glyph) without competing with the
                Send text label.
              */}
              <button
                type="button"
                className="search-button"
                onClick={() => onEnter('all')}
                aria-label="Open map view"
                title="Open map view"
                style={{
                  width: 48,
                  height: 48,
                  padding: 0,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                  background: 'linear-gradient(135deg, #60A5FA 0%, #3B82F6 100%)',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 2px 8px rgba(59, 130, 246, 0.3)',
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
                {/* Folded-map icon (Feather "map"): three column-folds
                    with a slight perspective. Tinted white via
                    stroke="currentColor" + the button's color. */}
                <svg
                  width={22}
                  height={22}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
                  <line x1="8" y1="2" x2="8" y2="18" />
                  <line x1="16" y1="6" x2="16" y2="22" />
                </svg>
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
              Welcome to Planetary Explorer!
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

    </div>
  );
};

export default LandingPage;
