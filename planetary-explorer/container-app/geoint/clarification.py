"""
Clarification / Slot-Filling State Machine
==========================================

Adds multi-turn clarification to the RouterAgent. When a query is ambiguous
or missing required information, the bot asks one focused follow-up question
(with quick-pick chips) and accumulates answers across turns until every slot
required by the chosen route is filled. Then it executes.

Design goals:
- Pure logic: no I/O, no async. Caller (fastapi_app) handles persistence and
  dispatch.
- Route-aware: every clarification names a target route and a missing slot.
- Multi-turn accumulation: a single user message can fill multiple slots.
- Safety caps: per-slot retries and total-turn caps prevent infinite loops.
- Cancel / restart keywords gracefully exit the loop.

Public surface:
- ROUTE_SLOTS                         — required slots per route
- ClarificationState                  — serializable state object
- start_clarification(...)            — kick off a new clarification
- next_action(state, msg, ctx)        — advance one turn (the state machine)
- slots_to_router_action(...)         — convert filled slots to router_action
- extract_slots(text, route)          — opportunistic multi-slot extraction
- infer_route(slots, ctx)             — pick route from accumulated slots

The result of next_action() is one of:
- {"kind": "ask",     "router_action": {...clarify action...}}
- {"kind": "execute", "router_action": {...real route action...}}
- {"kind": "escape",  "router_action": {...help/contextual action...}}
- {"kind": "cancel"}                  — caller should clear state and proceed normally
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Required slots per route. Order matters: we ask in this order.
ROUTE_SLOTS: Dict[str, List[str]] = {
    "navigate_to":     ["location"],
    "stac_search":     ["location", "collection"],
    "vision_analysis": ["has_imagery", "question"],
    "contextual":      ["question"],
    "hybrid":          ["location", "collection", "analysis_target"],
}

# Optional slots — never block execution, but accept if user volunteers them.
OPTIONAL_SLOTS: Dict[str, List[str]] = {
    "stac_search":     ["time_range"],
    "hybrid":          ["time_range"],
}

MAX_ATTEMPTS_PER_SLOT = 2
MAX_TOTAL_TURNS = 4

CANCEL_KEYWORDS = {
    "cancel", "nevermind", "never mind", "stop", "start over",
    "reset", "forget it", "abort", "quit",
}

# Quick-pick chip → intent route
INTENT_CHIP_MAP = {
    "go to a place":             "navigate_to",
    "load satellite imagery":    "stac_search",
    "analyze what's on the map": "vision_analysis",
    "ask a general question":    "contextual",
}

# Imagery-not-loaded chips for the vision route
IMAGERY_LOAD_CHIPS = {
    "yes — sentinel-2 here":    ("stac_search", "sentinel-2-l2a"),
    "yes - sentinel-2 here":    ("stac_search", "sentinel-2-l2a"),
    "yes — pick a location":    ("stac_search", None),
    "yes - pick a location":    ("stac_search", None),
}
IMAGERY_SKIP_CHIPS = {
    "no, ask a general question": "contextual",
    "no — ask a general question": "contextual",
}

# Default chip sets per (route, slot)
DEFAULT_LOCATION_CHIPS    = ["Seattle", "Tokyo", "Amazon", "Sahara"]
DEFAULT_COLLECTION_CHIPS  = ["Sentinel-2 (optical)", "Landsat", "HLS", "Elevation (DEM)"]
DEFAULT_TIME_CHIPS        = ["Latest", "Last 30 days", "Last year", "Custom date range"]
DEFAULT_ANALYSIS_CHIPS    = [
    "Land cover change", "Flood extent", "Vegetation (NDVI)", "Just describe what I see",
]
DEFAULT_INTENT_CHIPS      = list(INTENT_CHIP_MAP.keys())
DEFAULT_IMAGERY_CHIPS     = [
    "Yes — Sentinel-2 here",
    "Yes — pick a location",
    "No, ask a general question",
]


# Keyword sets used for opportunistic slot extraction.
_ANALYSIS_KEYWORDS = {
    "flood":            "Flood extent",
    "flooding":         "Flood extent",
    "fire":             "Fire activity",
    "wildfire":         "Fire activity",
    "burn":             "Burn severity",
    "vegetation":       "Vegetation (NDVI)",
    "ndvi":             "Vegetation (NDVI)",
    "land cover":       "Land cover change",
    "land use":         "Land cover change",
    "snow":             "Snow cover",
    "drought":          "Drought conditions",
    "deforestation":    "Deforestation",
    "damage":           "Damage assessment",
    "describe":         "Describe what's visible",
    "analyze":          "Describe what's visible",
}

_QUESTION_PREFIXES = (
    "what", "how", "why", "when", "where", "who", "which",
    "describe", "explain", "tell me", "is there", "are there", "can you",
)


# ============================================================================
# STATE
# ============================================================================

@dataclass
class ClarificationState:
    """Serializable clarification state (lives in session_context['pending_clarification'])."""
    target_route:        Optional[str]            = None
    original_query:      str                      = ""
    slots:               Dict[str, Any]           = field(default_factory=dict)
    awaiting_slot:       Optional[str]            = None
    attempts_per_slot:   Dict[str, int]           = field(default_factory=dict)
    total_attempts:      int                      = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_route":      self.target_route,
            "original_query":    self.original_query,
            "slots":             dict(self.slots),
            "awaiting_slot":     self.awaiting_slot,
            "attempts_per_slot": dict(self.attempts_per_slot),
            "total_attempts":    self.total_attempts,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["ClarificationState"]:
        if not data:
            return None
        return cls(
            target_route      = data.get("target_route"),
            original_query    = data.get("original_query", ""),
            slots             = dict(data.get("slots") or {}),
            awaiting_slot     = data.get("awaiting_slot"),
            attempts_per_slot = dict(data.get("attempts_per_slot") or {}),
            total_attempts    = int(data.get("total_attempts") or 0),
        )


# ============================================================================
# SYNC EXTRACTION HELPERS (no async, no network)
# ============================================================================

def _load_known_locations() -> set:
    """Load STORED_LOCATIONS keys lazily so this module has no hard import dep."""
    try:
        from location_resolver import EnhancedLocationResolver  # type: ignore
        return set(EnhancedLocationResolver.STORED_LOCATIONS.keys())
    except Exception as e:
        logger.warning(f"clarification: could not load STORED_LOCATIONS: {e}")
        return set()


def _load_collection_keywords() -> Dict[str, List[str]]:
    """Lazy-load collection keyword map → list of collection ids."""
    try:
        from collection_name_mapper import CollectionMapper  # type: ignore
        cm = CollectionMapper()
        return dict(cm.keyword_map)
    except Exception as e:
        logger.warning(f"clarification: could not load CollectionMapper: {e}")
        return {}


_KNOWN_LOCATIONS: Optional[set] = None
_COLLECTION_KEYWORDS: Optional[Dict[str, List[str]]] = None


def _known_locations() -> set:
    global _KNOWN_LOCATIONS
    if _KNOWN_LOCATIONS is None:
        _KNOWN_LOCATIONS = _load_known_locations()
    return _KNOWN_LOCATIONS


def _collection_keywords() -> Dict[str, List[str]]:
    global _COLLECTION_KEYWORDS
    if _COLLECTION_KEYWORDS is None:
        _COLLECTION_KEYWORDS = _load_collection_keywords()
    return _COLLECTION_KEYWORDS


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip("?.!,;:")


def is_cancel(text: str) -> bool:
    n = _norm(text)
    return n in CANCEL_KEYWORDS or any(n.startswith(k + " ") for k in CANCEL_KEYWORDS)


# ----- Per-slot extractors -------------------------------------------------

def _extract_location(text: str) -> Optional[str]:
    """Match against STORED_LOCATIONS (substring, longest first)."""
    n = _norm(text)
    if not n:
        return None
    locs = _known_locations()
    if not locs:
        return None
    if n in locs:
        return n
    # longest-first substring match to avoid 'iran' matching inside 'tehran, iran'
    for loc in sorted(locs, key=len, reverse=True):
        if len(loc) < 3:
            continue
        if re.search(r"\b" + re.escape(loc) + r"\b", n):
            return loc
    return None


def _extract_collection(text: str) -> Optional[str]:
    """Resolve a collection slot from free-text input.

    Resolution order:

    1. **STAC-id pass-through.** Any whitespace-delimited token that *looks
       like* a STAC collection id (kebab-case, contains a hyphen, lowercase
       alnum + ``._-``) is accepted as-is. This makes the slot filler
       dynamic by construction: when a new collection is published to MPC
       Pro / GeoCatalog (e.g. ``sentinel2-fire``), users can reference it
       by id without anyone editing the keyword map. The downstream Pro
       remapper still validates the id against the live catalog.

    2. **Pro catalog ids.** Match against the cached list of live Pro
       collection ids (populated by ``get_pro_collection_ids``). This
       catches ids that don't have hyphens or that overlap a stop word.

    3. **Friendly keyword map.** ``CollectionMapper.keyword_map`` for
       human-typed synonyms (``"wildfire"``, ``"swir fire"``,
       ``"true color"``).
    """
    n = _norm(text)
    if not n:
        return None

    # 1) STAC-id-shaped tokens win. Use the same regex CollectionMapper
    # exposes so the two stay in sync.
    try:
        from collection_name_mapper import CollectionMapper  # type: ignore
        stac_id_re = CollectionMapper._STAC_ID_TOKEN_RE
    except Exception:
        stac_id_re = re.compile(r"^[a-z][a-z0-9._]*-[a-z0-9._-]+$")
    for tok in re.split(r"\s+", n):
        tok = tok.strip(".,;:!?\"'()[]{}")
        if tok and stac_id_re.match(tok):
            return tok

    # 2) Live Pro catalog ids (best-effort, non-blocking).
    pro_ids: List[str] = []
    try:
        from pro_stac_client import _collection_ids_cache  # type: ignore
        _, cached = _collection_ids_cache
        pro_ids = list(cached or [])
    except Exception:
        pro_ids = []
    for cid in sorted(pro_ids, key=len, reverse=True):
        if len(cid) < 3:
            continue
        if re.search(r"\b" + re.escape(cid.lower()) + r"\b", n):
            return cid

    # 3) Friendly keyword map (last resort).
    kw_map = _collection_keywords()
    for kw in sorted(kw_map.keys(), key=len, reverse=True):
        if len(kw) < 2:
            continue
        if re.search(r"\b" + re.escape(kw) + r"\b", n):
            return kw
    return None


_TIME_RE = re.compile(
    r"\b("
    r"latest|now|today|current|this (?:week|month|year)|"
    r"last (?:\d+\s+)?(?:day|days|week|weeks|month|months|year|years)|"
    r"\d{4}(?:-\d{1,2})?(?:/\d{4}(?:-\d{1,2})?)?|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"(?:\s+\d{4})?"
    r")\b",
    re.IGNORECASE,
)


def _extract_time_range(text: str) -> Optional[str]:
    if not text:
        return None
    m = _TIME_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_analysis_target(text: str) -> Optional[str]:
    n = _norm(text)
    if not n:
        return None
    for kw, label in _ANALYSIS_KEYWORDS.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", n):
            return label
    return None


def _looks_like_question(text: str) -> bool:
    n = _norm(text)
    if not n:
        return False
    if "?" in (text or ""):
        return True
    return any(n.startswith(p) for p in _QUESTION_PREFIXES)


# ----- Public extraction --------------------------------------------------

def extract_slots(text: str, route: Optional[str] = None) -> Dict[str, Any]:
    """
    Opportunistic multi-slot extraction. Pulls out any slots the message
    plausibly contains. The caller decides which to merge based on `route`
    and which slots are still empty.
    """
    out: Dict[str, Any] = {}
    if not text:
        return out

    loc = _extract_location(text)
    if loc:
        out["location"] = loc

    coll = _extract_collection(text)
    if coll:
        out["collection"] = coll

    tr = _extract_time_range(text)
    if tr:
        out["time_range"] = tr

    if route in (None, "vision_analysis", "hybrid"):
        at = _extract_analysis_target(text)
        if at:
            out["analysis_target"] = at

    if route in (None, "contextual", "vision_analysis"):
        if _looks_like_question(text):
            out["question"] = text.strip()

    return out


# ----- Validation / acceptance --------------------------------------------

def _accept_awaiting_answer(
    state: ClarificationState,
    user_msg: str,
    has_imagery: bool,
) -> Tuple[bool, Optional[str]]:
    """
    When the user is replying directly to the slot we asked about, accept
    their message AS the slot value (with light validation). Returns
    (accepted, optional_route_change). If accepted, state.slots is updated.
    """
    slot = state.awaiting_slot
    if not slot:
        return False, None

    raw = (user_msg or "").strip()
    n   = _norm(raw)
    if not n:
        return False, None

    # Intent disambiguation
    if slot == "intent":
        new_route = INTENT_CHIP_MAP.get(n)
        if new_route:
            state.target_route = new_route
            state.slots["_intent_resolved"] = True
            return True, new_route
        # Free-text intent: re-route via opportunistic extraction
        # (handled by infer_route on the caller side)
        return False, None

    # Vision pre-condition: imagery-or-not chips
    if slot == "has_imagery":
        if n in IMAGERY_LOAD_CHIPS:
            new_route, coll = IMAGERY_LOAD_CHIPS[n]
            state.target_route = new_route
            if coll:
                state.slots["collection"] = coll
            state.slots["has_imagery"] = True   # promised, will be true after STAC
            return True, new_route
        if n in IMAGERY_SKIP_CHIPS:
            new_route = IMAGERY_SKIP_CHIPS[n]
            state.target_route = new_route
            # Treat the original query as the question for contextual
            state.slots.setdefault("question", state.original_query)
            return True, new_route
        return False, None

    if slot == "location":
        # Trust the user's reply when we asked for a location.
        # Downstream resolver (location_resolver) will geocode; if it fails
        # the navigate handler already has fallbacks.
        if len(n) >= 2 and not _looks_like_question(raw):
            state.slots["location"] = raw.strip().title() if raw.islower() else raw.strip()
            return True, None
        return False, None

    if slot == "collection":
        # Try to map the answer to a known collection keyword.
        coll = _extract_collection(raw) or n
        kw_map = _collection_keywords()
        if coll in kw_map:
            state.slots["collection"] = coll
            return True, None
        # Accept anyway — semantic translator may still resolve it.
        if len(n) >= 2:
            state.slots["collection"] = n
            return True, None
        return False, None

    if slot == "time_range":
        tr = _extract_time_range(raw) or raw
        state.slots["time_range"] = tr
        return True, None

    if slot == "analysis_target":
        at = _extract_analysis_target(raw) or raw
        state.slots["analysis_target"] = at
        return True, None

    if slot == "question":
        if len(raw) >= 3:
            state.slots["question"] = raw
            return True, None
        return False, None

    return False, None


# ============================================================================
# ROUTE INFERENCE
# ============================================================================

def infer_route(
    slots: Dict[str, Any],
    has_rendered_map: bool,
    has_screenshot: bool = False,
) -> Optional[str]:
    """Infer the most likely route from currently-filled slots + session state."""
    has_loc  = bool(slots.get("location"))
    has_coll = bool(slots.get("collection"))
    has_q    = bool(slots.get("question") or slots.get("analysis_target"))
    has_img  = bool(has_rendered_map or has_screenshot)

    # Educational question takes priority. "What is NDVI?" extracts
    # collection="ndvi" (and possibly analysis_target="ndvi") opportunistically,
    # but the user is asking ABOUT the dataset, not asking to load it. The
    # strongest signal that the user wants to ACT on imagery is a location.
    # Without one, treat a question-shaped slot as contextual (or
    # vision_analysis when imagery is already on screen).
    is_educational = bool(slots.get("question")) and not has_loc
    if is_educational:
        return "vision_analysis" if has_img else "contextual"

    if has_coll and slots.get("analysis_target"):
        return "hybrid"
    if has_coll:
        return "stac_search"
    if has_q and has_img:
        return "vision_analysis"
    if has_q:
        return "contextual"
    if has_loc:
        return "navigate_to"
    return None


# ============================================================================
# QUESTION + CHIP TEMPLATES
# ============================================================================

def _question_for(route: str, slot: str) -> Tuple[str, List[str]]:
    """Return (question, options) for a (route, slot) pair."""
    if slot == "intent":
        # Educational intent prompt: explain *what each option does* so the
        # user understands the capabilities of the app before picking.
        return (
            "Here's what I can help you with — pick one to get started:\n\n"
            "• **Go to a place** — fly the map to any city, country, or region.\n"
            "• **Load satellite imagery** — pull Sentinel-2, Landsat, HLS, or DEM tiles for an area.\n"
            "• **Analyze what's on the map** — once imagery is loaded, I can describe it, find floods, vegetation, fire, damage, etc.\n"
            "• **Ask a general question** — e.g. \"What is NDVI?\" or \"How does Sentinel-2 work?\"",
            DEFAULT_INTENT_CHIPS,
        )
    if slot == "has_imagery":
        return (
            "I can analyze what's on the map, but no imagery is loaded yet. "
            "Want me to load some so we can analyze it together?",
            DEFAULT_IMAGERY_CHIPS,
        )
    if slot == "location":
        if route == "navigate_to":
            return (
                "Sure — where would you like to go? Pick one or type any city, country, or place.",
                DEFAULT_LOCATION_CHIPS,
            )
        if route == "stac_search":
            return (
                "Got it. Which area should I pull imagery for? Pick one or type any location.",
                DEFAULT_LOCATION_CHIPS,
            )
        if route == "hybrid":
            return (
                "Which area should I analyze? Pick one or type a place name.",
                DEFAULT_LOCATION_CHIPS,
            )
        return ("Which location?", DEFAULT_LOCATION_CHIPS)
    if slot == "collection":
        return (
            "Which dataset should I use?\n\n"
            "• **Sentinel-2** — high-resolution optical imagery (good default)\n"
            "• **Landsat** — long historical archive (1972–present)\n"
            "• **HLS** — harmonized Landsat + Sentinel-2 30m\n"
            "• **Elevation (DEM)** — terrain / topography",
            DEFAULT_COLLECTION_CHIPS,
        )
    if slot == "time_range":
        return ("Which time period?", DEFAULT_TIME_CHIPS)
    if slot == "analysis_target":
        return (
            "What should I look for in the imagery?",
            DEFAULT_ANALYSIS_CHIPS,
        )
    if slot == "question":
        return ("What would you like to know?", [])
    return (
        "I can help you go to a place, load satellite imagery, analyze what's on the map, "
        "or answer general Earth-data questions. What would you like to do?",
        DEFAULT_INTENT_CHIPS,
    )


# ============================================================================
# STATE MACHINE
# ============================================================================

def start_clarification(
    *,
    natural_query: str,
    initial_route: Optional[str],
    initial_slots: Optional[Dict[str, Any]] = None,
    has_rendered_map: bool = False,
    has_screenshot: bool = False,
) -> Dict[str, Any]:
    """
    Begin a clarification chain. Returns (state, router_action) where
    router_action has action_type='clarify' (caller persists state).
    """
    slots = dict(initial_slots or {})

    # Auto-fill has_imagery from session
    if has_rendered_map or has_screenshot:
        slots.setdefault("has_imagery", True)

    # Opportunistically extract from the original query
    extracted = extract_slots(natural_query, initial_route)
    for k, v in extracted.items():
        slots.setdefault(k, v)

    route = initial_route or infer_route(slots, has_rendered_map, has_screenshot)

    state = ClarificationState(
        target_route   = route,
        original_query = natural_query,
        slots          = slots,
    )

    # Pick the next missing slot (or ask intent if route still unknown)
    return _advance(state, has_rendered_map, has_screenshot)


def next_action(
    state: ClarificationState,
    user_msg: str,
    *,
    has_rendered_map: bool = False,
    has_screenshot: bool   = False,
) -> Dict[str, Any]:
    """
    Advance the state machine by one user turn.

    Returns one of:
      {"kind": "ask",     "state": ..., "router_action": {...}}
      {"kind": "execute", "state": ..., "router_action": {...}}
      {"kind": "escape",  "state": None, "router_action": {...}}
      {"kind": "cancel",  "state": None}
    """
    if is_cancel(user_msg):
        logger.info("clarification: user cancelled")
        return {"kind": "cancel", "state": None}

    state.total_attempts += 1

    # 1) Try to fill the slot we asked about
    accepted, route_change = _accept_awaiting_answer(state, user_msg, has_rendered_map or has_screenshot)
    awaiting = state.awaiting_slot

    # 2) Always opportunistically extract more slots from the message
    extracted = extract_slots(user_msg, state.target_route)
    for k, v in extracted.items():
        if not state.slots.get(k):
            state.slots[k] = v

    # 3) If we couldn't fill the awaited slot, count a retry; possibly escape
    if awaiting and not accepted:
        # Maybe the user answered with another slot value entirely -> reroute
        if not state.target_route or awaiting == "intent":
            inferred = infer_route(state.slots, has_rendered_map, has_screenshot)
            if inferred:
                state.target_route = inferred
        else:
            attempts = state.attempts_per_slot.get(awaiting, 0) + 1
            state.attempts_per_slot[awaiting] = attempts
            if attempts >= MAX_ATTEMPTS_PER_SLOT or state.total_attempts >= MAX_TOTAL_TURNS:
                return _escape("I couldn't quite catch that.")
    else:
        # Reset retry counter on success
        if awaiting:
            state.attempts_per_slot[awaiting] = 0

    # 4) Route change from intent / has_imagery chips → recompute slots
    if route_change:
        logger.info(f"clarification: route changed to {route_change}")
        state.awaiting_slot = None

    # 5) Ensure we have a route. If still unknown, ask intent.
    if not state.target_route:
        state.awaiting_slot = "intent"
        return _ask(state, "intent")

    # 6) Re-infer route from accumulated slots (lets a stray collection upgrade
    #    a navigate_to chain into stac_search etc.)
    inferred = infer_route(state.slots, has_rendered_map, has_screenshot)
    if inferred and inferred != state.target_route and state.slots.get("_intent_resolved") is not True:
        logger.info(f"clarification: re-inferring route {state.target_route} -> {inferred}")
        state.target_route = inferred

    return _advance(state, has_rendered_map, has_screenshot)


def _advance(
    state: ClarificationState,
    has_rendered_map: bool,
    has_screenshot: bool,
) -> Dict[str, Any]:
    """Common path: ask next missing slot, or execute if complete."""
    # Total-turn cap
    if state.total_attempts >= MAX_TOTAL_TURNS:
        return _escape("Let's try a fresh start.")

    route = state.target_route

    # Auto-fill has_imagery from session if applicable
    if route in ("vision_analysis",) and (has_rendered_map or has_screenshot):
        state.slots.setdefault("has_imagery", True)

    if not route:
        state.awaiting_slot = "intent"
        return _ask(state, "intent")

    required = ROUTE_SLOTS.get(route, [])
    missing  = [s for s in required if not state.slots.get(s)]

    if missing:
        next_slot = missing[0]
        state.awaiting_slot = next_slot
        return _ask(state, next_slot)

    # All required slots filled → execute
    state.awaiting_slot = None
    return {
        "kind": "execute",
        "state": state,
        "router_action": slots_to_router_action(route, state.slots, state.original_query),
    }


def _ask(state: ClarificationState, slot: str) -> Dict[str, Any]:
    question, options = _question_for(state.target_route or "navigate_to", slot)
    action = {
        "action_type":          "clarify",
        "original_query":       state.original_query,
        "target_route":         state.target_route,
        "missing_slot":         slot,
        "options":              options,
        "user_response":        question,
        "response":             question,
        "needs_stac_search":    False,
        "needs_vision_analysis": False,
        "routing_reason":       "clarification_in_progress",
    }
    return {"kind": "ask", "state": state, "router_action": action}


def _escape(message: str) -> Dict[str, Any]:
    examples = [
        "Show Tokyo",
        "Sentinel-2 of Seattle",
        "What is NDVI?",
    ]
    text = (
        f"{message} Here are some things I can do:\n"
        "• Go to a place — e.g., 'Show Tokyo'\n"
        "• Load satellite imagery — e.g., 'Sentinel-2 of Seattle'\n"
        "• Analyze the map — e.g., 'What's the main river here?'\n"
        "• Ask a general question — e.g., 'What is NDVI?'"
    )
    action = {
        "action_type":          "clarify_escape",
        "original_query":       "",
        "user_response":        text,
        "response":             text,
        "options":              examples,
        "needs_stac_search":    False,
        "needs_vision_analysis": False,
        "routing_reason":       "clarification_escaped",
    }
    return {"kind": "escape", "state": None, "router_action": action}


# ============================================================================
# CONVERSION TO ROUTER ACTION
# ============================================================================

def slots_to_router_action(
    route: str,
    slots: Dict[str, Any],
    original_query: str,
) -> Dict[str, Any]:
    """Convert a fully-filled slot bag into the router_action shape that
    fastapi_app.py's dispatch already understands."""
    if route == "navigate_to":
        return {
            "action_type":          "navigate_to",
            "original_query":       original_query,
            "location":             slots.get("location"),
            "needs_stac_search":    False,
            "needs_vision_analysis": False,
            "routing_reason":       "clarification_completed",
        }

    if route == "stac_search":
        return {
            "action_type":          "stac_search",
            "original_query":       original_query,
            "location":             slots.get("location"),
            "collection_hint":      slots.get("collection"),
            "use_current_location": False,
            "needs_stac_search":    True,
            "needs_vision_analysis": False,
            "time_range":           slots.get("time_range"),
            "routing_reason":       "clarification_completed",
        }

    if route == "vision_analysis":
        return {
            "action_type":          "vision_analysis",
            "original_query":       slots.get("question") or original_query,
            "needs_stac_search":    False,
            "needs_vision_analysis": True,
            "routing_reason":       "clarification_completed",
        }

    if route == "contextual":
        return {
            "action_type":          "contextual",
            "original_query":       slots.get("question") or original_query,
            "question":             slots.get("question") or original_query,
            "needs_stac_search":    False,
            "needs_vision_analysis": False,
            "needs_contextual_response": True,
            "routing_reason":       "clarification_completed",
        }

    if route == "hybrid":
        return {
            "action_type":          "hybrid",
            "original_query":       original_query,
            "search_query":         original_query,
            "analysis_question":    slots.get("analysis_target") or original_query,
            "location":             slots.get("location"),
            "collection_hint":      slots.get("collection"),
            "use_current_location": False,
            "needs_stac_search":    True,
            "needs_vision_analysis": True,
            "time_range":           slots.get("time_range"),
            "routing_reason":       "clarification_completed",
        }

    # Unknown route — fall back to contextual
    return {
        "action_type":          "contextual",
        "original_query":       original_query,
        "question":             original_query,
        "needs_stac_search":    False,
        "needs_vision_analysis": False,
        "needs_contextual_response": True,
        "routing_reason":       "clarification_unknown_route",
    }


