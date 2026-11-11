"""CLI tests: the Stage 1 command surface, `ciao-sun fetch`, console script."""

from __future__ import annotations

import re
from importlib.metadata import entry_points

import typer
from typer.testing import CliRunner

from ciao_sun.cli import app

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Help text without styling. Rich colours its output on GitHub Actions,
    which splits option names such as `--coverage` with escape codes."""
    return " ".join(_ANSI.sub("", output).split())


def test_fetch_help_explains_every_input_and_the_coverage_argument():
    result = runner.invoke(app, ["fetch", "--help"], terminal_width=200)
    assert result.exit_code == 0, result.output
    text = _plain(result.output)
    for phrase in [
        "Environment Agency", "DSM", "DTM", "first-return", "Terrain 50", "Geofabrik",
        "--coverage", "GeoJSON", "WGS84", "3 km",
        "fetch.lock.json", "SHA-256", "--osm-date",
    ]:
        assert phrase in text, f"`fetch --help` does not mention {phrase!r}"
    for phrase in ["--protomaps-build", "YYYYMMDD", "Protomaps", "byte range", "zooms 10 to 15"]:
        assert phrase in text, f"`fetch --help` does not mention {phrase!r}"


def test_fetch_refuses_a_coverage_that_is_not_a_polygon_without_a_traceback(tmp_path):
    coverage = tmp_path / "point.geojson"
    coverage.write_text('{"type": "Point", "coordinates": [-2.6, 51.47]}')
    result = runner.invoke(
        app,
        ["fetch", "--coverage", str(coverage), "--osm-date", "261110",
         "--out", str(tmp_path / "inputs")],
    )
    assert result.exit_code == 1
    assert "Polygon" in result.output
    assert not (tmp_path / "inputs").exists()


def test_tiles_command_is_gone():
    result = runner.invoke(app, ["tiles", "--help"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_ciao_sun_console_script_runs_the_cli():
    (script,) = entry_points(group="console_scripts", name="ciao-sun")
    assert script.dist is not None and script.dist.name == "ciao-sun"
    assert script.load() is app

    result = runner.invoke(script.load(), ["--help"])
    assert result.exit_code == 0, result.output
    assert "fetch" in result.output


def test_cli_exposes_fetch_and_profile_only():
    group = typer.main.get_command(app)
    assert {"fetch", "profile-only"} <= set(group.commands)


def test_find_and_compare_are_no_longer_commands():
    for removed in ("find", "compare"):
        result = runner.invoke(app, [removed, "--help"])
        assert result.exit_code != 0, f"`{removed}` should be gone"
        assert "No such command" in result.output
