#!/usr/bin/env node
// Liveness/readiness probe used by Docker HEALTHCHECK and Container Apps
// httpGet probes. Exits 0 on /healthz=200, non-zero otherwise.
import http from "node:http";

const port = process.env.MCP_HTTP_PORT ?? "8080";
const url = `http://127.0.0.1:${port}/healthz`;

const req = http.get(url, (res) => {
  // Drain to free the socket promptly.
  res.resume();
  res.on("end", () => process.exit(res.statusCode === 200 ? 0 : 1));
});
req.setTimeout(5_000, () => {
  req.destroy(new Error("healthcheck timeout"));
  process.exit(1);
});
req.on("error", (err) => {
  process.stderr.write(`healthcheck error: ${err.message}\n`);
  process.exit(1);
});
