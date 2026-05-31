// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';

interface SourceChipsProps {
  dataSource?: string;          // "MPC Pro" | "Public PC" | undefined
  tilesAvailable?: number;      // # of STAC items returned by the search
  toolsUsed?: string[];         // ordered list of tool names from ReAct loop
  /**
   * Routing decision surfaced by the backend (`debug.stac_routing` on
   * /api/query). Used to render the resolved STAC host inside the
   * data-source chip tooltip so the user can verify Pro vs Public
   * without paging through Log Analytics. Optional -- absent on
   * pre-routing-debug backend builds.
   */
  stacRouting?: {
    requested_mode?: string | null;     // body.stac_mode the UI sent ("pro" | "public" | "")
    default_mode?: string;              // DEFAULT_STAC_MODE env on the server
    resolved_endpoint?: string;         // label, e.g. "planetary_computer" / "planetary_computer_pro"
    resolved_url?: string;              // full STAC search URL the backend would call
    resolved_host?: string;             // hostname portion (e.g. "planetarycomputer.microsoft.com")
    is_pro?: boolean;
    pro_configured?: boolean | null;
    pro_unconfigured_short_circuit?: boolean;
  };
}

interface Chip {
  label: string;
  bg: string;
  fg: string;
  border: string;
  title: string;
}

/**
 * Small pill badges shown under an assistant message to make the data
 * provenance + tool path observable in the UI. Today we surface:
 *
 *   - `Data: MPC Pro` / `Data: Public PC` (when the response answered
 *     from STAC tiles).
 *   - `Tool: <name>` for the *other* tools the agent called (vision,
 *     terrain, climate, …) so the user can see why the answer took the
 *     shape it did. Capped to keep the row compact.
 *
 * Rendered as an inline-flex row; renders nothing when there is no
 * provenance to show (e.g. plain greeting turns).
 */
const TOOL_DISPLAY: Record<string, string> = {
  general_earth_qa: 'Earth Q&A',
  describe_map_screenshot: 'Vision',
  sample_raster_value: 'Raster sample',
  get_collection_metadata: 'Collection meta',
  get_terrain_stats: 'Terrain',
  get_mobility_path: 'Mobility',
  get_extreme_weather_projection: 'Climate proj.',
  compute_netcdf_trend: 'NetCDF trend',
  compare_temporal: 'Temporal compare',
  ask_user_to_clarify: 'Clarify',
};

const SourceChips: React.FC<SourceChipsProps> = ({
  dataSource,
  tilesAvailable,
  toolsUsed,
  stacRouting,
}) => {
  const chips: Chip[] = [];

  // Build a routing-evidence suffix shown in the data-source chip
  // tooltip. The backend's `debug.stac_routing.resolved_host` is the
  // single most authoritative signal -- if it equals
  // "planetarycomputer.microsoft.com" the request hit Public, if it
  // ends in ".geocatalog.spatio.azure.com" it hit Pro. No log lag,
  // no inference, no guessing.
  const routingTooltip = stacRouting
    ? (
      '\n\nRouting evidence (debug.stac_routing):' +
      `\n  requested_mode: ${stacRouting.requested_mode || '(none)'}` +
      `\n  default_mode:   ${stacRouting.default_mode || '(unset)'}` +
      `\n  resolved label: ${stacRouting.resolved_endpoint || '(unknown)'}` +
      `\n  resolved host:  ${stacRouting.resolved_host || '(empty)'}` +
      `\n  is_pro:         ${stacRouting.is_pro ? 'true' : 'false'}` +
      (stacRouting.pro_unconfigured_short_circuit
        ? '\n  WARNING: Pro requested but MPC_PRO_STAC_URL not configured'
        : '')
    )
    : '';

  // Render the data-source chip whenever the backend tells us a catalog
  // served (or attempted to serve) this turn. Append the tile count so a
  // misrouted toggle (e.g. "Data: MPC Pro · 0 tiles" while the user
  // expects results) is visible without opening DevTools. When the
  // backend did not include a count we omit the suffix to avoid implying
  // zero.
  const tileSuffix =
    typeof tilesAvailable === 'number'
      ? ` · ${tilesAvailable} tile${tilesAvailable === 1 ? '' : 's'}`
      : '';
  if (dataSource === 'MPC Pro') {
    chips.push({
      // Blue palette to match the new MPC Pro toggle pill in the header /
      // landing page. The chip was purple before; that conflicted with
      // the blue Pro pill and made the routing harder to spot.
      label: `Data: MPC Pro${tileSuffix}`,
      bg: '#DBEAFE',
      fg: '#1D4ED8',
      border: '#3B82F6',
      title:
        'STAC tiles came from the private MPC Pro / GeoCatalog endpoint. ' +
        (typeof tilesAvailable === 'number'
          ? `The search returned ${tilesAvailable} item${tilesAvailable === 1 ? '' : 's'}.`
          : '') +
        routingTooltip,
    });
  } else if (dataSource === 'Public PC') {
    chips.push({
      label: `Data: Public PC${tileSuffix}`,
      bg: '#ECFDF5',
      fg: '#065F46',
      border: '#10B981',
      title:
        'STAC tiles came from the public Microsoft Planetary Computer. ' +
        (typeof tilesAvailable === 'number'
          ? `The search returned ${tilesAvailable} item${tilesAvailable === 1 ? '' : 's'}.`
          : '') +
        routingTooltip,
    });
  }

  // Other tools the agent invoked.
  const otherTools = (toolsUsed || []).filter(
    (t) => t in TOOL_DISPLAY,
  );
  const unique: string[] = [];
  for (const t of otherTools) {
    if (!unique.includes(t)) unique.push(t);
  }
  for (const t of unique.slice(0, 4)) {
    chips.push({
      label: `Tool: ${TOOL_DISPLAY[t]}`,
      bg: '#F3F4F6',
      fg: '#374151',
      border: '#9CA3AF',
      title: `AnalystAgent invoked ${t} during the ReAct loop.`,
    });
  }

  if (chips.length === 0) return null;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 6,
        marginTop: 8,
        alignItems: 'center',
      }}
    >
      {chips.map((c, i) => (
        <span
          key={`${c.label}-${i}`}
          title={c.title}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            // Slightly larger so the data-source chip is obvious at a
            // glance (previously 11px / 2x8 padding -- easy to miss).
            padding: '4px 10px',
            borderRadius: 999,
            border: `1px solid ${c.border}`,
            background: c.bg,
            color: c.fg,
            fontSize: 12,
            fontWeight: 600,
            lineHeight: 1.4,
            whiteSpace: 'nowrap',
          }}
        >
          {c.label}
        </span>
      ))}
    </div>
  );
};

export default SourceChips;
