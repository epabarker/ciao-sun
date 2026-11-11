"""Smoke tests for the TOML-backed pydantic settings model."""

from __future__ import annotations

import pytest

from ciao_sun.config import CiaoSunConfig


def test_defaults_with_required_fields():
    cfg = CiaoSunConfig.load(None, home_lat=51.472, home_lon=-2.604)
    assert cfg.radius == 1500.0
    assert cfg.eye_height == 1.6
    assert cfg.pass_fraction == 0.5


def test_load_from_toml_file(tmp_path):
    toml_path = tmp_path / "ciao-sun.toml"
    toml_path.write_text(
        """
home_lat = 51.4720
home_lon = -2.6040
radius = 800.0
pass_fraction = 0.75
"""
    )
    cfg = CiaoSunConfig.load(toml_path)
    assert cfg.home_lat == 51.4720
    assert cfg.radius == 800.0
    assert cfg.pass_fraction == 0.75


def test_cli_overrides_beat_toml_file(tmp_path):
    toml_path = tmp_path / "ciao-sun.toml"
    toml_path.write_text("home_lat = 51.4720\nhome_lon = -2.6040\nradius = 800.0\n")
    cfg = CiaoSunConfig.load(toml_path, radius=2000.0)
    assert cfg.radius == 2000.0


@pytest.mark.parametrize(
    "field,value",
    [("home_lat", 200.0), ("home_lon", -400.0), ("radius", -1.0), ("pass_fraction", 1.5)],
)
def test_out_of_range_values_are_rejected(field, value):
    kwargs = {"home_lat": 51.472, "home_lon": -2.604, field: value}
    with pytest.raises(ValueError):
        CiaoSunConfig.load(None, **kwargs)
