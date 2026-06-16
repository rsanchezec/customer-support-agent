"""Application settings loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration driven by environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Foundry
    foundry_project_endpoint: str = Field(
        default="",
        description="Foundry project endpoint URL",
    )
    azure_ai_agent_name: str = Field(
        default="customer-support-agent",
        description="Name of the Foundry agent",
    )
    foundry_model: str = Field(
        default="gpt-5-mini",
        description="Model to use for the agent",
    )

    # Agent version (pin the agent revision in Foundry) — string for Foundry API
    agent_version_str: str = Field(default="", validation_alias="AGENT_VERSION")

    # App environment
    app_env: str = Field(default="dev")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./app.db",
    )

    # Entra ID (consumed by auth in slice 3)
    entra_tenant_id: str = Field(default="")
    entra_client_id: str = Field(default="")
    entra_app_audience: str = Field(default="")
    # Optional: comma-separated allow-lists for relaxed dev validation.
    # When empty, validation is strict (default tenant + audience).
    # When set, any of the listed values is accepted. Useful for local dev
    # with personal MSAs or multi-tenant scenarios.
    entra_allowed_audiences_raw: str = Field(
        default="", validation_alias="ENTRA_ALLOWED_AUDIENCES"
    )
    entra_allowed_issuers_raw: str = Field(
        default="", validation_alias="ENTRA_ALLOWED_ISSUERS"
    )

    # CORS
    cors_allowed_origins: list[str] = Field(default=["http://localhost:5173"])

    @property
    def entra_allowed_audiences(self) -> list[str]:
        """Parse comma-separated string into a list of audiences."""
        return [s.strip() for s in self.entra_allowed_audiences_raw.split(",") if s.strip()]

    @property
    def entra_allowed_issuers(self) -> list[str]:
        """Parse comma-separated string into a list of issuers."""
        return [s.strip() for s in self.entra_allowed_issuers_raw.split(",") if s.strip()]
