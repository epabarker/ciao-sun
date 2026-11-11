"""CRS round-trip correctness: HANDOFF.md #6, test group 4."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyproj import Transformer

from ciao_sun.tiles import _WGS84_TO_BNG

SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "ciao_sun"

ENGLISH_COORDS = [
    (51.4720, -2.6040),  # Bristol
    (51.5074, -0.1278),  # London
    (53.4808, -2.2426),  # Manchester
    (50.7192, -1.8808),  # Bournemouth
    (54.9783, -1.6178),  # Newcastle
    (50.0654, -5.7139),  # Land's End
]


@pytest.mark.parametrize("lat,lon", ENGLISH_COORDS)
def test_wgs84_to_bng_round_trip(lat, lon):
    bng_to_wgs84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    x, y = _WGS84_TO_BNG.transform(lon, lat)
    lon2, lat2 = bng_to_wgs84.transform(x, y)
    assert lat2 == pytest.approx(lat, abs=1e-7)
    assert lon2 == pytest.approx(lon, abs=1e-7)


def test_every_transformer_in_the_package_uses_always_xy():
    """The single most likely bug here is lon/lat vs x/y ordering."""
    files = list(SRC_DIR.glob("*.py"))
    assert files, "expected to find ciao_sun source files"
    for path in files:
        text = path.read_text()
        n_transformers = text.count("Transformer.from_crs(")
        if n_transformers == 0:
            continue
        n_always_xy = text.count("always_xy=True")
        assert n_always_xy >= n_transformers, (
            f"{path.name} builds {n_transformers} Transformer(s) but only "
            f"{n_always_xy} use always_xy=True"
        )
