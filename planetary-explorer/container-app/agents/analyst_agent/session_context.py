"""Per-call session context shared between AnalystAgent and its tool functions.

Tools cannot accept the full ~12-field AnalysisRequest as an argument
(it would blow up the function-calling JSON schema and pollute the
LLM's reasoning). Instead, AnalystAgent populates a ContextVar with
the current request before running, and tools read it via
``get_session()``.

Pattern mirrors ``agents/vision_tools.set_session_context()``.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AnalystSession:
    """Snapshot of the AnalysisRequest visible to tool functions."""

    question: str = ""
    session_id: str = "default"
    pin: Optional[Tuple[float, float]] = None
    pins: List[Tuple[float, float]] = field(default_factory=list)
    bbox: Optional[Tuple[float, float, float, float]] = None
    location_name: Optional[str] = None
    time_range: Optional[Tuple[str, str]] = None
    loaded_collections: List[str] = field(default_factory=list)
    loaded_collections_meta: List[Dict[str, Any]] = field(default_factory=list)
    screenshot_b64: Optional[str] = None
    screenshot_url: Optional[str] = None
    has_screenshot: bool = False
    stac_items: List[Dict[str, Any]] = field(default_factory=list)
    tile_urls: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    hint: Optional[str] = None
    # Per-request feature toggles (mirrors UI controls).
    # When ``use_graphrag`` is False the search_graphrag tool short-circuits
    # with a skip result so the agent falls back to general_earth_qa or
    # map-context tools without burning a sidecar round-trip.
    use_graphrag: bool = True
    # "public" | "pro" — informational mirror of the STAC mode applied
    # upstream by ``_apply_stac_mode_override``. Surfaced to the chat UI
    # as a source chip; not used for routing inside Layer 2.
    stac_mode: str = "public"
    # Tool-call evidence chain (populated as tools run)
    evidence: List[Dict[str, Any]] = field(default_factory=list)


_CURRENT: ContextVar[Optional[AnalystSession]] = ContextVar(
    "analyst_session", default=None
)


def set_session(session: AnalystSession) -> None:
    _CURRENT.set(session)


def get_session() -> AnalystSession:
    s = _CURRENT.get()
    if s is None:
        # Fail-open: empty session rather than raise — tools degrade gracefully.
        s = AnalystSession()
        _CURRENT.set(s)
    return s


def clear_session() -> None:
    _CURRENT.set(None)
