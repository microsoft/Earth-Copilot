/**
 * ResiliencePanel — UI for the Resilience agent (use-case 9).
 *
 * Renders a floating panel that runs `/api/resilience/assess` and shows:
 *   - Header summary (facilities assessed, at-risk count, data source)
 *   - Per-facility risk cards sorted by overall_risk desc, with:
 *       severity pill, primary hazard, score bar, hazard drivers,
 *       upstream supply-chain dependencies, and BCP playbook snippets.
 *   - A "Run assessment" button that re-issues the API call.
 *
 * The panel emits a `resilience:facilities` CustomEvent on `window` after a
 * successful assessment so MapView can drop coloured facility markers /
 * supply-chain lines without ResiliencePanel needing a direct map handle.
 *
 * Auth: backend route uses _require_fabric_assertion → relies on the
 * standard EasyAuth header forwarding via authenticatedFetch.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { API_BASE_URL } from '../services/api';
import { authenticatedFetch } from '../services/authHelper';
import './ResiliencePanel.css';

// ─────────────────────────────────────────────────────────────────────────
// Types — mirror the dossier shape produced by
// agents/resilience/executors._build_dossier (Python side).
// ─────────────────────────────────────────────────────────────────────────
export type HazardName = 'heat' | 'wildfire' | string;
export type Severity = 'low' | 'moderate' | 'high' | 'severe';

export interface HazardScore {
  score: number;
  severity: Severity;
  peak_value: number | null;
  peak_day: string | null;
  summary: string;
  drivers: string[];
  consecutive_days?: number;
  facility_threshold_f?: number;
  total_precip_in?: number;
}

export interface UpstreamEdge {
  src_id: string;
  kind: string;
  lead_time_days: number;
  weekly_volume?: number;
}

export interface Playbook {
  title: string;
  snippet: string;
  score?: number | null;
  id?: string;
  url?: string;
}

export interface ResilienceFacility {
  facility_id: string;
  name: string;
  lat: number;
  lng: number;
  type?: string;
  region?: string;
  city?: string;
  criticality?: number;
  overall_risk: number;
  severity: Severity;
  primary_hazard: HazardName | null;
  hazards: Record<HazardName, HazardScore>;
  upstream_at_risk: UpstreamEdge[];
  downstream: UpstreamEdge[];
  playbooks: Playbook[];
}

export interface ResilienceDossier {
  input: {
    region_filter: string | null;
    horizon_days: number;
    hazards: string[];
    user_query: string | null;
  };
  facilities: ResilienceFacility[];
  hazards: Record<HazardName, Record<string, HazardScore>>;
  summary: {
    facilities_assessed: number;
    at_risk_facilities: number;
    top_risks: Array<{
      facility_id: string;
      name: string;
      severity: Severity;
      overall_risk: number;
      primary_hazard: HazardName | null;
    }>;
  };
  provenance: Array<Record<string, unknown>>;
  engine: string;
}

interface ResiliencePanelProps {
  visible: boolean;
  onClose: () => void;
  regionFilter?: string;
  horizonDays?: number;
  hazards?: HazardName[];
  userQuery?: string;
  /** Optional callback when the user clicks a facility (zooms map). */
  onFacilityClick?: (facility: ResilienceFacility) => void;
  /** Optional: prevent emitting the global event (e.g. for tests). */
  suppressMapEvent?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────
// Visual helpers
// ─────────────────────────────────────────────────────────────────────────
const SEVERITY_COLORS: Record<Severity, { bg: string; fg: string; bar: string }> = {
  low:      { bg: 'rgba(34, 197, 94, 0.12)',  fg: '#15803d', bar: '#22c55e' },
  moderate: { bg: 'rgba(234, 179, 8, 0.15)',  fg: '#a16207', bar: '#eab308' },
  high:     { bg: 'rgba(249, 115, 22, 0.15)', fg: '#c2410c', bar: '#f97316' },
  severe:   { bg: 'rgba(220, 38, 38, 0.18)',  fg: '#991b1b', bar: '#dc2626' },
};

const HAZARD_LABELS: Record<string, string> = {
  heat: 'Heat',
  wildfire: 'Wildfire / Smoke',
};

function severityLabel(s: Severity): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatScore(n: number): string {
  return Number.isFinite(n) ? Math.round(n).toString() : '–';
}

