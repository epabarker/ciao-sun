"""CLI smoke test: `sunspot tiles` for the Bristol example in HANDOFF.md."""

from __future__ import annotations

from typer.testing import CliRunner

from sunspot.cli import app

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
