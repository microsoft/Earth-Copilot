// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useState, useEffect, useRef } from 'react';
import { getUserInfo, type UserInfo } from '../services/authHelper';

/**
 * User account menu — pill-shaped button matching the header style
 * (Get Started, Data Catalog, Health, etc.) but with a teal accent color.
 *
 * Shows "Sign in" when not authenticated, or user initials + name when signed in.
 * Clicking opens a dropdown with user info and Sign Out.
 *
 * Uses EasyAuth /.auth/me to fetch user claims. In local dev (no EasyAuth),
 * the component renders nothing so the header stays clean.
 */
const UserAccountMenu: React.FC = () => {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getUserInfo().then((info) => {
      setUser(info);
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // In local dev, render nothing
  const isDevMode = import.meta.env.DEV;
  if (isDevMode) return null;

  // Still loading — don't flash
  if (!loaded) return null;

  const initials = user ? getInitials(user.name || user.email || '') : null;
  const displayName = user?.name?.split(' ')[0] || null; // First name only for pill

  return (
    <div ref={menuRef} style={{ position: 'relative' }}>
      {/* Pill button — matches header button style with teal accent */}
      <div
        className="account-menu-button"
        onClick={() => {
          if (user) {
            setOpen((o) => !o);
          } else {
            window.location.href = '/.auth/login/aad';
          }
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        title={user ? `Signed in as ${user.name || user.email}` : 'Sign in with Microsoft'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 12px',
          backgroundColor: hovered ? '#107c70' : 'rgba(255, 255, 255, 0.7)',
          border: '1px solid',
          borderColor: hovered ? '#107c70' : 'rgba(16, 124, 112, 0.4)',
          borderRadius: '20px',
          cursor: 'pointer',
          transition: 'all 0.3s ease',
          boxShadow: hovered
            ? '0 4px 12px rgba(16, 124, 112, 0.3)'
            : '0 2px 6px rgba(0, 0, 0, 0.1)',
          backdropFilter: 'blur(10px)',
          transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
          color: hovered ? '#fff' : '#1e293b',
        }}
      >
        {/* Person icon */}
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="5" r="3" stroke={hovered ? '#fff' : '#107c70'} strokeWidth="1.5" />
          <path d="M2.5 14c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke={hovered ? '#fff' : '#107c70'} strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span style={{
          fontSize: '13px',
          fontWeight: 600,
          letterSpacing: '0.5px',
          whiteSpace: 'nowrap',
        }}>
          {user ? (displayName || initials || 'Account') : 'Sign in'}
        </span>
      </div>

      {/* Dropdown — only when signed in */}
      {user && open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            minWidth: 240,
            background: '#fff',
            borderRadius: '10px',
            boxShadow: '0 8px 30px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)',
            border: '1px solid rgba(0,0,0,0.08)',
            zIndex: 9999,
            overflow: 'hidden',
            animation: 'accountMenuFadeIn 0.15s ease',
          }}
        >
          {/* User info */}
          <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid #f1f5f9' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: 36,
                height: 36,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #107c70, #0d6b61)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '14px',
                fontWeight: 600,
                flexShrink: 0,
              }}>
                {initials || '?'}
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '14px', color: '#0f172a', lineHeight: 1.4 }}>
                  {user.name || 'User'}
                </div>
                {user.email && (
                  <div style={{ fontSize: '12px', color: '#64748b', marginTop: '1px', wordBreak: 'break-all' }}>
                    {user.email}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Sign out */}
          <div style={{ padding: '6px' }}>
            <button
              onClick={() => {
                window.location.href = '/.auth/logout';
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                width: '100%',
                padding: '10px 12px',
                background: 'none',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px',
                color: '#dc2626',
                fontWeight: 500,
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = '#fef2f2';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'none';
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M6 14H3.333A1.333 1.333 0 0 1 2 12.667V3.333A1.333 1.333 0 0 1 3.333 2H6M10.667 11.333L14 8l-3.333-3.333M14 8H6"
                  stroke="#dc2626"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Sign out
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes accountMenuFadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};

/** Extract up to 2 initials from a display name or email. */
function getInitials(nameOrEmail: string): string {
  if (!nameOrEmail) return '?';
  // If it looks like an email, use the part before @
  const base = nameOrEmail.includes('@') ? nameOrEmail.split('@')[0] : nameOrEmail;
  const parts = base.split(/[\s._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return (parts[0]?.[0] ?? '?').toUpperCase();
}

export default UserAccountMenu;
