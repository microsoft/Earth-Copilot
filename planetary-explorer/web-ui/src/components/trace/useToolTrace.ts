import { useCallback, useMemo, useRef, useState } from "react";
import type {
  PermissionTier,
  ToolCallEvent,
  ToolResultEvent,
  ToolTraceEvent,
  ToolTraceRow,
} from "./types";

/**
 * Reduce a stream of `tool_call` / `tool_result` SSE events into a
 * stable list of trace rows. Designed to be fed from any SSE consumer:
 *
 *     const { rows, ingest, clear } = useToolTrace();
 *     // when an SSE event arrives:
 *     if (evt.type === "tool_call" || evt.type === "tool_result") ingest(evt);
 *
 * The hook is presentation-only — it does not open the EventSource
 * itself, so panels can plug it into whatever fetch/SSE wiring they
 * already have without coupling.
 */
export function useToolTrace() {
  const [rows, setRows] = useState<ToolTraceRow[]>([]);
  const byId = useRef<Map<string, ToolTraceRow>>(new Map());

  const ingest = useCallback((evt: ToolTraceEvent) => {
    if (evt.type === "tool_call") {
      const e = evt as ToolCallEvent;
      const row: ToolTraceRow = {
        traceId: e.trace_id,
        serverId: e.server_id,
        tool: e.tool,
        tier: e.tier,
        args: e.args ?? {},
        status: "pending",
      };
      byId.current.set(e.trace_id, row);
    } else if (evt.type === "tool_result") {
      const e = evt as ToolResultEvent;
      const existing =
        byId.current.get(e.trace_id) ?? {
          traceId: e.trace_id,
          serverId: e.server_id,
          tool: e.tool,
          tier: e.tier,
          args: e.args ?? {},
          status: "pending" as const,
        };
      const denied = e.error === "denied_by_user";
      byId.current.set(e.trace_id, {
        ...existing,
        status: denied ? "denied" : e.ok ? "ok" : "error",
        latencyMs: e.latency_ms,
        responseSummary: e.response_summary ?? undefined,
        error: e.error ?? undefined,
      });
    } else {
      return;
    }
    setRows(Array.from(byId.current.values()));
  }, []);

  const clear = useCallback(() => {
    byId.current.clear();
    setRows([]);
  }, []);

  const counts = useMemo(() => {
    const c = { total: rows.length, read: 0, write: 0, destructive: 0, error: 0 };
    for (const r of rows) {
      c[r.tier as PermissionTier]++;
      if (r.status === "error" || r.status === "denied") c.error++;
    }
    return c;
  }, [rows]);

  return { rows, counts, ingest, clear };
}
