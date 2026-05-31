#!/usr/bin/env node
// =============================================================================
// bridge.mjs
//
// stdio <-> streamable-HTTP bridge for Microsoft's GeoCatalog STAC MCP Server.
//
// The vendored upstream binary at ./vendor/server_main.js (MIT, see
// vendor/PROVENANCE.md) only speaks the stdio MCP transport. The Planetary Explorer
// backend, however, runs inside another Container App and needs a network-
// accessible MCP server. This bridge:
//
//   * spawns ONE long-lived stdio child running the vendored binary,
//   * connects an MCP Client to it via StdioClientTransport,
//   * exposes a streamable-HTTP MCP Server (node:http + the MCP SDK's
//     StreamableHTTPServerTransport), and
//   * proxies tools/* + resources/* + prompts/* requests from inbound HTTP
//     sessions to that single upstream Client.
//
// We deliberately keep the upstream child SINGLE and long-lived. The upstream
// binary is in-memory only -- no per-request state worth isolating -- and
// reusing one stdio process eliminates ~hundred-ms cold-start per call.
//
// Auth is handled outside this process: docker-entrypoint.sh runs
// ``az login --identity`` before exec-ing us, so the upstream's
// AzureCliCredential finds a valid token cache. See vendor/PROVENANCE.md.
// =============================================================================

import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { resolve as pathResolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  GetPromptRequestSchema,
  ListPromptsRequestSchema,
  ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// -----------------------------------------------------------------------------
// Config
// -----------------------------------------------------------------------------

const HERE = pathResolve(fileURLToPath(import.meta.url), "..");
const VENDOR_BIN = process.env.MPC_MCP_VENDOR_BIN ?? pathResolve(HERE, "vendor/server_main.js");
const HOST = process.env.MCP_HTTP_HOST ?? "0.0.0.0";
const PORT = Number(process.env.MCP_HTTP_PORT ?? "8080");
const BRIDGE_NAME = "planetary-explorer-mpc-mcp-bridge";
const BRIDGE_VERSION = process.env.MPC_MCP_BRIDGE_VERSION ?? "1.0.9";

// -----------------------------------------------------------------------------
// Structured logging (one JSON object per line to stderr)
// -----------------------------------------------------------------------------

function log(level, msg, extra) {
  const rec = { ts: new Date().toISOString(), level, component: "bridge", msg, ...(extra ?? {}) };
  try {
    process.stderr.write(JSON.stringify(rec) + "\n");
  } catch {
    // never let logging crash the process
  }
}

// -----------------------------------------------------------------------------
// Upstream stdio child + Client (single long-lived connection)
// -----------------------------------------------------------------------------

async function connectUpstream() {
  log("info", "spawning upstream stdio child", { bin: VENDOR_BIN });
  const transport = new StdioClientTransport({
    command: "node",
    args: [VENDOR_BIN],
    env: process.env,
    stderr: "inherit",
  });
  const client = new Client(
    { name: BRIDGE_NAME, version: BRIDGE_VERSION },
    { capabilities: {} },
  );
  await client.connect(transport);
  const info = client.getServerVersion?.();
  log("info", "upstream connected", { serverInfo: info ?? null });
  return { client, transport };
}

let upstreamPromise = connectUpstream().catch((err) => {
  log("error", "failed to connect to upstream", { error: String(err?.stack ?? err) });
  // Without an upstream there is nothing useful to do. Exit non-zero so the
  // container restarts under Container Apps' supervision.
  process.exit(1);
});

async function getUpstream() {
  return (await upstreamPromise).client;
}

// -----------------------------------------------------------------------------
// Per-session bridge Server (one instance per HTTP MCP session)
// -----------------------------------------------------------------------------

function buildProxyServer() {
  const server = new Server(
    { name: BRIDGE_NAME, version: BRIDGE_VERSION },
    {
      capabilities: {
        tools: { listChanged: false },
        resources: { listChanged: false },
        prompts: { listChanged: false },
      },
    },
  );

  // -- tools ----------------------------------------------------------------
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const u = await getUpstream();
    return await u.listTools();
  });
  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const u = await getUpstream();
    return await u.callTool(req.params);
  });

  // -- resources ------------------------------------------------------------
  // Some upstream tools advertise resources/templates; safe to forward.
  // Swallow "method not supported" so the bridge degrades gracefully if the
  // upstream stops advertising a capability across version bumps.
  server.setRequestHandler(ListResourcesRequestSchema, async () => {
    const u = await getUpstream();
    try {
      return await u.listResources();
    } catch (err) {
      log("debug", "upstream listResources failed; returning empty", { error: String(err) });
      return { resources: [] };
    }
  });
  server.setRequestHandler(ListResourceTemplatesRequestSchema, async () => {
    const u = await getUpstream();
    try {
      return await u.listResourceTemplates();
    } catch (err) {
      log("debug", "upstream listResourceTemplates failed; returning empty", { error: String(err) });
      return { resourceTemplates: [] };
    }
  });
  server.setRequestHandler(ReadResourceRequestSchema, async (req) => {
    const u = await getUpstream();
    return await u.readResource(req.params);
  });

  // -- prompts --------------------------------------------------------------
  server.setRequestHandler(ListPromptsRequestSchema, async () => {
    const u = await getUpstream();
    try {
      return await u.listPrompts();
    } catch (err) {
      log("debug", "upstream listPrompts failed; returning empty", { error: String(err) });
      return { prompts: [] };
    }
  });
  server.setRequestHandler(GetPromptRequestSchema, async (req) => {
    const u = await getUpstream();
    return await u.getPrompt(req.params);
  });

  return server;
}

