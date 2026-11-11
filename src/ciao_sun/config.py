"""Pydantic settings model for Ciao Sun, optionally backed by a TOML config file."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CiaoSunConfig(BaseSettings):
    """Parameters for a `ciao-sun profile-only` run."""

    model_config = SettingsConfigDict(env_prefix="CIAO_SUN_", extra="forbid")

    home_lat: float = Field(..., description="Home latitude, WGS84 degrees")
    home_lon: float = Field(..., description="Home longitude, WGS84 degrees")
    date: str = "2026-12-21"
    max_ray: float = 3000.0
    tz: str = "Europe/London"
    dtm_dir: Path = Path("data/dtm")
    dsm_dir: Path = Path("data/dsm")
    cache_dir: Path = Path("data/cache")

    @model_validator(mode="after")
    def _check_ranges(self) -> CiaoSunConfig:
        if not (-90.0 <= self.home_lat <= 90.0):
            raise ValueError(f"home_lat out of range: {self.home_lat}")
        if not (-180.0 <= self.home_lon <= 180.0):
            raise ValueError(f"home_lon out of range: {self.home_lon}")
        if self.max_ray <= 0:
            raise ValueError("max_ray must be positive")
        return self

    @classmethod
    def load(cls, config_path: Path | None = None, **overrides: object) -> CiaoSunConfig:
        """Build a config from an optional TOML file, with keyword overrides on top."""
        data: dict[str, object] = {}
        if config_path is not None:
            with open(config_path, "rb") as f:
                data = dict(tomllib.load(f))
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
        return cls.model_validate(data)
