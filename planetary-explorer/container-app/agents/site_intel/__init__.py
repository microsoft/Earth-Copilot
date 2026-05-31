"""Site Intel — MAF-based multi-agent siting workflow.

This is the v2 of ``agents.site_audit`` decomposed into a Microsoft Agent
Framework (MAF) :class:`WorkflowBuilder` graph:

    SiteSpec
       │
       ▼
    PlannerExecutor            (LLM — picks active dimensions + weights;
                                no-op when SITE_PLANNER=0)
       │
       ▼
    RetrievalExecutor          (loads 4 Fabric Delta tables concurrently)
       │  fan-out
       ├──► GridExecutor       (Fabric power_infrastructure)
       ├──► WaterExecutor      (Fabric water_assets)
       ├──► CompetitionExecutor(Fabric existing_data_centers)
       ├──► LandExecutor       (Fabric candidate_sites — parcel match)
       ├──► HazardExecutor     (Planetary Computer — dynamic + anchor collections)
       ├──► PrecedentExecutor  (Azure AI Search — permitting-docs)
       └──► MetaExecutor       (sidecar — carries planner weights via fan-in)
       │  fan-in
       ▼
    AggregatorExecutor         (weighted sum + serializes the same JSON
                                contract as ``audit_site``)
       │
       ▼
    EvidenceExecutor           (extracts stable source IDs; SITE_EVIDENCE=1)
       │
       ▼
    ReviewExecutor             (LLM critique — confidence/concerns/next_steps;
                                yields final dossier; SITE_REVIEW=1)

Selected by ``SITE_AUDIT_V2=1`` in ``fastapi_app.py``. When the flag is not
set or MAF is unavailable, the legacy monolithic ``audit_site`` is used.

The deterministic scoring functions (``_score_power``, ``_score_water``, …)
live in ``agents.site_audit`` and are imported unchanged so v1 and v2
produce identical numbers when the planner picks the same dimensions.
"""

from .workflow import audit_site_v2, audit_site_v2_stream, is_available

__all__ = ["audit_site_v2", "audit_site_v2_stream", "is_available"]
