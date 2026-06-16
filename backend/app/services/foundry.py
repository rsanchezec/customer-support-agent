"""Async Foundry client wrapper.

Wraps ``AIProjectClient`` and ``AzureCliCredential`` from the Azure AI Projects
SDK, providing a reusable :class:`FoundryClient` that owns the connection
lifecycle and exposes a thin, sync-style invoke interface for a single-shot
agent turn.

The client is designed to be instantiated once per process (e.g. in the
FastAPI lifespan) and shared across all requests.
"""

from __future__ import annotations

import inspect
import warnings
from typing import TYPE_CHECKING

from agent_framework.foundry import FoundryAgent
from azure.ai.projects.aio import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.services.agent_cache import get_or_resolve

if TYPE_CHECKING:
    from azure.ai.projects.models import AgentResponse, AgentVersionDetails


# Suppress experimental-feature warnings from agent_framework.
warnings.filterwarnings("ignore", message=r"\[(SKILLS|HARNESS)\]")


class FoundryClient:
    """Async wrapper around the Azure AI Projects SDK.

    Instantiate once at application startup and close it when the app shuts
    down. All methods are async and the class supports the async context-manager
    protocol.

    Parameters
    ----------
    endpoint
        Foundry project endpoint URL (e.g. ``FOUNDRY_PROJECT_ENDPOINT``).
    agent_name
        Logical name of the deployed agent in Foundry.
        agent_version
        String version identifier of the agent (e.g. ``"1"``). Empty means
        resolve the latest published version.
    credential
        Optional credential. Defaults to :class:`DefaultAzureCredential`,
        matching the working Streamlit example.
    """

    def __init__(
        self,
        endpoint: str,
        agent_name: str,
        agent_version: str,
        credential: object | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.agent_name = agent_name
        self.agent_version = agent_version
        self._credential = credential or DefaultAzureCredential()
        self._client: AIProjectClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> AIProjectClient:
        """Lazily initialise the underlying AIProjectClient."""
        if self._client is None:
            self._client = AIProjectClient(
                endpoint=self.endpoint,
                credential=self._credential,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the underlying client and credential.

        Idempotent: safe to call multiple times.
        """
        if self._client is not None:
            await self._client.close()
            self._client = None
        close = getattr(self._credential, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result

    async def __aenter__(self) -> FoundryClient:
        """Enter the async context manager."""
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit the async context manager and release resources."""
        await self.aclose()

    # ------------------------------------------------------------------
    # Agent resolution
    # ------------------------------------------------------------------

    async def get_existing_agent(
        self,
        name: str | None = None,
        version: str | None = None,
    ) -> AgentVersionDetails:
        """Resolve an agent's metadata by name and version.

        Uses the module-level agent cache so the underlying
        ``client.agents.get_version()`` is called at most once per process,
        per (name, version) pair.

        Parameters
        ----------
        name
            Agent logical name. Defaults to the instance-level ``agent_name``.
        version
            Agent version string. Defaults to the instance-level
            ``agent_version``.

        Returns
        -------
        AgentVersionDetails
            Agent metadata returned by Foundry (includes ``.name`` and
            ``.version``).
        """
        resolved_name = name or self.agent_name
        resolved_version = version if version is not None else self.agent_version
        if resolved_version:
            client = await self._ensure_client()
            return await get_or_resolve(client, resolved_name, resolved_version)
        return await self._resolve_latest_agent(resolved_name)

    async def _resolve_latest_agent(self, agent_name: str) -> AgentVersionDetails:
        """Resolve the latest published version for an agent."""
        client = await self._ensure_client()
        versions: list[AgentVersionDetails] = []
        async for version in client.agents.list_versions(agent_name=agent_name):
            versions.append(version)

        if not versions:
            raise RuntimeError(
                f"No versions found for agent '{agent_name}'. Publish a version first."
            )

        def version_key(agent_version: AgentVersionDetails) -> tuple[int, int | str]:
            try:
                return (0, int(agent_version.version))
            except (TypeError, ValueError):
                return (1, str(agent_version.version))

        return max(versions, key=version_key)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    async def invoke(
        self,
        query: str,
        *,
        agent_name: str | None = None,
        agent_version: str | None = None,
    ) -> str:
        """Invoke the Foundry agent with a single-turn query.

        Constructs a fresh :class:`FoundryAgent` on each call (the SDK object
        is lightweight and stateless) and issues a single non-streaming
        ``agent.run(query)`` call, returning the aggregated text response.

        Parameters
        ----------
        query
            The user's message / question.
        agent_name
            Override the agent name for this call. Defaults to the instance
            level name.
        agent_version
            Override the agent version for this call. Defaults to the
            instance-level version.

        Returns
        -------
        str
            The plain-text response from the agent.
        """
        client = await self._ensure_client()
        resolved = await self.get_existing_agent(name=agent_name, version=agent_version)
        resolved_name = resolved.name
        resolved_version = resolved.version

        agent = FoundryAgent(
            project_client=client,
            agent_name=resolved_name,
            agent_version=resolved_version,
        )

        result: AgentResponse = await agent.run(query)
        return result.text