// -----------------------------------------------------------------------------
// HTTP layer (node:http -- no express dep to keep the surface small)
// -----------------------------------------------------------------------------

/** sessionId -> { transport } */
const sessions = new Map();

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (chunks.length === 0) return undefined;
  const text = Buffer.concat(chunks).toString("utf8");
  if (!text.trim()) return undefined;
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`invalid JSON body: ${err?.message ?? err}`);
  }
}

function sendJson(res, status, body, extraHeaders = {}) {
  if (res.headersSent) {
    res.end();
    return;
  }
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", ...extraHeaders });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
}

// Cached health probe so /healthz at every-30s probe interval doesn't hammer
// the upstream child. Refresh on TTL miss only.
const HEALTH_TTL_MS = 5_000;
let healthCache = { at: 0, ok: false, detail: "uninitialized" };
async function checkHealth() {
  const now = Date.now();
  if (now - healthCache.at < HEALTH_TTL_MS) return healthCache;
  try {
    const u = await getUpstream();
    const tools = await u.listTools();
    healthCache = { at: now, ok: true, detail: `tools=${tools?.tools?.length ?? 0}` };
  } catch (err) {
    healthCache = { at: now, ok: false, detail: String(err?.message ?? err) };
  }
  return healthCache;
}

const httpServer = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  try {
    if (url.pathname === "/healthz") {
      const h = await checkHealth();
      return sendJson(res, h.ok ? 200 : 503, { status: h.ok ? "ok" : "unavailable", detail: h.detail });
    }
    if (url.pathname !== "/mcp") {
      return sendJson(res, 404, { error: "not found" });
    }

    const sidHdr = req.headers["mcp-session-id"];
    const sessionId = Array.isArray(sidHdr) ? sidHdr[0] : sidHdr;

    // Existing session: dispatch to its transport.
    if (sessionId && sessions.has(sessionId)) {
      const { transport } = sessions.get(sessionId);
      const body = req.method === "POST" ? await readJsonBody(req) : undefined;
      return await transport.handleRequest(req, res, body);
    }

    // New session: must be a POST (initialize request).
    if (req.method !== "POST") {
      return sendJson(res, 400, { error: "invalid or missing Mcp-Session-Id" });
    }

    const body = await readJsonBody(req);
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
      onsessioninitialized: (sid) => {
        sessions.set(sid, { transport });
        log("info", "session initialized", { sid, totalSessions: sessions.size });
      },
    });
    transport.onclose = () => {
      const sid = transport.sessionId;
      if (sid) {
        sessions.delete(sid);
        log("info", "session closed", { sid, totalSessions: sessions.size });
      }
    };
    const server = buildProxyServer();
    await server.connect(transport);
    return await transport.handleRequest(req, res, body);
  } catch (err) {
    log("error", "request failed", {
      url: req.url,
      method: req.method,
      error: String(err?.stack ?? err),
    });
    if (!res.headersSent) sendJson(res, 500, { error: String(err?.message ?? err) });
    else res.end();
  }
});

httpServer.listen(PORT, HOST, () => {
  log("info", "bridge listening", { host: HOST, port: PORT, vendorBin: VENDOR_BIN });
});

// -----------------------------------------------------------------------------
// Graceful shutdown
// -----------------------------------------------------------------------------

let shuttingDown = false;
async function shutdown(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  log("info", "shutting down", { reason });
  try {
    httpServer.close();
  } catch {}
  try {
    const { client } = await upstreamPromise;
    await client.close();
  } catch {}
  // Give in-flight requests a moment to flush, then exit.
  setTimeout(() => process.exit(0), 1500).unref();
}
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("uncaughtException", (err) => {
  log("error", "uncaughtException", { error: String(err?.stack ?? err) });
  shutdown("uncaughtException");
});
process.on("unhandledRejection", (err) => {
  log("error", "unhandledRejection", { error: String(err?.stack ?? err) });
});
