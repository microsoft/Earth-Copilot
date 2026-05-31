import React, { useState } from "react";
import { apiService } from "../../services/api";
import type { PermissionTier } from "./types";

/**
 * Pending MCP confirmation surfaced by a backend ``confirm_request``
 * SSE event. The card asks the user to Approve / Deny before the agent
 * dispatches the (potentially destructive) tool call.
 */
export interface PendingConfirm {
  traceId: string;
  serverId: string;
  tool: string;
  tier: PermissionTier;
  args: Record<string, unknown>;
}

export interface ConfirmationCardProps {
  pending: PendingConfirm;
  /** Called after the POST returns. Removes the card from the stack. */
  onResolved: (traceId: string, approved: boolean) => void;
}

const tierColor: Record<PermissionTier, string> = {
  read: "#0078d4",
  write: "#bc4b00",
  destructive: "#a80000",
};

export const ConfirmationCard: React.FC<ConfirmationCardProps> = ({ pending, onResolved }) => {
  const [busy, setBusy] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handle = async (approved: boolean) => {
    setBusy(approved ? "approve" : "deny");
    setError(null);
    try {
      const ok = await apiService.resolveMcpConfirmation(pending.traceId, approved);
      if (!ok) {
        // 404 → broker had no pending entry (timeout or wrong replica).
        // Still hand control back to the parent so the card unmounts.
        setError("This confirmation already expired.");
      }
      onResolved(pending.traceId, approved);
    } catch (err: any) {
      setError(err?.message || "Failed to send confirmation.");
      setBusy(null);
    }
  };

  const tier = pending.tier;
  return (
    <div
      role="alertdialog"
      aria-labelledby={`confirm-${pending.traceId}-title`}
      style={{
        border: `1px solid ${tierColor[tier]}`,
        borderLeft: `4px solid ${tierColor[tier]}`,
        borderRadius: 8,
        padding: 12,
        background: "#fffaf5",
        margin: "8px 0",
        fontFamily: "Segoe UI, system-ui, sans-serif",
      }}
    >
      <div
        id={`confirm-${pending.traceId}-title`}
        style={{ fontSize: 13, fontWeight: 600, color: tierColor[tier], marginBottom: 4 }}
      >
        {tier.toUpperCase()} action — approval required
      </div>
      <div style={{ fontSize: 13, color: "#323130", marginBottom: 6 }}>
        Agent wants to call <code>{pending.tool}</code> on{" "}
        <strong>{pending.serverId}</strong>.
      </div>
      <details style={{ marginBottom: 8 }}>
        <summary style={{ fontSize: 12, color: "#605e5c", cursor: "pointer" }}>
          arguments ({Object.keys(pending.args || {}).length} key
          {Object.keys(pending.args || {}).length === 1 ? "" : "s"})
        </summary>
        <pre
          style={{
            margin: "6px 0 0",
            padding: 8,
            background: "#fff",
            border: "1px solid #edebe9",
            borderRadius: 4,
            fontSize: 12,
            fontFamily: "Consolas, monospace",
            maxHeight: 180,
            overflow: "auto",
          }}
        >
          {JSON.stringify(pending.args || {}, null, 2)}
        </pre>
      </details>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button
          type="button"
          onClick={() => handle(true)}
          disabled={busy !== null}
          style={{
            padding: "4px 12px",
            background: tierColor[tier],
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: busy ? "not-allowed" : "pointer",
            fontSize: 12,
          }}
        >
          {busy === "approve" ? "Approving…" : "Approve"}
        </button>
        <button
          type="button"
          onClick={() => handle(false)}
          disabled={busy !== null}
          style={{
            padding: "4px 12px",
            background: "#fff",
            color: "#323130",
            border: "1px solid #8a8886",
            borderRadius: 4,
            cursor: busy ? "not-allowed" : "pointer",
            fontSize: 12,
          }}
        >
          {busy === "deny" ? "Denying…" : "Deny"}
        </button>
        {error && (
          <span style={{ fontSize: 12, color: "#a80000" }}>{error}</span>
        )}
      </div>
    </div>
  );
};
