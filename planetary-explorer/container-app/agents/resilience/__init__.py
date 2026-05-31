"""Resilience — climate-aware industrial productivity twin.

Different problem shape from Site Intel:

  Site Intel: "Where should we build?"          (one-shot ranking of candidates)
  Resilience: "What's at risk right now / next week?"
              (continuous monitoring of existing facilities)

MAF graph:

    ResilienceQuery
        │
        ▼
    RetrievalExecutor          (load facilities + supply edges from
                                Fabric Lakehouse; fall back to bundled
                                seed data when Fabric not configured)
        │  fan-out
        ├──► WeatherExecutor       (Open-Meteo 7-day forecast per facility,
        │                           heat / wildfire risk scoring)
        ├──► SupplyGraphExecutor   (propagate per-facility risk through
        │                           upstream/downstream edges)
        └──► ContextExecutor       (Azure AI Search over BCP / playbook docs,
                                    filtered to at-risk facilities)
        │  fan-in
        ▼
    AggregatorExecutor         (compose dashboard: facility risk scores,
                                supply-chain blast radius, recommended
                                actions from BCP docs)

Gated by ``RESILIENCE_MVP=1`` in ``fastapi_app.py`` so it can be toggled
per environment.
"""

from .workflow import assess_resilience, assess_resilience_stream, is_available
from .snapshot import (
    SnapshotNotConfigured,
    build_snapshot_url,
    render_assessment_png,
)

__all__ = [
    "assess_resilience",
    "assess_resilience_stream",
    "is_available",
    "SnapshotNotConfigured",
    "build_snapshot_url",
    "render_assessment_png",
]
