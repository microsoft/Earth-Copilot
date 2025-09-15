import React from 'react';

interface HeaderProps {
  onReturnToLanding: () => void;
  onRestartSession: () => void;
}

const MicrosoftLogo: React.FC = () => (
  <svg width="20" height="20" viewBox="0 0 22 22" aria-label="Microsoft logo" role="img">
    <rect x="0" y="0" width="10" height="10" fill="#F25022" />
    <rect x="12" y="0" width="10" height="10" fill="#7FBA00" />
    <rect x="0" y="12" width="10" height="10" fill="#00A4EF" />
    <rect x="12" y="12" width="10" height="10" fill="#FFB900" />
  </svg>
);

const Header: React.FC<HeaderProps> = ({ onReturnToLanding, onRestartSession }) => {
  const handleRestartSession = () => {
    // Clear chat and dataset selection but stay in the app
    onRestartSession();
  };

  return (
    <div className="top-header">
      <div style={{ padding: '0 16px' }}>
        <div className="brand" onClick={onReturnToLanding} style={{cursor:'pointer', transition:'opacity 0.2s ease'}}
             onMouseEnter={(e) => (e.target as HTMLElement).style.opacity = '0.8'}
             onMouseLeave={(e) => (e.target as HTMLElement).style.opacity = '1'}>
          <MicrosoftLogo />
          <div className="brand-name">Microsoft | Earth Copilot</div>
        </div>
      </div>
      <div className="top-title"></div>
      <div style={{ padding: '0 16px', display: 'flex', justifyContent: 'flex-end', width: '100%' }}>
        <button 
          onClick={handleRestartSession}
          style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
            padding: '8px 16px',
            fontSize: '13px',
            color: '#374151',
            cursor: 'pointer',
            fontWeight: '500',
            transition: 'all 0.2s ease',
            boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)'
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLElement).style.background = '#f9fafb';
            (e.target as HTMLElement).style.transform = 'translateY(-1px)';
            (e.target as HTMLElement).style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.15)';
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLElement).style.background = '#ffffff';
            (e.target as HTMLElement).style.transform = 'translateY(0)';
            (e.target as HTMLElement).style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)';
          }}
        >
          🔄 Restart Session
        </button>
      </div>
    </div>
  );
};

export default Header;
