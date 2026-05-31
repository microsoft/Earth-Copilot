"""
Layer-2 Clarifier Agent — modality + analyzer chooser.

Runs after the Layer-1 clarifier (or v2 ActionRouter) has decided the user
wants `vision_analysis` / `hybrid` (i.e. `ANALYZE` / `LOAD_AND_ANALYZE`).
Decides TEXT / VISION / BOTH and the specific Layer-2 analyzer, asking one
focused follow-up when needed.

Public surface:
    >>> from agents.layer2_clarifier_agent import (
    ...     get_layer2_clarifier_agent, Layer2ClarifierInput,
    ... )
    >>> agent = get_layer2_clarifier_agent()
    >>> decision = await agent.decide(Layer2ClarifierInput(
    ...     query="Sample the surface reflectance bands here",
    ...     target_route="vision_analysis",
    ...     has_rendered_map=True,
    ...     has_pin=True, pin_lat=47.6, pin_lng=-122.3,
    ...     loaded_collections=["sentinel-2-l2a"],
    ... ))
    >>> decision.analyzer_kind, decision.analyzer
    ('vision', 'raster_sampling')
"""

from .layer2_clarifier_models import Layer2ClarifierDecision, Layer2ClarifierInput
from .layer2_clarifier_agent import (
    Layer2ClarifierAgent,
    get_layer2_clarifier_agent,
)
from .Executors.Layer2ClarifierDecider.layer2_clarifier_decider import (  # noqa: E402
    Layer2ClarifierDecider,
    build_layer2_clarifier_workflow,
    get_layer2_clarifier_decider,
)

__all__ = [
    "Layer2ClarifierAgent",
    "Layer2ClarifierDecider",
    "Layer2ClarifierDecision",
    "Layer2ClarifierInput",
    "build_layer2_clarifier_workflow",
    "get_layer2_clarifier_agent",
    "get_layer2_clarifier_decider",
]
