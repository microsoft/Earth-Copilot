// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';
import STACInfoButton from './STACInfoButton';
import HealthCheckInfo from './HealthCheckInfo';
import RestartButton from './RestartButton';
import { API_BASE_URL } from '../config/api';

interface HeaderProps {
  onReturnToLanding: () => void;
  onRestartSession?: () => void;
}

const MicrosoftLogo: React.FC = () => (
  <svg width="32" height="32" viewBox="0 0 22 22" aria-label="Microsoft logo" role="img">
    <rect x="0" y="0" width="10" height="10" fill="#F35325" />
    <rect x="12" y="0" width="10" height="10" fill="#81BC06" />
    <rect x="0" y="12" width="10" height="10" fill="#05A6F0" />
    <rect x="12" y="12" width="10" height="10" fill="#FFBA08" />
  </svg>
);

const Header: React.FC<HeaderProps> = ({ onReturnToLanding, onRestartSession }) => {
  return (
    <div className="top-header">
      <div style={{ padding: '0', paddingLeft: '4px' }}>
        <div className="brand" onClick={onReturnToLanding} style={{cursor:'pointer', transition:'opacity 0.2s ease'}}
             onMouseEnter={(e) => (e.target as HTMLElement).style.opacity = '0.8'}
             onMouseLeave={(e) => (e.target as HTMLElement).style.opacity = '1'}>
          <MicrosoftLogo />
          <div className="brand-name">Microsoft | Earth Copilot</div>
        </div>
      </div>
      <div style={{ 
        padding: '0', 
        display: 'flex', 
        justifyContent: 'flex-end', 
        alignItems: 'center', 
        gap: '12px',
        position: 'absolute',
        top: '16px',
        right: '24px',
        zIndex: 100
      }}>
        <STACInfoButton />
        <HealthCheckInfo apiBaseUrl={API_BASE_URL} />
        {onRestartSession && <RestartButton onRestart={onRestartSession} />}
      </div>
      <style>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 1;
          }
          50% {
            opacity: 0.5;
          }
        }
      `}</style>
    </div>
  );
};

export default Header;
