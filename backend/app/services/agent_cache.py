"""Module-level async cache for resolved Foundry agents.

Caches the result of agent resolution so we hit the Foundry API at most once
per process, per (agent_name, version) pair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.ai.projects.aio import AIProjectClient
    from azure.ai.projects.models import AgentVersionDetails


# In-process cache: key -> already-resolved AgentVersionDetails
_cache: dict[tuple[str, str], AgentVersionDetails] = {}


async def get_or_resolve(
    client: AIProjectClient,
    agent_name: str,
    agent_version: str,
) -> AgentVersionDetails:
    """Resolve the agent once and cache the result.

    Returns the cached AgentVersionDetails if already resolved for this
    (agent_name, agent_version) pair; otherwise calls
    ``client.agents.get_version()`` and caches the result.
    """
    key = (agent_name, agent_version)
    if key in _cache:
        return _cache[key]

    resolved: AgentVersionDetails = await client.agents.get_version(
        agent_name=agent_name,
        agent_version=agent_version,
    )
    _cache[key] = resolved
    return resolved


def reset() -> None:
    """Clear the agent cache.

    Exists exclusively for use in unit tests that need to verify cache
    miss behaviour after a prior resolve call.
    """
    _cache.clear()
