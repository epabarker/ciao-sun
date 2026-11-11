"""CLI tests: the Stage 1 command surface, `ciao-sun tiles` for Bristol, console script."""

from __future__ import annotations

from importlib.metadata import entry_points

import typer
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


def test_cli_exposes_only_profile_only_and_the_tiles_placeholder():
    group = typer.main.get_command(app)
    assert sorted(group.commands) == ["profile-only", "tiles"]


def test_find_and_compare_are_no_longer_commands():
    for removed in ("find", "compare"):
        result = runner.invoke(app, [removed, "--help"])
        assert result.exit_code != 0, f"`{removed}` should be gone"
        assert "No such command" in result.output
