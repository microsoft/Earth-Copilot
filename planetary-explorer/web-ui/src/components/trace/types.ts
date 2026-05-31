/**
 * Tool trace event shapes — match the backend's `mcp_runtime.TraceEntry`
 * after JSON serialisation. Two event types arrive on SSE for any route
 * that wraps its generator with `_framework.merge_with_trace`:
 *
 *   { type: "tool_call",   trace_id, server_id, tool, args, tier, ... }
 *   { type: "tool_result", trace_id, server_id, tool, ok, error,
 *                          latency_ms, response_summary, ... }
 *
 * Permission tier classification is computed server-side; the UI uses
 * it only to colour-code chips and (eventually) gate confirmation
 * cards.
 */
export type PermissionTier = "read" | "write" | "destructive";

export interface ToolCallEvent {
  type: "tool_call";
  trace_id: string;
  turn_id: string;
  server_id: string;
  tool: string;
  args: Record<string, unknown>;
  tier: PermissionTier;
  started_at: number;
}

export interface ToolResultEvent {
  type: "tool_result";
  trace_id: string;
  turn_id: string;
  server_id: string;
  tool: string;
  args: Record<string, unknown>;
  tier: PermissionTier;
  started_at: number;
  finished_at: number;
  latency_ms: number;
  ok: boolean;
  response_summary?: string | null;
  error?: string | null;
}

export type ToolTraceEvent = ToolCallEvent | ToolResultEvent;

/**
 * A consolidated row keyed by ``trace_id`` — collapses the matching
 * ``tool_call`` + ``tool_result`` pair into one renderable record.
 */
export interface ToolTraceRow {
  traceId: string;
  serverId: string;
  tool: string;
  tier: PermissionTier;
  args: Record<string, unknown>;
  status: "pending" | "ok" | "error" | "denied";
  latencyMs?: number;
  responseSummary?: string | null;
  error?: string | null;
}
