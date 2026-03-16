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
      <span className="restart-button-label">Restart</span>
    </div>
  );
};

export default RestartButton;
