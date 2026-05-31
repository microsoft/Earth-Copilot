import React from "react";
import type { ToolTraceRow } from "./types";

const TIER_STYLES: Record<string, React.CSSProperties> = {
  read: { background: "rgba(0, 120, 212, 0.10)", color: "#0078d4", border: "1px solid rgba(0,120,212,0.30)" },
  write: { background: "rgba(202, 80, 16, 0.10)", color: "#ca5010", border: "1px solid rgba(202,80,16,0.30)" },
  destructive: { background: "rgba(168, 0, 0, 0.10)", color: "#a80000", border: "1px solid rgba(168,0,0,0.30)" },
};

const STATUS_GLYPH: Record<string, string> = {
  pending: "...",
  ok: "ok",
  error: "err",
  denied: "denied",
};

/**
 * Compact one-line badge for a single MCP tool call. Drop in-line in
 * the chat message footer (next to provenance chips).
 */
export const ToolTraceChip: React.FC<{ row: ToolTraceRow; onClick?: () => void }> = ({
  row,
  onClick,
}) => {
  const tierStyle = TIER_STYLES[row.tier] ?? TIER_STYLES.read;
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${row.serverId} · ${row.tool} (${row.tier})${row.latencyMs != null ? ` · ${row.latencyMs}ms` : ""}`}
      style={{
        ...tierStyle,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 11,
        lineHeight: "16px",
        fontFamily: "Segoe UI, system-ui, sans-serif",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <span style={{ fontWeight: 600 }}>{row.tool}</span>
      <span style={{ opacity: 0.7 }}>{STATUS_GLYPH[row.status] ?? row.status}</span>
      {row.latencyMs != null && (
        <span style={{ opacity: 0.6 }}>{row.latencyMs}ms</span>
      )}
    </button>
  );
};
