"""The committed synthetic build and its golden fixtures: `fixtures/synthetic/`.

    uv run python -m tests.synthetic_fixtures

rebuilds the wider synthetic world of `tests/build_world.py` (three named
streets, the whole street covered) with the real `build`, runs
`fixtures/synthetic/queries.json` through the reference, and replaces
`fixtures/synthetic/f1/`. The JS tests read that directory on every push, with
no Python (`docs/fixtures.md`). Rerun it, and commit the result, whenever the
build, the tile format, the reference, the synthetic world or the query set
changes; `tests/test_fixtures.py` fails while the committed set is stale.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

from ciao_sun.build import build
from ciao_sun.reference.fixtures import read_query_set
from tests import build_world

SYNTHETIC = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
QUERIES = SYNTHETIC / "queries.json"
# The build id is cut from this date, so the committed directory keeps its name.
BUILD_DATE = date(2026, 11, 11)
BUILD_ID = "20261111a"


def regenerate(out: Path = SYNTHETIC) -> Path:
    """Build the synthetic world with its fixtures into `<out>/f1/`, replacing what is there.

    Returns the build directory, `<out>/f1/20261111a`.
    """
    with tempfile.TemporaryDirectory() as scratch:
        box = build_world.WIDE_COVERAGE_BOX
        lock = build_world.fetch_inputs(Path(scratch), streets=build_world.THREE_STREETS, box=box)
        built = build(
            build_world.coverage(box),
            lock.root,
            Path(scratch) / "builds",
            today=BUILD_DATE,
            queries=read_query_set(QUERIES),
        )
        format_dir = out / built.parent.name
        if format_dir.exists():
            shutil.rmtree(format_dir)
        shutil.copytree(built, format_dir / built.name)
    return format_dir / built.name


if __name__ == "__main__":
    print(f"Wrote {regenerate()}")
