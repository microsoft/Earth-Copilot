"""
Pipeline data contracts (Pydantic v2).

These models are the single source of truth for the v2 pipeline. Every
analyzer consumes an `AnalysisRequest` and returns an `AnalyzerResult`. The
AnalysisRouter produces an `AnalysisPlan`. The Orchestrator merges results
into a `SynthesizedResponse`.

All fields are optional/typed conservatively so wrapping existing agents
incrementally is easy.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------ #
#  Citations and visualizations                                      #
# ------------------------------------------------------------------ #


class Source(BaseModel):
    """A citation surfaced by an analyzer.

    `kind` lets the UI route to the right renderer:
      - "doc"     -> Indexed document (clickable link to PDF/URL, e.g. Fabric AI Search hit)
      - "dataset" -> STAC collection (link to PC explorer)
      - "raster"  -> Specific raster URL/COG used for a measurement
      - "api"     -> External authoritative API response (NOAA, USGS, ...)
    """

    title: str
    uri: Optional[str] = None
    excerpt: Optional[str] = None
    kind: Literal["doc", "dataset", "raster", "api"] = "doc"
    score: Optional[float] = None


class Visualization(BaseModel):
    """A map layer or chart produced by an analyzer."""

    kind: Literal["raster_layer", "vector_layer", "chart", "marker", "heatmap"]
    spec: dict[str, Any] = Field(default_factory=dict)
    title: Optional[str] = None


# ------------------------------------------------------------------ #
#  Analyzer I/O                                                      #
# ------------------------------------------------------------------ #


class AnalysisRequest(BaseModel):
    """Input contract for every analyzer.

    Earlier analyzers' results are accessible via `grounding` so a downstream
    analyzer (e.g. terrain) can consume e.g. methodology context from earlier
    running its own analysis.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    question: str
    session_id: str

    # Spatial context
    bbox: Optional[Tuple[float, float, float, float]] = None  # WGS84 minx,miny,maxx,maxy
    location_name: Optional[str] = None
    pin: Optional[Tuple[float, float]] = None  # lat, lng
    # Multi-point comparison support. Empty unless a comparison-style turn
    # collected >=2 pins. Each entry is (lat, lng). Used by ComparisonAnalyzer.
    pins: list[Tuple[float, float]] = Field(default_factory=list)

    # Temporal context
    time_range: Optional[Tuple[str, str]] = None  # ISO 8601 pair

    # Map state
    loaded_collections: list[str] = Field(default_factory=list)
    # Compact per-collection metadata so Layer 2 can disambiguate optical vs
    # thermal vs DEM vs raw single-band rasters without re-fetching STAC.
    # Each entry is { id, title, asset_keys, band_names, gsd, eo_cloud_cover }
    # populated from `stac_items` in dispatch._build_request when available.
    loaded_collections_meta: list[dict[str, Any]] = Field(default_factory=list)
    has_screenshot: bool = False
    screenshot_url: Optional[str] = None
    screenshot_b64: Optional[str] = None
    rendered_layers: list[dict[str, Any]] = Field(default_factory=list)
    # Full STAC item dicts and titiler tile URLs for the rasters currently
    # rendered on the map. Populated by the FastAPI layer from the request
    # body when present. Used by the raster_sampling analyzer to extract
    # numeric pixel values at a pin.
    stac_items: list[dict[str, Any]] = Field(default_factory=list)
    tile_urls: list[str] = Field(default_factory=list)

    # Conversation
    history: list[dict[str, Any]] = Field(default_factory=list)

    # Chained context — populated by Orchestrator from upstream analyzers
    grounding: list["AnalyzerResult"] = Field(default_factory=list)

    # Hint from the AnalysisRouter (e.g. "methodology", "compute_anomaly")
    hint: Optional[str] = None

    # ------------------------------------------------------------------
    # Per-request UI toggles (mirrored from chat-request body)
    # ------------------------------------------------------------------
    # "public" | "pro" — echoes ``req_body.stac_mode`` so Layer 2 can
    # surface the data source on the response (source chip).
    stac_mode: str = "public"


class AnalyzerResult(BaseModel):
    """Output contract for every analyzer."""

    analyzer: str
    success: bool = True

    answer: str = ""
    structured: dict[str, Any] = Field(default_factory=dict)

    sources: list[Source] = Field(default_factory=list)
    visualizations: list[Visualization] = Field(default_factory=list)

    confidence: float = 0.0
    elapsed_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


# Forward-ref resolution for `grounding`
AnalysisRequest.model_rebuild()


# ------------------------------------------------------------------ #
#  Layer 1 — Action Router                                           #
# ------------------------------------------------------------------ #


ActionType = Literal["NAVIGATE", "LOAD", "ANALYZE", "LOAD_AND_ANALYZE"]


class ActionDecision(BaseModel):
    """Layer 1 output. One LLM call produces this."""

    action: ActionType
    location: Optional[str] = None  # for NAVIGATE / LOAD
    use_current_location: bool = False
    stac_query: Optional[str] = None  # for LOAD / LOAD_AND_ANALYZE
    analysis_question: Optional[str] = None  # for ANALYZE / LOAD_AND_ANALYZE
    reasoning: str = ""
    confidence: float = 0.0


# ------------------------------------------------------------------ #
#  Layer 2 — Analysis Router                                         #
# ------------------------------------------------------------------ #


class AnalysisStep(BaseModel):
    """One step in an AnalysisPlan."""

    analyzer: str  # registered analyzer id
    hint: Optional[str] = None
    rationale: str = ""
    # When True, this step has no data dependency on the immediately prior
    # step and may be executed concurrently with it (and any consecutive
    # parallel_with_previous steps before it). The Orchestrator batches such
    # runs with asyncio.gather. Default False = strict sequential, identical
    # to legacy behavior.
    parallel_with_previous: bool = False


class AnalysisPlan(BaseModel):
    """Ordered execution plan produced by the AnalysisRouter."""

    steps: list[AnalysisStep] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0

    def is_empty(self) -> bool:
        return not self.steps


# ------------------------------------------------------------------ #
#  Final synthesized response                                        #
# ------------------------------------------------------------------ #


class SynthesizedResponse(BaseModel):
    """What the Orchestrator hands back to the FastAPI layer."""

    answer: str
    sources: list[Source] = Field(default_factory=list)
    visualizations: list[Visualization] = Field(default_factory=list)
    structured: dict[str, dict[str, Any]] = Field(default_factory=dict)
    plan: Optional[AnalysisPlan] = None
    elapsed_ms: int = 0
