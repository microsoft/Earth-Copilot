"""
Raster Sampling Agent — designated MAF agent for point-value extraction.

Owns the "extract the actual numeric pixel value at a pin from a loaded
STAC raster" capability. Wraps the legacy `agents.vision_tools.sample_raster_value`
helper as its single tool call, plus an LLM-driven response shaping pass
that converts the helper's free-text reply into a concise grounded answer.

Mirrors the package layout of every other Layer-2 agent in this codebase:
  - `<id>_models.py` — Pydantic input/output
  - `<id>_agent.py`  — singleton agent with `decide()` (or `run()` here)
  - `Executors/<Decider>/` — MAF Executor wrapper
  - `__init__.py` — public exports
"""

from .raster_sampling_models import (
    RasterSamplingInput,
    RasterSamplingResult,
)
from .raster_sampling_agent import (
    RasterSamplingAgent,
    get_raster_sampling_agent,
)
from .Executors.RasterSamplingDecider.raster_sampling_decider import (  # noqa: E402
    RasterSamplingDecider,
    build_raster_sampling_workflow,
    get_raster_sampling_decider,
)

__all__ = [
    "RasterSamplingAgent",
    "RasterSamplingDecider",
    "RasterSamplingInput",
    "RasterSamplingResult",
    "build_raster_sampling_workflow",
    "get_raster_sampling_agent",
    "get_raster_sampling_decider",
]
