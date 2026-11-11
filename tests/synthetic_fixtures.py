"""The committed synthetic build and its golden fixtures: `fixtures/synthetic/`.

    uv run python -m tests.synthetic_fixtures

rebuilds the wider synthetic world of `tests/build_world.py` (three named
streets, the whole street covered) with the real `build`, runs
`fixtures/synthetic/queries.json` through the reference, and replaces
`fixtures/synthetic/f1/`. The JS tests read that directory on every push, with
no Python (`docs/fixtures.md`). Rerun it, and commit the result, whenever the
build, the tile format, the reference, the synthetic world or the query set
changes; `tests/test_fixtures.py` fails while the committed set is stale.

It also writes `fixtures/synthetic/decoded-tiles.json`: what the Python reader
makes of each committed tile, for the JS tile decoder to be checked against
(`docs/fixtures.md`, "What the Python reader decodes").
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from ciao_sun.build import build
from ciao_sun.reference.fixtures import read_query_set
from ciao_sun.tile_codec import codes_to_degrees, read_tile
from tests import build_world

SYNTHETIC = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
QUERIES = SYNTHETIC / "queries.json"
# The build id is cut from this date, so the committed directory keeps its name.
BUILD_DATE = date(2026, 11, 11)
BUILD_ID = "20261111a"
DECODED_TILES = SYNTHETIC / "decoded-tiles.json"


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


def decoded_tiles(build_dir: Path) -> dict[str, Any]:
    """Every tile of a build as the Python reader decodes it, keyed by grid ref.

    Columns are written whole. The Horizon profiles are too big to list, so
    they are two SHA-256 digests over all Candidates in order: of the storage
    codes (one byte each) and of the angles (little-endian float64 degrees).
    """
    tiles: dict[str, Any] = {}
    for path in sorted((build_dir / "tiles").glob("*.bin")):
        tile = read_tile(path)
        c, g = tile.candidates, tile.walk_graph
        degrees = codes_to_degrees(c.profile_codes).astype("<f8")
        tiles[tile.grid_ref] = {
            "names": list(tile.names),
            "candidates": {
                "latE7": c.lat_e7.tolist(),
                "lonE7": c.lon_e7.tolist(),
                "nodeIndex": c.node_index.tolist(),
                "offsetCm": c.offset_cm.tolist(),
                "nameIndex": c.name_index.tolist(),
                "spotNames": [tile.spot_name(k) for k in range(c.lat_e7.shape[0])],
                "profileCodesSha256": hashlib.sha256(c.profile_codes.tobytes()).hexdigest(),
                "profileDegreesSha256": hashlib.sha256(degrees.tobytes()).hexdigest(),
                # Candidate 0's whole profile, so a wrong digest can be chased by eye.
                "firstProfileCodes": c.profile_codes[0].tolist() if len(c.lat_e7) else [],
            },
            "walkGraph": {
                "nodeId": g.node_id.tolist(),
                "nodeLatE7": g.node_lat_e7.tolist(),
                "nodeLonE7": g.node_lon_e7.tolist(),
                "edgeFrom": g.edge_from.tolist(),
                "edgeTo": g.edge_to.tolist(),
                "edgeLengthCm": g.edge_length_cm.tolist(),
            },
        }
    return tiles


def write_decoded_tiles(build_dir: Path, path: Path = DECODED_TILES) -> Path:
    text = json.dumps(decoded_tiles(build_dir), ensure_ascii=False, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    built = regenerate()
    print(f"Wrote {built}")
    print(f"Wrote {write_decoded_tiles(built)}")
