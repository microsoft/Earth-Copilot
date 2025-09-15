import React, { useState } from 'react';

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
        <div className="landing-center">
          <div className="landing-prompt-box">
            <div className="landing-prompt">What would you like to search?</div>
          </div>
          <form onSubmit={handleSubmit} className="search-form">
            <div className="search-input-container">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder=""
                className="search-input"
              />
              <button type="submit" className="search-button">
                Send
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
