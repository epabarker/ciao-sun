"""Pydantic settings model for sunspot, optionally backed by a TOML config file."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SunspotConfig(BaseSettings):
    """All parameters for a `sunspot find` / `sunspot compare` run."""

    model_config = SettingsConfigDict(env_prefix="SUNSPOT_", extra="forbid")

    home_lat: float = Field(..., description="Home latitude, WGS84 degrees")
    home_lon: float = Field(..., description="Home longitude, WGS84 degrees")
    date: str = "2026-12-21"
    radius: float = 1500.0
    spacing: float = 10.0
    eye_height: float = 1.6
    max_ray: float = 3000.0
    pass_fraction: float = 0.5
    min_clear_minutes: float = 5.0
    curvature: bool = True
    tz: str = "Europe/London"
    step_minutes: float = 5.0
    window_minutes: float = 60.0
    chunk_size: int = 4000
    dtm_dir: Path = Path("data/dtm")
    dsm_dir: Path = Path("data/dsm")
    cache_dir: Path = Path("data/cache")
    walk: bool = False
    output_dir: Path = Path(".")

    @model_validator(mode="after")
    def _check_ranges(self) -> SunspotConfig:
        if not (-90.0 <= self.home_lat <= 90.0):
            raise ValueError(f"home_lat out of range: {self.home_lat}")
        if not (-180.0 <= self.home_lon <= 180.0):
            raise ValueError(f"home_lon out of range: {self.home_lon}")
        if self.radius <= 0 or self.spacing <= 0 or self.max_ray <= 0:
            raise ValueError("radius, spacing and max_ray must all be positive")
        if not (0.0 < self.pass_fraction <= 1.0):
            raise ValueError(f"pass_fraction must be in (0, 1]: {self.pass_fraction}")
        if self.min_clear_minutes < 0:
            raise ValueError(f"min_clear_minutes must be >= 0: {self.min_clear_minutes}")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        return self

    @classmethod
    def load(cls, config_path: Path | None = None, **overrides: object) -> SunspotConfig:
        """Build a config from an optional TOML file, with keyword overrides on top."""
        data: dict[str, object] = {}
        if config_path is not None:
            with open(config_path, "rb") as f:
                data = dict(tomllib.load(f))
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
        return cls.model_validate(data)
