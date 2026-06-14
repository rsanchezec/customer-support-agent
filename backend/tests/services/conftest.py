"""Fixtures for Foundry service unit tests.

All tests use fakes / mocks so they run without any live Foundry endpoint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fake AgentVersionDetails
# ---------------------------------------------------------------------------


def make_fake_agent_version_details(
    name: str = "customer-support-agent",
    version: str = "1",
) -> MagicMock:
    """Return a fake ``AgentVersionDetails`` with the given name / version."""
    details = MagicMock()
    details.name = name
    details.version = version
    return details


# ---------------------------------------------------------------------------
# Fake AgentResponse (returned by agent.run())
# ---------------------------------------------------------------------------


def make_fake_agent_response(text: str = "Hello from the agent.") -> MagicMock:
    """Return a fake ``AgentResponse`` with the given text."""
    response = MagicMock()
    response.text = text
    return response


# ---------------------------------------------------------------------------
# Fake AIProjectClient
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_project_client() -> MagicMock:
    """Return a fake ``AIProjectClient`` with async ``agents.get_version``."""
    client = MagicMock()
    client.agents = MagicMock()
    client.agents.get_version = AsyncMock(return_value=make_fake_agent_version_details())
    return client


# ---------------------------------------------------------------------------
# Fake FoundryAgent
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_foundry_agent() -> MagicMock:
    """Return a fake ``FoundryAgent`` whose ``run()`` is async and returns text."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=make_fake_agent_response("Test response."))
    return agent


# ---------------------------------------------------------------------------
# Fake credential (no-op close)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_credential() -> AsyncMock:
    """Return a fake async credential with a no-op ``close`` method."""
    cred = AsyncMock()
    cred.close = AsyncMock(return_value=None)
    return cred
