// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React from 'react';

export type StacMode = 'public' | 'pro';

interface Props {
  mode: StacMode;
  onChange: (next: StacMode) => void;
  /**
   * Whether this deployment has the MPC Pro (private GeoCatalog) integration
   * enabled. Surfaced via /api/config.features.mpcPro and threaded down from
   * App.tsx. When ``false``, the Pro side of the toggle renders as a locked
   * control with a tooltip + "How to enable" link instead of switching the
   * mode. Defaults to ``true`` so existing call sites that don't know about
   * the flag yet keep working.
   */
  proEnabled?: boolean;
}

/**
 * Two-state toggle that pins every chat request to either the public
 * Microsoft Planetary Computer STAC API or the private MPC Pro /
 * GeoCatalog instance configured on the backend (MPC_PRO_STAC_URL).
 *
 * When the deployment does not have the Pro integration wired up
 * (``proEnabled=false``), the control still renders so users see the
 * capability exists, but clicking the Pro side is a no-op and the chip
 * shows a "How to enable" link pointing at the deployment docs.
 */
const StacModeToggle: React.FC<Props> = ({ mode, onChange, proEnabled = true }) => {
  const isPro = mode === 'pro';
  const locked = !proEnabled;

  const handleClick = () => {
    // When Pro is locked out for this deployment we never flip into Pro;
    // we also don't bounce out of Pro into Public from a click, because
    // we only ever land in Public when locked (App.tsx forces public on
    // /api/config response). So a click here is just inert.
    if (locked) return;
    onChange(isPro ? 'public' : 'pro');
  };

  const tooltip = locked
    ? 'MPC Pro is not enabled. To enable, redeploy application with MPC Pro variable toggled on.'
    : isPro
      ? 'Routing STAC searches to MPC Pro (private GeoCatalog). Click to switch to Public.'
      : 'Routing STAC searches to public Microsoft Planetary Computer. Click to switch to Pro.';

  const labelText = locked ? 'MPC Pro' : isPro ? 'MPC Pro' : 'MPC Public';

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <button
        type="button"
        onClick={handleClick}
        title={tooltip}
        aria-disabled={locked || undefined}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 12px',
          borderRadius: 999,
          // When locked, render in a muted grey palette so it's clearly
          // unavailable without hiding the capability. When active, keep
          // the blue/green palette from before.
          border: `1px solid ${locked ? '#D1D5DB' : isPro ? '#3B82F6' : '#6B7280'}`,
          background: locked ? '#F9FAFB' : isPro ? '#DBEAFE' : '#F3F4F6',
          color: locked ? '#9CA3AF' : isPro ? '#1D4ED8' : '#374151',
          fontSize: 13,
          fontWeight: 600,
          cursor: locked ? 'not-allowed' : 'pointer',
          userSelect: 'none',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: locked ? '#9CA3AF' : isPro ? '#3B82F6' : '#10B981',
            display: 'inline-block',
          }}
        />
        <span>{labelText}</span>
      </button>
    </span>
  );
};

export default StacModeToggle;
