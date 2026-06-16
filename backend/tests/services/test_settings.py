"""Unit tests for application settings.

Verifies that Settings loads all required fields from environment variables,
including the Foundry-related settings added in this slice.
"""

from __future__ import annotations

import pytest

from app.settings import Settings


class TestFoundrySettings:
    """Tests for Foundry-related settings fields."""

    def test_foundry_endpoint_loaded_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FOUNDRY_PROJECT_ENDPOINT is read from the environment."""
        monkeypatch.setenv(
            "FOUNDRY_PROJECT_ENDPOINT", "https://foundry.example.com/api/projects/my-project"
        )
        settings = Settings()
        assert (
            settings.foundry_project_endpoint
            == "https://foundry.example.com/api/projects/my-project"
        )

    def test_agent_name_default(self) -> None:
        """AZURE_AI_AGENT_NAME defaults to 'customer-support-agent'."""
        settings = Settings()
        assert settings.azure_ai_agent_name == "customer-support-agent"

    def test_agent_name_overridden_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AZURE_AI_AGENT_NAME can be overridden via the environment."""
        monkeypatch.setenv("AZURE_AI_AGENT_NAME", "my-custom-agent")
        settings = Settings()
        assert settings.azure_ai_agent_name == "my-custom-agent"

    def test_foundry_model_default(self) -> None:
        """FOUNDRY_MODEL defaults to 'gpt-5-mini'."""
        settings = Settings()
        assert settings.foundry_model == "gpt-5-mini"

    def test_agent_version_str_default(self) -> None:
        """AGENT_VERSION defaults to empty string (auto-detect latest)."""
        settings = Settings()
        assert settings.agent_version_str == ""

    def test_agent_version_str_overridden_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AGENT_VERSION can be overridden via the environment."""
        monkeypatch.setenv("AGENT_VERSION", "42")
        settings = Settings()
        assert settings.agent_version_str == "42"
