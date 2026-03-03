# Tile & Data Processing in Earth Copilot

## Overview

Nearly every module in Earth Copilot works with **Cloud-Optimized GeoTIFF (COG)** raster data retrieved from STAC catalogs. The backend queries Planetary Computer for satellite imagery, fetches COG assets, and either renders them as map tiles via TiTiler or reads raw pixel values for analysis. The one exception is the **Extreme Weather module**, which operates on NetCDF climate model data instead.

## COG/Raster Processing (Most Modules)

The following modules all query STAC collections, fetch COG assets, and process raster data:

| Module | What It Does with COG Data |
|--------|---------------------------|
| **Text Query Pipeline** | Searches STAC → fetches COG tiles via TiTiler → renders satellite imagery on the map |
| **Terrain Analysis** | Reads Sentinel-2 COG imagery, sends to Vision API for terrain feature analysis |
| **Mobility Analysis** | Downloads COG raster data from 5 collections (DEM, land cover, canopy height, soil moisture, surface water) for pixel-level terrain scoring |
| **Building Damage** | Fetches satellite COG imagery and sends to Vision API for structural damage classification |
| **Comparison** | Retrieves COG tiles from two time periods for before/after change detection |
| **Animation** | Fetches time-ordered COG tiles to generate animated GIF sequences |
| **Vision Analysis** | Renders COG data as map tile images for multimodal AI analysis |

**Processing flow:**
```
STAC Catalog → COG Assets → TiTiler / rasterio → Map Tiles or Pixel Analysis → Frontend
(metadata)     (raw data)    (server-side)         (PNG tiles or values)        (display)
```

TiTiler handles band math (NDVI, NBR, etc.), colormaps, and dynamic tile rendering directly on COG files without needing to download entire datasets.

## Extreme Weather Module (NetCDF — The Exception)

The Extreme Weather module is fundamentally different. It works with **NASA NEX-GDDP-CMIP6** climate projection data stored as **NetCDF files**, not COGs. This data cannot be rendered as map tiles.

| Aspect | COG Modules | Extreme Weather |
|--------|-------------|-----------------|
| **Data format** | Cloud-Optimized GeoTIFF | NetCDF |
| **Output** | Map tiles (visual) | Chat-based text (numerical values) |
| **Processing** | TiTiler / rasterio | xarray + h5netcdf point-sampling |
| **Resolution** | 10m–30m (Sentinel/Landsat) | ~25 km (0.25° grid) |
| **Time range** | Historical observations | 2015–2100 projections |
| **Variables** | Spectral bands (RGB, NIR, SWIR) | Temperature, precipitation, wind, humidity, radiation |

The Extreme Weather agent samples a single grid cell from remote NetCDF files at the user's coordinates and returns projected climate values — no tiles are generated or displayed on the map.

---

## Planetary Computer Pro Integration

Earth Copilot currently queries the **open Microsoft Planetary Computer** STAC API, which provides 100+ freely available collections (Sentinel-2, Landsat, MODIS, Copernicus DEM, etc.). Integrating with **Planetary Computer Pro** (GeoCatalog) would expand the platform's data capabilities significantly.

### What Planetary Computer Pro Adds

Planetary Computer Pro allows organizations to deploy their own private GeoCatalog instance and bring in new data sources beyond the open catalog:

- **Commercial high-resolution imagery** — Sub-meter optical data from providers like Maxar, Airbus, or Planet that is not available in the open Planetary Computer
- **Classified or restricted datasets** — Government or defense imagery that must stay within controlled environments
- **Custom organizational data** — Proprietary satellite collections, drone imagery, LiDAR point clouds, or other raster datasets ingested into a private STAC catalog
- **Sovereign cloud deployments** — GeoCatalog instances in Azure Government for FedRAMP/IL5 compliance

### How It Works

Earth Copilot already supports Planetary Computer Pro via the `STAC_API_URL` environment variable. Pointing this to a GeoCatalog instance routes all STAC queries to the private catalog:

```bash
# Default: Open Planetary Computer
STAC_API_URL=https://planetarycomputer.microsoft.com/api/stac/v1

# Planetary Computer Pro: Your private GeoCatalog
STAC_API_URL=https://your-geocatalog.geocatalog.azure.com/stac/v1
```

Once connected, the collection mapping agent automatically discovers available collections from the new catalog. New collection profiles can be added to `collection_profiles.py` to define rendering parameters (band combinations, colormaps, rescaling) for any custom data brought in through PC Pro.

### Impact on Modules

All COG-based modules would immediately benefit from new collections added via PC Pro — higher resolution imagery for terrain analysis, more frequent revisit times for change detection, and commercial data for building damage assessment. The Extreme Weather module would remain unchanged since it uses NASA CMIP6 data from a separate pipeline.

---

## Related Files

- `earth-copilot/container-app/collection_profiles.py` — STAC collection rendering definitions
- `earth-copilot/container-app/hybrid_rendering_system.py` — TiTiler rendering logic
- `earth-copilot/container-app/cloud_config.py` — STAC API URL and Planetary Computer Pro configuration
- `earth-copilot/container-app/geoint/extreme_weather_tools.py` — NetCDF point-sampling for climate data
- `earth-copilot/web-ui/src/utils/tileLayerFactory.ts` — Frontend tile layers
