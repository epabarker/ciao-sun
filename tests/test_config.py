"""Smoke tests for the TOML-backed pydantic settings model."""

from __future__ import annotations

import pytest

from ciao_sun.config import CiaoSunConfig


def test_defaults_with_required_fields():
    cfg = CiaoSunConfig.load(None, home_lat=51.472, home_lon=-2.604)
    assert cfg.max_ray == 3000.0
    assert cfg.step_minutes == 5.0
    assert cfg.window_minutes == 60.0


def test_load_from_toml_file(tmp_path):
    toml_path = tmp_path / "ciao-sun.toml"
    toml_path.write_text(
        """
home_lat = 51.4720
home_lon = -2.6040
max_ray = 800.0
step_minutes = 2.0
"""
    )
    cfg = CiaoSunConfig.load(toml_path)
    assert cfg.home_lat == 51.4720
    assert cfg.max_ray == 800.0
    assert cfg.step_minutes == 2.0


def test_cli_overrides_beat_toml_file(tmp_path):
    toml_path = tmp_path / "ciao-sun.toml"
    toml_path.write_text("home_lat = 51.4720\nhome_lon = -2.6040\nmax_ray = 800.0\n")
    cfg = CiaoSunConfig.load(toml_path, max_ray=2000.0)
    assert cfg.max_ray == 2000.0


@pytest.mark.parametrize(
    "field,value",
    [("home_lat", 200.0), ("home_lon", -400.0), ("max_ray", -1.0)],
)
def test_out_of_range_values_are_rejected(field, value):
    kwargs = {"home_lat": 51.472, "home_lon": -2.604, field: value}
    with pytest.raises(ValueError):
        CiaoSunConfig.load(None, **kwargs)


@pytest.mark.parametrize("key", ["radius", "pass_fraction", "min_clear_minutes", "walk"])
def test_settings_of_the_removed_find_and_compare_commands_are_rejected(key):
    with pytest.raises(ValueError):
        CiaoSunConfig.load(None, home_lat=51.472, home_lon=-2.604, **{key: 1})
