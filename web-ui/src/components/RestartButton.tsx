// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';
import './RestartButton.css';

interface RestartButtonProps {
  onRestart: () => void;
}

const RestartButton: React.FC<RestartButtonProps> = ({ onRestart }) => {
  return (
    <div 
      className="restart-button"
      onClick={onRestart}
      title="Clear chat and start a new session"
    >
      <svg 
        width="20" 
        height="20" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        strokeWidth="2"
        strokeLinecap="round" 
        strokeLinejoin="round"
      >
        <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
      </svg>
      <span className="restart-button-label">Restart</span>
    </div>
  );
};

export default RestartButton;
