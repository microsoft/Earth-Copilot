"""Tests for the literal-id passthrough and word-boundary keyword match
added to :mod:`collection_name_mapper` (Phase 0 of the MCP migration).

These guard the two regressions the fix was designed to close:

* ``sentinel2-fire`` (a Pro-only collection id) must route to itself,
  not to ``sentinel-2-l2a``.
* The substring keyword match must no longer fire inside hyphenated
  collection ids -- only on whole-word boundaries.
"""
from __future__ import annotations

import pytest

from collection_name_mapper import CollectionMapper, find_collections


@pytest.fixture(scope="module")
def mapper() -> CollectionMapper:
    return CollectionMapper()


class TestLiteralIdPassthrough:
    def test_pro_only_id_routes_to_itself(self, mapper: CollectionMapper) -> None:
        """A literal Pro-only id (not in the static public inventory) is
        passed through as the top hit so the downstream STAC search can
        actually use it."""
        hits = mapper.find_collections_by_keywords(
            "Show sentinel2-fire imagery over Northern California in May 2026"
        )
        assert hits, "expected at least one routing candidate"
        assert hits[0] == "sentinel2-fire"

    def test_passthrough_suppresses_substring_keyword_hit(
        self, mapper: CollectionMapper
    ) -> None:
        """When the user types ``sentinel2-fire`` we must NOT also emit
        ``sentinel-2-l2a`` -- the keyword path would otherwise add it via
        the ``sentinel`` alias."""
        hits = mapper.find_collections_by_keywords(
            "Show sentinel2-fire over Lake Tahoe"
        )
        assert "sentinel-2-l2a" not in hits, (
            "literal-id passthrough must suppress keyword-derived ids "
            "whose canonical id is a substring of the typed token"
        )

    def test_known_id_returns_canonical_casing(
        self, mapper: CollectionMapper
    ) -> None:
        """If the typed id matches a known public collection (modulo
        case), the canonical id casing is returned."""
        hits = mapper.find_collections_by_keywords("show SENTINEL-2-L2A over Paris")
        assert hits
        assert hits[0] == "sentinel-2-l2a"

    def test_plain_english_not_treated_as_id(self, mapper: CollectionMapper) -> None:
        """Plain English without an id-shaped token must NOT trigger the
        passthrough -- keyword routing still applies."""
        hits = mapper.find_collections_by_keywords(
            "Show me sentinel two imagery over Seattle"
        )
        # The passthrough emits nothing here (no hyphenated id-shaped
        # token); keyword routing may or may not match depending on the
        # inventory. The key invariant is that we did not invent an id.
        for h in hits:
            assert "-" in h or h == "sentinel"  # canonical ids are hyphenated

    def test_module_level_function_uses_same_path(self) -> None:
        """The ``find_collections`` convenience function must honour the
        passthrough too."""
        hits = find_collections("Show sentinel2-fire over California")
        assert hits and hits[0] == "sentinel2-fire"


class TestWordBoundaryMatch:
    def test_sentinel_keyword_does_not_match_inside_hyphenated_id(
        self, mapper: CollectionMapper
    ) -> None:
        """Even without the passthrough, the keyword ``sentinel`` must
        not match inside ``sentinel2-fire`` (it did before -- this was
        the bug)."""
        hits = mapper.find_collections_by_keywords("sentinel2-fire only")
        # ``sentinel-2-l2a`` should NOT appear from the ``sentinel``
        # alias firing inside ``sentinel2-fire``.
        assert "sentinel-2-l2a" not in hits

    def test_sentinel_keyword_still_matches_whole_word(
        self, mapper: CollectionMapper
    ) -> None:
        """Whole-word matches must still work for ordinary queries."""
        hits = mapper.find_collections_by_keywords("show sentinel imagery over Paris")
        assert "sentinel-2-l2a" in hits, (
            "whole-word ``sentinel`` must still route to the public "
            "Sentinel-2 L2A collection"
        )

    def test_landsat_keyword_whole_word_only(self, mapper: CollectionMapper) -> None:
        hits = mapper.find_collections_by_keywords("landsat over Yosemite")
        assert "landsat-c2-l2" in hits
