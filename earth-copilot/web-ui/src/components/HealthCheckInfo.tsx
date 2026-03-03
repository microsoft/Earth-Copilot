// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect } from 'react';
import './HealthCheckInfo.css';
import { authenticatedFetch } from '../services/authHelper';

interface HealthCheckData {
  status: string;
  timestamp: string;
  message?: string;
  version?: string;
  basic_checks?: {
    semantic_kernel?: boolean;
    geoint?: boolean;
    azure_openai_endpoint?: boolean;
    azure_openai_api_key?: boolean;
    azure_openai_deployment?: boolean;
    azure_maps_key?: boolean;
    use_managed_identity?: boolean;
  };
  // Backend may return either 'checks' or 'connectivity_tests'
  checks?: {
    azure_openai?: { status: string; endpoint?: string; model?: string; available_models?: string[] };
    stac_api?: { status: string; api_url?: string };
    azure_maps?: { status: string };
  };
  connectivity_tests?: {
    azure_openai?: { status: string; endpoint?: string; model?: string; available_models?: string[] };
    stac_api?: { status: string; api_url?: string };
    azure_maps?: { status: string };
  };
}

/** Check if a service status indicates it's working */
const isServiceOk = (status?: string): boolean => {
  if (!status) return false;
  return ['connected', 'configured', 'healthy', 'ok'].includes(status.toLowerCase());
};

interface HealthCheckInfoProps {
  apiBaseUrl?: string;
}

const HealthCheckInfo: React.FC<HealthCheckInfoProps> = ({ 
  apiBaseUrl = 'http://localhost:8000' 
}) => {
  const [healthData, setHealthData] = useState<HealthCheckData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const [hasInitialLoad, setHasInitialLoad] = useState(false);

  useEffect(() => {
    fetchHealthCheck();
    // Refresh health check every 30 seconds
    const interval = setInterval(fetchHealthCheck, 30000);
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  const fetchHealthCheck = async () => {
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/api/health`);
      const data = await response.json();
      setHealthData(data);
      setError(null);
      setHasInitialLoad(true);
    } catch (err) {
      setError('Unable to connect to backend');
      console.error('Health check failed:', err);
      setHasInitialLoad(true);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'healthy':
      case 'connected':
        return '#4CAF50';
      case 'degraded':
        return '#FF9800';
      case 'unhealthy':
      case 'failed':
      case 'error':
        return '#F44336';
      default:
        return '#9E9E9E';
    }
  };

  const getStatusIcon = (status: string): string => {
    switch (status) {
      case 'healthy':
      case 'connected':
        return '✓';
      case 'degraded':
        return '⚠';
      case 'unhealthy':
      case 'failed':
      case 'error':
        return '✗';
      default:
        return 'ℹ️';
    }
  };

  const renderHealthTooltip = () => {
    if (!healthData) {
      return (
        <div className="health-tooltip">
          <div className="health-tooltip-header">
            <span className="health-tooltip-title">System Status</span>
          </div>
          <div className="health-tooltip-content">
            {loading ? (
              <div className="health-status-item">
                <span>Loading health status...</span>
              </div>
            ) : (
              <div className="health-status-item error">
                <span>{error || 'Unable to fetch health status'}</span>
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className="health-tooltip">
        <div className="health-tooltip-header">
          <span className="health-tooltip-title">System Status</span>
          <span 
            className="health-status-badge"
            style={{ backgroundColor: getStatusColor(healthData.status) }}
          >
            {getStatusIcon(healthData.status)} {healthData.status.toUpperCase()}
          </span>
        </div>
        
        <div className="health-tooltip-content">
          <div className="health-section">
            <div className="health-section-title">Core Services</div>
            
            {(() => {
              // Backend may return 'checks' or 'connectivity_tests'
              const svc = healthData.checks || healthData.connectivity_tests || {};
              return (
                <>
                  <div className="health-status-item">
                    <span className="health-label">AI Model:</span>
                    <span className={`health-value ${isServiceOk(svc.azure_openai?.status) ? 'success' : 'error'}`}>
                      {isServiceOk(svc.azure_openai?.status) ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>

                  <div className="health-status-item">
                    <span className="health-label">Planetary Computer:</span>
                    <span className={`health-value ${isServiceOk(svc.stac_api?.status) ? 'success' : 'error'}`}>
                      {isServiceOk(svc.stac_api?.status) ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>

                  <div className="health-status-item">
                    <span className="health-label">Azure Maps:</span>
                    <span className={`health-value ${isServiceOk(svc.azure_maps?.status) ? 'success' : 'error'}`}>
                      {isServiceOk(svc.azure_maps?.status) ? 'Connected' : 'Disconnected'}
                    </span>
                  </div>
                </>
              );
            })()}
          </div>

          <div className="health-section">
            <div className="health-section-title">Last Check</div>
            
            <div className="health-status-item">
              <span className="health-value">{new Date(healthData.timestamp).toLocaleString('en-US', { 
                timeZone: 'America/New_York',
                month: '2-digit', 
                day: '2-digit', 
                year: 'numeric', 
                hour: '2-digit', 
                minute: '2-digit', 
                second: '2-digit',
                hour12: false
              })} EST</span>
            </div>
          </div>

          <div className="health-info-footer">
            <span style={{ fontSize: '10px', opacity: 0.7 }}>
              If anything is not working it should have a red X and Disconnected
            </span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div 
      className="health-check-info"
      onMouseEnter={() => hasInitialLoad && setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div 
        className="health-info-button"
        style={{ 
          cursor: 'pointer'
        }}
        title="System Health Status"
      >
        <span className="health-button-label">Health</span>
      </div>

      {showTooltip && hasInitialLoad && renderHealthTooltip()}
    </div>
  );
};

export default HealthCheckInfo;
