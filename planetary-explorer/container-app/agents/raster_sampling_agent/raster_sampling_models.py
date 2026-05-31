"""Pydantic models for the RasterSamplingAgent."""

from __future__ import annotations

from typing import Any, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


class RasterSamplingInput(BaseModel):
    """Inputs the RasterSamplingAgent needs to extract a value at a pin."""

    question: str = Field(..., description="User's natural-language question.")
    pin: Tuple[float, float] = Field(..., description="(lat, lng) of the pin.")

    bbox: Optional[Tuple[float, float, float, float]] = Field(
        None, description="Optional viewport bbox (west, south, east, north)."
    )
    loaded_collections: List[str] = Field(
        default_factory=list, description="STAC collection ids currently loaded."
    )
    stac_items: List[dict] = Field(
        default_factory=list, description="Raw STAC items rendered on the map."
    )
    tile_urls: List[str] = Field(
        default_factory=list, description="Tile URLs currently rendered."
    )
    screenshot_b64: Optional[str] = Field(
        None, description="Optional base64 screenshot for context (rarely used)."
    )

    data_type: Literal[
        "auto", "sst", "temperature", "elevation", "ndvi", "burn", "fire",
        "water", "snow", "sar", "biomass", "reflectance", "climate",
    ] = Field("auto", description="Hint that disambiguates raster bands.")


class RasterSamplingResult(BaseModel):
    """Structured output of a RasterSamplingAgent run."""

    success: bool
    answer: str = ""
    raw_value: Optional[str] = None
    data_type: str = "auto"
    pin: Optional[Tuple[float, float]] = None
    loaded_collections: List[str] = Field(default_factory=list)
    sources: List[dict] = Field(default_factory=list)
    confidence: float = 0.0
    error: Optional[str] = None
    structured: dict = Field(default_factory=dict)
    elapsed_ms: int = 0
