import { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import './FabricConnect.css';

/**
 * Sidebar card for connecting to a Microsoft Fabric workspace + Lakehouse.
 *
 * Calls the backend `/api/fabric/*` endpoints, which use OBO to flow the
 * signed-in user's identity through to Fabric. Selection is persisted in
 * `localStorage` under `fabric.selection` so the chat agent can pick it up
 * (see `Chat.tsx` — selection is forwarded as `fabric_workspace_id` /
 * `fabric_lakehouse_id` on `/api/query` requests).
 */
interface FabricItem {
  id: string;
  displayName: string;
}

interface Selection {
  workspaceId?: string;
  workspaceName?: string;
  lakehouseId?: string;
  lakehouseName?: string;
}

const STORAGE_KEY = 'fabric.selection';

function loadSelection(): Selection {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveSelection(sel: Selection) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sel));
  window.dispatchEvent(new CustomEvent('fabric:selection', { detail: sel }));
}

export default function FabricConnect() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [workspaces, setWorkspaces] = useState<FabricItem[]>([]);
  const [lakehouses, setLakehouses] = useState<FabricItem[]>([]);
  const [selection, setSelection] = useState<Selection>(loadSelection());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Probe the backend on mount.
  useEffect(() => {
    apiService.getFabricStatus()
      .then((s) => setConfigured(!!s.configured))
      .catch(() => setConfigured(false));
  }, []);

  // Load lakehouses when a workspace is chosen.
  useEffect(() => {
    if (!selection.workspaceId) {
      setLakehouses([]);
      return;
    }
    setLoading(true);
    apiService.listFabricLakehouses(selection.workspaceId)
      .then(setLakehouses)
      .catch((e) => setError(e?.message || 'Failed to list lakehouses'))
      .finally(() => setLoading(false));
  }, [selection.workspaceId]);

  const loadWorkspaces = async () => {
    setLoading(true);
    setError(null);
    try {
      const ws = await apiService.listFabricWorkspaces();
      setWorkspaces(ws);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to connect to Fabric');
    } finally {
      setLoading(false);
    }
  };

  const pickWorkspace = (w: FabricItem) => {
    const next: Selection = {
      workspaceId: w.id,
      workspaceName: w.displayName,
      lakehouseId: undefined,
      lakehouseName: undefined,
    };
    setSelection(next);
    saveSelection(next);
  };

  const pickLakehouse = (lh: FabricItem) => {
    const next: Selection = {
      ...selection,
      lakehouseId: lh.id,
      lakehouseName: lh.displayName,
    };
    setSelection(next);
    saveSelection(next);
  };

  const clear = () => {
    setSelection({});
    saveSelection({});
  };

  if (configured === null) {
    return <div className="fabric-card">Checking Fabric…</div>;
  }
  if (configured === false) {
    return (
      <div className="fabric-card fabric-card--muted">
        <div className="fabric-card__title">Microsoft Fabric</div>
        <div className="fabric-card__hint">
          Not configured. Ask your admin to set <code>FABRIC_CLIENT_ID</code> /
          <code> FABRIC_CLIENT_SECRET</code> on the API container app and grant
          the Workspace.Read / Item.ReadWrite delegated permissions.
        </div>
      </div>
    );
  }

  return (
    <div className="fabric-card">
      <div className="fabric-card__title">Microsoft Fabric</div>

      {error && <div className="fabric-card__error">{error}</div>}

      {!workspaces.length && (
        <button className="fabric-card__action" onClick={loadWorkspaces} disabled={loading}>
          {loading ? 'Connecting…' : 'Connect to Fabric'}
        </button>
      )}

      {workspaces.length > 0 && !selection.workspaceId && (
        <>
          <div className="fabric-card__label">Workspace</div>
          <ul className="fabric-card__list">
            {workspaces.map((w) => (
              <li key={w.id}>
                <button onClick={() => pickWorkspace(w)}>{w.displayName}</button>
              </li>
            ))}
          </ul>
        </>
      )}

      {selection.workspaceId && (
        <div className="fabric-card__chip">
          <strong>Workspace:</strong> {selection.workspaceName}
          <button className="fabric-card__chip-x" onClick={clear} title="Change">✕</button>
        </div>
      )}

      {selection.workspaceId && !selection.lakehouseId && (
        <>
          <div className="fabric-card__label">Lakehouse</div>
          {loading && <div className="fabric-card__hint">Loading…</div>}
          <ul className="fabric-card__list">
            {lakehouses.map((lh) => (
              <li key={lh.id}>
                <button onClick={() => pickLakehouse(lh)}>{lh.displayName}</button>
              </li>
            ))}
          </ul>
        </>
      )}

      {selection.lakehouseId && (
        <div className="fabric-card__chip fabric-card__chip--success">
          <strong>Lakehouse:</strong> {selection.lakehouseName}
        </div>
      )}
    </div>
  );
}
