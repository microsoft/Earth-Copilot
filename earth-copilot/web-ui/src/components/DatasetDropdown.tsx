// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState } from 'react';
import { Dataset } from '../services/api';

interface DatasetDropdownProps {
  datasets: Dataset[];
  selectedDataset: Dataset | null;
  onDatasetSelect: (dataset: Dataset) => void;
  placeholder?: string;
}

const DatasetDropdown: React.FC<DatasetDropdownProps> = ({
  datasets,
  selectedDataset,
  onDatasetSelect,
  placeholder = "Select a dataset..."
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleToggle = () => {
    setIsOpen(!isOpen);
  };

  const handleSelect = (dataset: Dataset) => {
    onDatasetSelect(dataset);
    setIsOpen(false);
  };

  return (
    <div className="dataset-dropdown">
      <button
        className={`dropdown-button ${isOpen ? 'open' : ''}`}
        onClick={handleToggle}
      >
        <span>{selectedDataset ? selectedDataset.title : placeholder}</span>
        <span className={`dropdown-arrow ${isOpen ? 'open' : ''}`}>▼</span>
      </button>
      
      {isOpen && (
        <div className="dropdown-menu">
          {Array.isArray(datasets) && datasets.map((dataset) => (
            <div
              key={dataset.id}
              className={`dropdown-item ${selectedDataset?.id === dataset.id ? 'selected' : ''}`}
              onClick={() => handleSelect(dataset)}
            >
              {dataset.title}
            </div>
          ))}
          {(!Array.isArray(datasets) || datasets.length === 0) && (
            <div className="dropdown-item" style={{ color: '#666', fontStyle: 'italic' }}>
              No datasets available
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DatasetDropdown;
