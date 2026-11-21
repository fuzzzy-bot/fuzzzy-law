"""
Connector settings, read from environment variables (or a .env file).

Usage:
    from app.config.settings import settings

Every setting has a safe default; the compose file sets the ones a server needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All connector settings, validated at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    connector_access_mode: Literal["open", "api_key"] = Field(
        default="open",
        description="open = anyone, rate limited per address; api_key = Bearer key "
                    "from connector_api_keys_file with per-key daily quotas.",
    )
    connector_public_base_url: str = Field(
        default="http://localhost:8000",
        description="Public origin the connector is reached at; written into "
                    "the OpenAPI servers list and the coverage page.",
    )
    connector_rate_limit_per_minute: int = Field(
        default=30,
        description="Requests per minute per caller (per address in open mode, "
                    "per key in api_key mode).",
    )
    connector_shared_ip_ranges: str = Field(
        default="",
        description="Comma-separated networks (CIDR) that AI providers call "
                    "from on behalf of many people at once. Calls from them get "
                    "connector_shared_rate_limit_per_minute instead of the "
                    "per-person limit.",
    )
    connector_shared_rate_limit_per_minute: int = Field(
        default=600,
        description="Requests per minute for one address inside connector_shared_ip_ranges.",
    )
    connector_max_body_bytes: int = Field(
        default=65_536,
        description="Largest request body the connector accepts; larger is refused with 413.",
    )
    connector_data_dir: Path | None = Field(
        default=None,
        description="Folder holding article_store.db, court_store.db, "
                    "law_history.db and status.json. Unset = ./data.",
    )
    connector_stale_after_days: int = Field(
        default=3,
        description="Days without a successful check against matsne.gov.ge "
                    "after which every connector answer carries a warning.",
    )
    connector_daily_quota: int = Field(
        default=1000,
        description="Requests per day per key in api_key mode, unless the key's "
                    "entry sets its own daily_quota.",
    )
    connector_api_keys_file: Path = Field(
        default=Path("connector_api_keys.json"),
        description='{"<sha256 of key>": {"user": "...", "daily_quota": 1000}}. '
                    "Only hashes are stored; the key itself is never on disk.",
    )
    connector_allowed_hosts: str = Field(
        default="",
        description="Comma-separated Host values the MCP endpoint accepts "
                    "(DNS-rebinding protection). Empty = any host.",
    )
    connector_cors_origins: str = Field(
        default="",
        description="Comma-separated web origins allowed to read the coverage "
                    "endpoint from a browser (the project website). Empty = none.",
    )

    @property
    def connector_allowed_host_list(self) -> list[str]:
        """Parse comma-separated connector hosts into a list."""
        return [h.strip() for h in self.connector_allowed_hosts.split(",") if h.strip()]

    @property
    def connector_shared_networks(self) -> list[str]:
        """Parse the comma-separated provider networks into a list."""
        return [n.strip() for n in self.connector_shared_ip_ranges.split(",") if n.strip()]

    @property
    def connector_cors_origin_list(self) -> list[str]:
        """Parse the comma-separated website origins into a list."""
        return [o.strip() for o in self.connector_cors_origins.split(",") if o.strip()]

    @property
    def data_dir(self) -> Path:
        """Where the data files are read from."""
        return self.connector_data_dir or Path("data")


# Singleton: import this everywhere.
settings = Settings()
