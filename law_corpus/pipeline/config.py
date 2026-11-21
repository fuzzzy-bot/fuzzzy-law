"""
Settings for the law data pipeline: polite scraping and where data is kept.

All settings are loaded from environment variables (via .env files) and
validated through Pydantic Settings.  Import ``settings`` to access them
anywhere in the codebase:

    from pipeline.config import settings
"""

from __future__ import annotations

import enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Enums ────────────────────────────────────────────────────

class LogLevel(str, enum.Enum):
    """Supported log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ── Settings ─────────────────────────────────────────────────

class Settings(BaseSettings):
    """Pipeline settings, from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Scraping ─────────────────────────────────────────────
    scrape_delay_seconds: float = Field(
        default=2.0,
        ge=1.0,
        description="Minimum seconds between requests to any single host",
    )
    scrape_max_concurrent: int = Field(
        default=3,
        ge=1,
        description="Maximum concurrent scrape connections",
    )
    scrape_user_agent: str = Field(
        default="FuzzzyLawCorpusBot/1.1 (Fuzzy Core LLC, Fuzzzy Law legal-information app; +mailto:support@fuzzzycore.com)",
        description="User-Agent header sent with every request",
    )

    # ── Pipeline ─────────────────────────────────────────────
    log_level: LogLevel = Field(default=LogLevel.INFO)
    data_dir: Path = Field(
        default=Path("./data"),
        description="Root directory for all pipeline data",
    )
    checkpoint_dir: Path = Field(
        default=Path("./data/georgian_laws/checkpoints"),
        description="Directory for pipeline checkpoint files",
    )

    # ── Derived paths ────────────────────────────────────────

    @property
    def georgian_laws_dir(self) -> Path:
        """Root for the georgian_laws module data."""
        return self.data_dir / "georgian_laws"

    @property
    def raw_html_dir(self) -> Path:
        return self.georgian_laws_dir / "raw" / "html"

    @property
    def raw_pdf_dir(self) -> Path:
        return self.georgian_laws_dir / "raw" / "pdf"

    @property
    def raw_metadata_dir(self) -> Path:
        return self.georgian_laws_dir / "raw" / "metadata"

    @property
    def parsed_dir(self) -> Path:
        return self.georgian_laws_dir / "parsed"

    @property
    def index_dir(self) -> Path:
        return self.georgian_laws_dir / "index"

    def module_data_dir(self, module_id: str) -> Path:
        """Return the data directory for a given corpus module."""
        return self.data_dir / module_id

    def ensure_dirs(self) -> None:
        """Create every data directory that the pipeline needs."""
        for d in (
            self.raw_html_dir,
            self.raw_pdf_dir,
            self.raw_metadata_dir,
            self.parsed_dir,
            self.index_dir,
            self.checkpoint_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @field_validator("data_dir", "checkpoint_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v: str | Path) -> Path:
        return Path(v).resolve()


# Singleton instance — import this everywhere.
settings = Settings()
