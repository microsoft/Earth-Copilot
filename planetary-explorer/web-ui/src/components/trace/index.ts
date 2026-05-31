/**
 * Tool-trace UI components — presentation-only, unwired by default.
 *
 * Wiring:
 *
 *   const { rows, ingest } = useToolTrace();
 *   // SSE consumer:
 *   if (evt.type === "tool_call" || evt.type === "tool_result") ingest(evt);
 *
 *   <TraceDrawer rows={rows} inline />
 *
 * The hook + components have zero dependencies on the rest of the
 * web-ui, so forks can drop them into a custom chat surface without
 * pulling in the whole panel stack.
 */
export { TraceDrawer } from "./TraceDrawer";
export { ToolTraceChip } from "./ToolTraceChip";
export { useToolTrace } from "./useToolTrace";
export { ConfirmationCard } from "./ConfirmationCard";
export type { PendingConfirm } from "./ConfirmationCard";
export type { PermissionTier, ToolTraceEvent, ToolTraceRow } from "./types";
