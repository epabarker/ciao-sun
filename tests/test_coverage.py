"""The coverage polygon: read from GeoJSON, handed on in British National Grid."""

from __future__ import annotations

import json

import pytest

from ciao_sun.coverage import Coverage, CoverageError

# A small box around Clifton Down, Bristol. Its BNG position is known from the
# EA tiles downloaded for it by hand: it sits in ST57se (ST5570) and ST57ne (ST5575).
_RING = [[-2.62, 51.46], [-2.58, 51.46], [-2.58, 51.48], [-2.62, 51.48], [-2.62, 51.46]]
_POLYGON = {"type": "Polygon", "coordinates": [_RING]}


def test_polygon_ring_is_projected_to_british_national_grid():
    (ring,) = Coverage.from_geojson(_POLYGON).rings_bng()
    assert len(ring) == 5
    for easting, northing in ring:
        assert 355_000 < easting < 360_000
        assert 170_000 < northing < 180_000


def test_feature_and_feature_collection_wrappers_are_accepted():
    feature = {"type": "Feature", "properties": {}, "geometry": _POLYGON}
    collection = {"type": "FeatureCollection", "features": [feature]}
    assert Coverage.from_geojson(feature) == Coverage.from_geojson(_POLYGON)
    assert Coverage.from_geojson(collection) == Coverage.from_geojson(_POLYGON)


def test_multipolygon_gives_one_outer_ring_per_part():
    shifted = [[lon + 0.2, lat] for lon, lat in _RING]
    multi = {"type": "MultiPolygon", "coordinates": [[_RING], [shifted]]}
    assert len(Coverage.from_geojson(multi).rings_bng()) == 2


def test_coverage_is_read_from_a_geojson_file(tmp_path):
    path = tmp_path / "bristol.geojson"
    path.write_text(json.dumps(_POLYGON))
    assert Coverage.from_file(path) == Coverage.from_geojson(_POLYGON)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "Point", "coordinates": [-2.6, 51.47]},
        {"type": "FeatureCollection", "features": []},
        {"type": "Polygon", "coordinates": [[[-2.62, 51.46], [-2.58, 51.46]]]},
        # Easting/northing pasted where longitude/latitude belong.
        {"type": "Polygon", "coordinates": [[[357000, 172000], [358000, 172000],
                                             [358000, 173000], [357000, 172000]]]},
        ["not", "an", "object"],
    ],
)
def test_anything_but_a_wgs84_polygon_is_refused(bad):
    with pytest.raises(CoverageError):
        Coverage.from_geojson(bad)


def test_unreadable_file_is_refused_with_its_path(tmp_path):
    path = tmp_path / "broken.geojson"
    path.write_text("{not json")
    with pytest.raises(CoverageError, match="broken.geojson"):
        Coverage.from_file(path)
