"""CLI smoke tests: `ciao-sun tiles` for the Bristol example in HANDOFF.md; console script."""

from __future__ import annotations

from importlib.metadata import entry_points

from typer.testing import CliRunner

from ciao_sun.cli import app

runner = CliRunner()


def test_tiles_command_prints_codes_for_bristol():
    result = runner.invoke(app, ["tiles", "--centre", "51.4720,-2.6040", "--radius", "1500"])
    assert result.exit_code == 0, result.output
    codes = [c.strip() for c in result.output.strip().split(",")]
    assert len(codes) > 0
    assert all(len(c) == 6 and c[:2].isalpha() for c in codes)


def test_tiles_command_rejects_bad_centre():
    result = runner.invoke(app, ["tiles", "--centre", "not-a-coord", "--radius", "1500"])
    assert result.exit_code != 0


def test_ciao_sun_console_script_runs_the_cli():
    (script,) = entry_points(group="console_scripts", name="ciao-sun")
    assert script.dist is not None and script.dist.name == "ciao-sun"
    assert script.load() is app

    result = runner.invoke(script.load(), ["--help"])
    assert result.exit_code == 0, result.output
    assert "tiles" in result.output
