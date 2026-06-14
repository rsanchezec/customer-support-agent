"""Unit tests for the Foundry client wrapper.

Verifies ``FoundryClient`` behaviour using fully-mocked Azure SDK objects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_cache import reset as reset_agent_cache
from app.services.foundry import FoundryClient


class TestGetExistingAgent:
    """Tests for FoundryClient.get_existing_agent()."""

    @pytest.mark.asyncio
    async def test_returns_agent_metadata(self, fake_project_client: MagicMock) -> None:
        """get_existing_agent() returns the AgentVersionDetails it receives from the SDK."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        result = await client.get_existing_agent()

        assert result.name == "customer-support-agent"
        assert result.version == "1"

    @pytest.mark.asyncio
    async def test_uses_provided_name_over_default(self, fake_project_client: MagicMock) -> None:
        """Passing name/version to get_existing_agent() overrides the instance defaults."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="default-agent",
            agent_version="1",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        await client.get_existing_agent(
            name="override-agent",
            version="3",
        )

        call_kwargs = fake_project_client.agents.get_version.call_args
        assert call_kwargs.kwargs["agent_name"] == "override-agent"
        assert call_kwargs.kwargs["agent_version"] == "3"


class TestInvoke:
    """Tests for FoundryClient.invoke()."""

    @pytest.mark.asyncio
    async def test_returns_text(
        self, fake_project_client: MagicMock, fake_foundry_agent: MagicMock
    ) -> None:
        """invoke() returns the .text attribute of the AgentResponse."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        with patch("app.services.foundry.FoundryAgent", return_value=fake_foundry_agent):
            result = await client.invoke("Hello")

        assert result == "Test response."

    @pytest.mark.asyncio
    async def test_passes_query_to_agent(
        self, fake_project_client: MagicMock, fake_foundry_agent: MagicMock
    ) -> None:
        """The user's query is forwarded to agent.run()."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        with patch("app.services.foundry.FoundryAgent", return_value=fake_foundry_agent):
            await client.invoke("What is 2+2?")

        fake_foundry_agent.run.assert_called_once_with("What is 2+2?")

    @pytest.mark.asyncio
    async def test_uses_instance_defaults_when_no_override(
        self, fake_project_client: MagicMock, fake_foundry_agent: MagicMock
    ) -> None:
        """When no override is given, invoke uses the client-level agent_name / version."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="my-agent",
            agent_version="2",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        with patch("app.services.foundry.FoundryAgent", return_value=fake_foundry_agent):
            result = await client.invoke("Hello")

        assert result == "Test response."


class TestContextManager:
    """Tests for async-context-manager behaviour."""

    @pytest.mark.asyncio
    async def test_context_manager_closes_resources(self, fake_credential: AsyncMock) -> None:
        """Using 'async with' closes both the client and the credential."""
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
            credential=fake_credential,
        )

        async with client:
            pass

        fake_credential.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_aclose_idempotent(self, fake_credential: AsyncMock) -> None:
        """Calling aclose() twice does not raise."""
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
            credential=fake_credential,
        )

        await client.aclose()
        await client.aclose()  # must not raise


class TestAgentCache:
    """Tests for the module-level agent cache."""

    @pytest.mark.asyncio
    async def test_cache_resolves_once(self, fake_project_client: MagicMock) -> None:
        """Calling get_existing_agent twice returns the cached value (single SDK call)."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        result1 = await client.get_existing_agent()
        result2 = await client.get_existing_agent()

        assert result1 is result2  # same object from cache
        assert fake_project_client.agents.get_version.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_reset_allows_re_resolve(self, fake_project_client: MagicMock) -> None:
        """After reset(), a new call to get_existing_agent hits the SDK again."""
        reset_agent_cache()
        client = FoundryClient(
            endpoint="https://foundry.example.com/api/projects/test",
            agent_name="test-agent",
            agent_version="1",
        )
        client._client = fake_project_client  # type: ignore[assignment]

        await client.get_existing_agent()
        assert fake_project_client.agents.get_version.call_count == 1

        reset_agent_cache()

        await client.get_existing_agent()
        assert fake_project_client.agents.get_version.call_count == 2
