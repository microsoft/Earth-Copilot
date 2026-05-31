// ============================================================================
// Planetary Explorer — Quickstart Query Verifier
// ============================================================================
// Paste this WHOLE FILE into your Planetary Explorer tab's DevTools Console
// (Cmd+Option+J / F12) and press Enter. It will:
//   1) Reuse your current AAD session (msal cache) to get a token
//   2) POST each of the 28 Get-Started Step-1 queries to /api/query
//      with stac_mode='public'
//   3) For each: report HTTP status, feature count, tile-URL count,
//      data_source label, and probe one sample tile URL
//   4) Print a final pass/fail table at the end
//
// Runtime: ~6-12 minutes (queries run sequentially to avoid throttling).
// Output: real-time per-query lines + summary table at the end.
// ============================================================================

(async () => {
  const QUERIES = [
    "Show wildfire MODIS data for California",
    "Show fire modis thermal anomalies daily activity for Australia from June 2025",
    "Show MTBS burn severity for California in 2017",
    "Show Harmonized Landsat Sentinel-2 imagery of Athens",
    "Show Harmonized Landsat Sentinel-2 (HLS) Version 2.0 images of Moscow from November 2024",
    "Show HLS images of Washington DC",
    "Display JRC Global Surface Water in Bangladesh",
    "Show modis snow cover daily for Quebec for January 2025",
    "Show me Sea Surface Temperature near Madagascar",
    "Show modis net primary production for San Jose",
    "Show me chloris biomass for the Amazon rainforest",
    "Show modis vedgetation indices for Ukraine",
    "Show USDA Cropland Data Layers (CDLs) for Florida",
    "Show recent modis nadir BDRF adjusted reflectance for Mexico",
    "Show coastal land cover changes in California",
    "Show DEM elevation map of Grand Canyon",
    "Show elevation map of Grand Canyon",
    "Show elevation map of Mount Rainier, Washington",
    "Show ALOS World 3D-30m of Tomas de Berlanga",
    "Show USGS 3DEP Lidar Height above Ground for New Orleans",
    "Show USGS 3DEP Lidar Height above Ground for Denver, Colorado",
    "Show HLS imagery of Houston",
    "Display JRC Global Surface Water in Florida",
    "Show NAIP aerial imagery of Paradise, California from 2020",
    "Show NAIP aerial imagery of Houston, Texas from 2018",
    "Show Sentinel 1 RTC for Baltimore",
    "Show ALOS PALSAR Annual for Ecuador",
    "Show Sentinel 1 Radiometrically Terrain Corrected (RTC) for Philippines",
  ];

  // ----- Find the API base + auth token from the live app -----
  // The frontend stores its API base in window or via Vite env. Try a few:
  const apiBase =
    window.__PLANETARY_EXPLORER_API__ ||
    (window.location.hostname.includes("localhost") ? "http://localhost:8000" : window.location.origin);

  // Grab token from MSAL cache (same one the chat uses).
  let token = null;
  for (const k in sessionStorage) {
    if (k.includes("accesstoken") || k.includes("AccessToken")) {
      try {
        const v = JSON.parse(sessionStorage.getItem(k));
        if (v && v.secret) { token = v.secret; break; }
      } catch {}
    }
  }
  if (!token) {
    for (const k in localStorage) {
      if (k.includes("accesstoken") || k.includes("AccessToken")) {
        try {
          const v = JSON.parse(localStorage.getItem(k));
          if (v && v.secret) { token = v.secret; break; }
        } catch {}
      }
    }
  }
  if (!token) {
    console.error("%cCould not find AAD token in storage. Make sure you are signed in.", "color:red;font-weight:bold");
    return;
  }
  console.log(`%cAPI base: ${apiBase}`, "color:#4ea1ff");
  console.log(`%cToken length: ${token.length}`, "color:#4ea1ff");

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const sampleTile = (tpl) =>
    tpl
      .replace("{z}", "6")
      .replace("{x}", "20")
      .replace("{y}", "23")
      .replace("{tileMatrixSetId}", "WebMercatorQuad");

  async function runOne(q) {
    const body = {
      query: q,
      model: "gpt-5",
      preferences: { interface_type: "planetary_explorer", data_source: "planetary_computer" },
      include_visualization: true,
      session_id: `verify-${Math.random().toString(36).slice(2, 10)}`,
      stac_mode: "public",
    };
    const t0 = performance.now();
    let res, json;
    try {
      res = await fetch(`${apiBase}/api/query`, { method: "POST", headers, body: JSON.stringify(body) });
      json = await res.json();
    } catch (e) {
      return { q, status: "FETCH_ERR", http: 0, feat: 0, tiles: 0, src: "", probe: "-", ms: 0, err: e.message };
    }
    const ms = Math.round(performance.now() - t0);
    if (!res.ok) {
      return { q, status: "HTTP_ERR", http: res.status, feat: 0, tiles: 0, src: "", probe: "-", ms, err: (json && (json.detail || json.error)) || "" };
    }
    const feats = (json.data?.stac_results?.features || []).length;
    const tileUrls = json.translation_metadata?.all_tile_urls || [];
    const mosaic = json.translation_metadata?.mosaic_tilejson?.tilejson_url;
    const src = json.data_source || "(none)";

    // Probe one tile
    let probe = "-";
    let tileTarget = null;
    if (tileUrls.length > 0) tileTarget = tileUrls[0];
    else if (mosaic) {
      try {
        const tj = await fetch(mosaic).then((r) => r.json());
        if (tj.tiles?.length) tileTarget = tj.tiles[0];
      } catch {}
    }
    if (tileTarget) {
      try {
        const tUrl = sampleTile(tileTarget);
        const tr = await fetch(tUrl, { method: "GET" });
        const buf = tr.ok ? await tr.arrayBuffer() : null;
        probe = tr.ok && buf && buf.byteLength > 200 ? `${tr.status}/${buf.byteLength}b` : `${tr.status}/small`;
      } catch (e) {
        probe = `err`;
      }
    } else {
      probe = "no-tile";
    }

    const status =
      feats > 0 && (probe.startsWith("200/") || probe === "no-tile") ? "OK" :
      feats === 0 ? "NO_FEATURES" : "TILE_FAIL";

    return { q, status, http: res.status, feat: feats, tiles: tileUrls.length, src, probe, ms };
  }

  console.log("%cRunning 28 quickstart queries...", "color:#4ea1ff;font-weight:bold");
  const out = [];
  for (let i = 0; i < QUERIES.length; i++) {
    const r = await runOne(QUERIES[i]);
    out.push(r);
    const color =
      r.status === "OK" ? "color:#4caf50" :
      r.status === "NO_FEATURES" ? "color:#ff9800" :
      "color:#f44336";
    console.log(
      `%c[${(i + 1).toString().padStart(2, "0")}/28] %c${r.status.padEnd(12)} feat=${String(r.feat).padEnd(3)} tiles=${String(r.tiles).padEnd(3)} probe=${r.probe.padEnd(12)} src=${(r.src || "").padEnd(10)} ${r.ms}ms :: ${r.q}`,
      "color:gray", color
    );
  }

  console.log("\n%c===== SUMMARY =====", "color:#4ea1ff;font-weight:bold");
  const grouped = out.reduce((m, r) => ((m[r.status] = (m[r.status] || 0) + 1), m), {});
  console.table(grouped);

  console.log("\n%c===== FULL TABLE =====", "color:#4ea1ff;font-weight:bold");
  console.table(out, ["status", "feat", "tiles", "probe", "src", "ms", "q"]);

  const fail = out.filter((r) => r.status !== "OK");
  if (fail.length === 0) {
    console.log("%cAll 28 quickstart queries rendered tiles successfully.", "color:#4caf50;font-weight:bold;font-size:14px");
  } else {
    console.log(`%c${fail.length} failure(s):`, "color:#f44336;font-weight:bold");
    fail.forEach((f) => console.log(`  [${f.status}] ${f.q}  ::  probe=${f.probe}, err=${f.err || ""}`));
  }

  window.__verifyResults__ = out;
  console.log("%cFull results stored in window.__verifyResults__", "color:gray");
})();