# ============================================================================
# VALIDATION HOOK FOR ROUTER OUTPUT
# ============================================================================

def needs_clarification(
    router_action: Dict[str, Any],
    *,
    has_rendered_map: bool = False,
    has_screenshot: bool   = False,
    has_last_bbox: bool    = False,
) -> Optional[str]:
    """
    Inspect a router_action AFTER route_query and decide whether it should
    be redirected through clarification. Returns the missing slot (string)
    if clarification is needed, else None.

    Rules:
    - vision_analysis without rendered map AND without screenshot → has_imagery
    - stac_search without location AND without last_bbox → location
    - hybrid without location AND without last_bbox → location
    - hybrid without collection_hint → collection
    - navigate_to without location → location
    """
    if not router_action:
        return None
    action = router_action.get("action_type")

    if action == "vision_analysis":
        if not (has_rendered_map or has_screenshot):
            return "has_imagery"
        return None

    if action == "stac_search":
        if not router_action.get("location") and not router_action.get("use_current_location") and not has_last_bbox:
            return "location"
        return None

    if action == "hybrid":
        if not router_action.get("location") and not router_action.get("use_current_location") and not has_last_bbox:
            return "location"
        if not router_action.get("collection_hint"):
            return "collection"
        return None

    if action == "navigate_to":
        if not router_action.get("location"):
            return "location"
        return None

    return None
