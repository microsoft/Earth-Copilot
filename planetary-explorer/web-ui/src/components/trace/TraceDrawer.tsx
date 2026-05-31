import React, { useState } from "react";
import type { ToolTraceRow } from "./types";
import { ToolTraceChip } from "./ToolTraceChip";

/**
 * Per-turn tool-trace drawer. Renders a collapsible list of every MCP
 * call the agent made on this turn, with copy-to-clipboard JSON for
 * debugging.
 *
 * This component is presentation-only and unwired — host panels pass
 * in the rows from `useToolTrace()`. The default layout assumes a
 * docked side-panel; pass `inline` for a chat-footer treatment.
 */
export interface TraceDrawerProps {
  rows: ToolTraceRow[];
  title?: string;
  inline?: boolean;
}

export const TraceDrawer: React.FC<TraceDrawerProps> = ({ rows, title = "Tools used", inline = false }) => {
  const [openId, setOpenId] = useState<string | null>(null);

  if (rows.length === 0) {
    return null;
  }

  const containerStyle: React.CSSProperties = inline
    ? { borderTop: "1px solid #e1dfdd", padding: "8px 12px", background: "rgba(243,242,241,0.6)" }
    : {
        border: "1px solid #e1dfdd",
        borderRadius: 8,
        padding: 12,
        background: "#faf9f8",
        maxHeight: 360,
        overflowY: "auto",
        fontFamily: "Segoe UI, system-ui, sans-serif",
      };

  return (
    <div style={containerStyle} aria-label={title}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#605e5c", marginBottom: 8 }}>
        {title} ({rows.length})
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {rows.map((row) => (
          <ToolTraceChip
            key={row.traceId}
            row={row}
            onClick={() => setOpenId(openId === row.traceId ? null : row.traceId)}
          />
        ))}
      </div>
      {openId && (
        <TraceDetail row={rows.find((r) => r.traceId === openId)!} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
};

const TraceDetail: React.FC<{ row: ToolTraceRow; onClose: () => void }> = ({ row, onClose }) => {
  const payload = {
    jsonrpc: "2.0",
    method: "tools/call",
    params: { name: row.tool, arguments: row.args },
  };
  const handleCopy = () => {
    navigator.clipboard?.writeText(JSON.stringify(payload, null, 2)).catch(() => undefined);
  };
  return (
    <div
      style={{
        marginTop: 8,
        padding: 10,
        background: "#fff",
        border: "1px solid #edebe9",
        borderRadius: 6,
        fontSize: 12,
        fontFamily: "Consolas, monospace",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <strong style={{ flex: 1 }}>{row.serverId} · {row.tool}</strong>
        <span style={{ color: "#605e5c" }}>{row.tier}</span>
        {row.latencyMs != null && <span style={{ color: "#605e5c" }}>{row.latencyMs}ms</span>}
        <button type="button" onClick={handleCopy} style={{ fontSize: 11 }}>
          copy JSON-RPC
        </button>
        <button type="button" onClick={onClose} style={{ fontSize: 11 }}>
          close
        </button>
      </div>
      <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {JSON.stringify(payload, null, 2)}
      </pre>
      {row.error && (
        <div style={{ marginTop: 6, color: "#a80000" }}>error: {row.error}</div>
      )}
      {row.responseSummary && (
        <div style={{ marginTop: 6, color: "#323130" }}>
          response: <span style={{ color: "#605e5c" }}>{row.responseSummary}</span>
        </div>
      )}
    </div>
  );
};