// ─────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────
const ResiliencePanel: React.FC<ResiliencePanelProps> = ({
  visible,
  onClose,
  regionFilter = 'TX',
  horizonDays = 7,
  hazards = ['heat', 'wildfire'],
  userQuery,
  onFacilityClick,
  suppressMapEvent,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dossier, setDossier] = useState<ResilienceDossier | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const runAssessment = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authenticatedFetch(`${API_BASE_URL}/api/resilience/assess`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_filter: regionFilter,
          horizon_days: horizonDays,
          hazards,
          user_query: userQuery,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text.slice(0, 240)}`);
      }
      const data: ResilienceDossier = await response.json();
      setDossier(data);

      // Auto-expand the top at-risk facility so the demo lands on visible
      // content without the user having to click.
      if (data.facilities.length > 0) {
        setExpanded({ [data.facilities[0].facility_id]: true });
      }

      // Emit so MapView can drop markers / draw supply edges.
      if (!suppressMapEvent && typeof window !== 'undefined') {
        const evt = new CustomEvent('resilience:facilities', { detail: data });
        window.dispatchEvent(evt);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [regionFilter, horizonDays, hazards, userQuery, suppressMapEvent]);

  // First-time auto-run when the panel becomes visible.
  useEffect(() => {
    if (visible && !dossier && !loading && !error) {
      runAssessment();
    }
  }, [visible, dossier, loading, error, runAssessment]);

  // Clear markers on the map when the panel is closed.
  useEffect(() => {
    if (!visible && !suppressMapEvent && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('resilience:clear'));
    }
  }, [visible, suppressMapEvent]);

  const sortedFacilities = useMemo(() => dossier?.facilities ?? [], [dossier]);

  if (!visible) return null;

  return (
    <div className="resilience-panel">
      <div className="resilience-panel-header">
        <div>
          <div className="resilience-title">Resilience</div>
          <div className="resilience-subtitle">
            {regionFilter ? `${regionFilter} · ` : ''}{horizonDays}-day forecast · hazards: {hazards.map(h => HAZARD_LABELS[h] ?? h).join(', ')}
          </div>
        </div>
        <div className="resilience-header-actions">
          <button
            className="resilience-action-btn"
            onClick={runAssessment}
            disabled={loading}
            title="Re-run assessment with current parameters"
          >
            {loading ? 'Assessing…' : 'Refresh'}
          </button>
          <button className="resilience-close-btn" onClick={onClose} title="Close">×</button>
        </div>
      </div>

      {error && (
        <div className="resilience-error">
          <strong>Assessment failed.</strong>
          <div className="resilience-error-detail">{error}</div>
          <button className="resilience-action-btn" onClick={runAssessment}>Retry</button>
        </div>
      )}

      {loading && !dossier && (
        <div className="resilience-loading">
          <div className="resilience-spinner" />
          <div>Fetching forecasts for facilities…</div>
        </div>
      )}

      {dossier && (
        <>
          <div className="resilience-summary">
            <div className="resilience-summary-stat">
              <div className="resilience-summary-value">{dossier.summary.facilities_assessed}</div>
              <div className="resilience-summary-label">Facilities</div>
            </div>
            <div className="resilience-summary-stat">
              <div className="resilience-summary-value resilience-at-risk">
                {dossier.summary.at_risk_facilities}
              </div>
              <div className="resilience-summary-label">At risk</div>
            </div>
            <div className="resilience-summary-stat">
              <div className="resilience-summary-value">{dossier.input.horizon_days}d</div>
              <div className="resilience-summary-label">Horizon</div>
            </div>
            <div className="resilience-summary-stat" title="Where the facility registry came from">
              <div className="resilience-summary-value resilience-source">
                {extractDataSource(dossier)}
              </div>
              <div className="resilience-summary-label">Source</div>
            </div>
          </div>

          {dossier.summary.top_risks.length > 0 && (
            <div className="resilience-top-risks">
              <div className="resilience-section-label">Top risks</div>
              <div className="resilience-top-risks-row">
                {dossier.summary.top_risks.map((r) => (
                  <div
                    key={r.facility_id}
                    className="resilience-top-risk-chip"
                    style={{
                      background: SEVERITY_COLORS[r.severity].bg,
                      color: SEVERITY_COLORS[r.severity].fg,
                      borderColor: SEVERITY_COLORS[r.severity].bar,
                    }}
                    onClick={() => {
                      const fac = dossier.facilities.find((f) => f.facility_id === r.facility_id);
                      if (fac && onFacilityClick) onFacilityClick(fac);
                      setExpanded((prev) => ({ ...prev, [r.facility_id]: true }));
                    }}
                  >
                    <span className="resilience-chip-name">{r.name}</span>
                    <span className="resilience-chip-score">{formatScore(r.overall_risk)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="resilience-facility-list">
            {sortedFacilities.map((fac) => (
              <FacilityCard
                key={fac.facility_id}
                facility={fac}
                expanded={!!expanded[fac.facility_id]}
                onToggle={() =>
                  setExpanded((prev) => ({ ...prev, [fac.facility_id]: !prev[fac.facility_id] }))
                }
                onLocate={() => onFacilityClick && onFacilityClick(fac)}
              />
            ))}
            {sortedFacilities.length === 0 && (
              <div className="resilience-empty">
                No facilities matched the filter. Try clearing the region filter.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────
// Subcomponents
// ─────────────────────────────────────────────────────────────────────────
interface FacilityCardProps {
  facility: ResilienceFacility;
  expanded: boolean;
  onToggle: () => void;
  onLocate: () => void;
}

const FacilityCard: React.FC<FacilityCardProps> = ({ facility, expanded, onToggle, onLocate }) => {
  const colors = SEVERITY_COLORS[facility.severity];
  const score = Math.max(0, Math.min(100, facility.overall_risk));

  return (
    <div
      className="resilience-facility-card"
      style={{ borderLeftColor: colors.bar }}
    >
      <div className="resilience-facility-header" onClick={onToggle}>
        <div className="resilience-facility-id">
          <div className="resilience-facility-name">{facility.name || facility.facility_id}</div>
          <div className="resilience-facility-meta">
            {facility.type ?? '—'}{facility.city ? ` · ${facility.city}` : ''}
            {facility.criticality !== undefined ? ` · criticality ${facility.criticality.toFixed(2)}` : ''}
          </div>
        </div>
        <div className="resilience-facility-score">
          <div
            className="resilience-severity-pill"
            style={{ background: colors.bg, color: colors.fg, borderColor: colors.bar }}
          >
            {severityLabel(facility.severity)}
          </div>
          <div className="resilience-score-val">{formatScore(score)}</div>
        </div>
      </div>

      <div className="resilience-score-bar-wrap">
        <div
          className="resilience-score-bar"
          style={{ width: `${score}%`, background: colors.bar }}
        />
      </div>

      {expanded && (
        <div className="resilience-facility-body">
          {facility.primary_hazard && (
            <div className="resilience-primary-hazard">
              Primary hazard: <strong>{HAZARD_LABELS[facility.primary_hazard] ?? facility.primary_hazard}</strong>
            </div>
          )}

          <div className="resilience-hazards-grid">
            {Object.entries(facility.hazards).map(([hzName, hz]) => (
              <HazardBlock key={hzName} name={hzName} score={hz} />
            ))}
          </div>

          {facility.upstream_at_risk.length > 0 && (
            <div className="resilience-section">
              <div className="resilience-section-label">Upstream supply dependencies</div>
              <ul className="resilience-edge-list">
                {facility.upstream_at_risk.map((e, i) => (
                  <li key={i}>
                    <span className="resilience-edge-src">{e.src_id}</span>
                    <span className="resilience-edge-kind">{e.kind}</span>
                    <span className="resilience-edge-lead">lead {e.lead_time_days}d</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {facility.playbooks.length > 0 && (
            <div className="resilience-section">
              <div className="resilience-section-label">Recommended actions (BCP)</div>
              <ul className="resilience-playbook-list">
                {facility.playbooks.map((p, i) => (
                  <li key={`${p.id ?? p.title}-${i}`}>
                    <div className="resilience-playbook-title">{p.title}</div>
                    <div className="resilience-playbook-snippet">{p.snippet}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="resilience-card-actions">
            <button className="resilience-action-btn" onClick={onLocate}>Show on map</button>
          </div>
        </div>
      )}
    </div>
  );
};

interface HazardBlockProps {
  name: string;
  score: HazardScore;
}

const HazardBlock: React.FC<HazardBlockProps> = ({ name, score }) => {
  const colors = SEVERITY_COLORS[score.severity];
  return (
    <div
      className="resilience-hazard-block"
      style={{ borderColor: colors.bar, background: colors.bg }}
    >
      <div className="resilience-hazard-header">
        <span className="resilience-hazard-label">{HAZARD_LABELS[name] ?? name}</span>
        <span className="resilience-hazard-score" style={{ color: colors.fg }}>
          {formatScore(score.score)}
        </span>
      </div>
      <div className="resilience-hazard-summary">{score.summary}</div>
      {score.drivers && score.drivers.length > 0 && (
        <ul className="resilience-driver-list">
          {score.drivers.slice(0, 4).map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────
function extractDataSource(dossier: ResilienceDossier): string {
  // Find the supply_edges provenance entry — it carries no source field;
  // we look at the open-meteo and search entries first, and finally infer
  // "seed" if everything else is missing.
  for (const p of dossier.provenance) {
    const source = (p.source as string | undefined) ?? '';
    if (source === 'fabric' || source === 'open-meteo') {
      return source === 'fabric' ? 'Fabric' : 'Open-Meteo';
    }
  }
  return 'Seed';
}

export default ResiliencePanel;
