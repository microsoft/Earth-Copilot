// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

/**
 * Authentication Helper for EasyAuth Token Forwarding
 * 
 * When EasyAuth is enabled on the frontend App Service, the user's id_token
 * is available via the /.auth/me endpoint. This module fetches and caches that
 * token, then provides utilities to attach it to API calls to the backend
 * Container App (which also has EasyAuth configured to validate tokens).
 * 
 * In development mode (no EasyAuth), all functions gracefully return null/empty
 * so the app works without auth locally.
 */

const isDevelopment = import.meta.env.DEV;

// Token cache — avoids calling /.auth/me on every API request
let cachedToken: string | null = null;
let tokenExpiry: number = 0;
let isRefreshing = false;

/**
 * Parse JWT expiry from the token payload (without validation).
 * Returns the `exp` timestamp in ms, or 0 if unparseable.
 */
function getTokenExp(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return (payload.exp ?? 0) * 1000; // `exp` is in seconds
  } catch {
    return 0;
  }
}

/**
 * Fetch the user's id_token from EasyAuth.
 * Returns null in development mode or if EasyAuth is not configured.
 */
export async function getAuthToken(): Promise<string | null> {
  // Skip in development mode — no EasyAuth available
  if (isDevelopment) return null;

  // Return cached token if still valid (refresh 5 min before expiry)
  if (cachedToken && Date.now() < tokenExpiry - 300_000) {
    return cachedToken;
  }

  try {
    const response = await fetch('/.auth/me');
    if (!response.ok) return null;

    const data = await response.json();
    const idToken = data?.[0]?.id_token;
    if (idToken) {
      cachedToken = idToken;
      // Use actual JWT expiry if available, otherwise assume 1 hour
      const exp = getTokenExp(idToken);
      tokenExpiry = exp > 0 ? exp : Date.now() + 55 * 60 * 1000;
      return cachedToken;
    }
  } catch {
    // EasyAuth not configured or user not logged in — this is expected in
    // deployments without AUTH_CLIENT_ID or during local development
  }

  return null;
}

/**
 * Force-refresh the EasyAuth session and obtain a new id_token.
 * Called automatically when the backend returns 401 "Token has expired".
 *
 * Flow: POST /.auth/refresh (extends server-side session) → GET /.auth/me
 * If the refresh token itself has expired (>24h), returns null and the user
 * must re-authenticate.
 */
export async function refreshAuthToken(): Promise<string | null> {
  if (isDevelopment) return null;

  // Prevent multiple concurrent refresh calls
  if (isRefreshing) {
    // Wait for the in-flight refresh to finish then return whatever it got
    await new Promise((r) => setTimeout(r, 1000));
    return cachedToken;
  }

  isRefreshing = true;
  try {
    // Step 1: Ask EasyAuth to refresh the server-side token
    const refreshResp = await fetch('/.auth/refresh', { method: 'GET' });
    if (!refreshResp.ok) {
      console.warn('[Auth] /.auth/refresh failed — user may need to re-login');
      // Clear stale cache so the next request triggers a login redirect
      cachedToken = null;
      tokenExpiry = 0;
      return null;
    }

    // Step 2: Fetch the new token from /.auth/me
    cachedToken = null;
    tokenExpiry = 0;
    return await getAuthToken();
  } catch (err) {
    console.warn('[Auth] Token refresh error:', err);
    cachedToken = null;
    tokenExpiry = 0;
    return null;
  } finally {
    isRefreshing = false;
  }
}

/**
 * Invalidate the cached token.  Called externally when a 401 is received
 * to ensure the next getAuthToken() call fetches a fresh token.
 */
export function clearCachedToken(): void {
  cachedToken = null;
  tokenExpiry = 0;
}

/**
 * Get Authorization headers if a token is available.
 * Returns an empty object when no token exists (development mode / no auth).
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Drop-in replacement for window.fetch that automatically attaches
 * the EasyAuth Bearer token when available.
 * 
 * Usage:  import { authenticatedFetch } from '../services/authHelper';
 *         const response = await authenticatedFetch(`${API_BASE_URL}/api/config`);
 */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const token = await getAuthToken();
  if (!token) return fetch(input, init);

  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);

  return fetch(input, { ...init, headers });
}

// ---- User Info (for account menu UI) ----

export interface UserInfo {
  name: string | null;
  email: string | null;
}

let cachedUser: UserInfo | null = null;

/**
 * Fetch the logged-in user's display name and email from EasyAuth.
 * Returns null in development mode or when EasyAuth is not configured.
 *
 * EasyAuth /.auth/me response shape:
 *   [{ id_token, user_claims: [{ typ, val }], ... }]
 * Common claim types:
 *   name                                        -> display name
 *   preferred_username / emails                  -> email
 *   http://schemas.xmlsoap.org/.../name          -> fallback name
 *   http://schemas.xmlsoap.org/.../emailaddress  -> fallback email
 */
export async function getUserInfo(): Promise<UserInfo | null> {
  if (isDevelopment) return null;
  if (cachedUser) return cachedUser;

  try {
    const response = await fetch('/.auth/me');
    if (!response.ok) return null;

    const data = await response.json();
    const claims: Array<{ typ: string; val: string }> = data?.[0]?.user_claims ?? [];

    const claim = (types: string[]): string | null => {
      for (const t of types) {
        const c = claims.find((c) => c.typ === t);
        if (c?.val) return c.val;
      }
      return null;
    };

    cachedUser = {
      name: claim([
        'name',
        'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
        'preferred_username',
      ]),
      email: claim([
        'preferred_username',
        'email',
        'emails',
        'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
      ]),
    };

    return cachedUser;
  } catch {
    return null;
  }
}
