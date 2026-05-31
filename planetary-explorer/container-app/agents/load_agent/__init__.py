"""LoadAgent — owns LOAD turns in the v2 pipeline.

Public surface:
    >>> from agents.load_agent import get_load_agent, LoadAgentInput
    >>> agent = get_load_agent()
    >>> plan = await agent.plan(LoadAgentInput(
    ...     query="Show coastal land cover changes in California",
    ...     location_name="California",
    ... ))
    >>> plan.intent, plan.action
    ('temporal_change', 'clarify')
"""

from .load_agent_models import (
    CollectionCandidate,
    DatetimeSlot,
    LoadAgentInput,
    LoadPlan,
    LocationSlot,
)
from .load_agent import LoadAgent, get_load_agent

__all__ = [
    "CollectionCandidate",
    "DatetimeSlot",
    "LoadAgent",
    "LoadAgentInput",
    "LoadPlan",
    "LocationSlot",
    "get_load_agent",
]
