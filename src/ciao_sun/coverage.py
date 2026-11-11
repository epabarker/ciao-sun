"""The coverage polygon: the area a build produces Candidates for.

It is given as GeoJSON in WGS84 longitude/latitude (a Polygon or MultiPolygon,
bare or wrapped in a Feature or a one-feature FeatureCollection) and handed to
the rest of the pipeline as outer rings in British National Grid metres.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import Transformer

_WGS84_TO_BNG = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)

Point = tuple[float, float]


class CoverageError(ValueError):
    """The coverage is not a usable WGS84 polygon."""


@dataclass(frozen=True)
class Coverage:
    """A coverage polygon. `geometry` is its GeoJSON Polygon or MultiPolygon."""

    geometry: dict[str, Any]

    @classmethod
    def from_file(cls, path: Path) -> Coverage:
        try:
            document = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise CoverageError(f"Cannot read coverage GeoJSON {path}: {exc}") from exc
        try:
            return cls.from_geojson(document)
        except CoverageError as exc:
            raise CoverageError(f"{path}: {exc}") from exc

    @classmethod
    def from_geojson(cls, document: object) -> Coverage:
        geometry = _unwrap(document)
        coverage = cls(geometry=geometry)
        for ring in coverage._outer_rings_wgs84():
            if len(ring) < 4:
                raise CoverageError("A coverage ring needs at least four positions.")
            for lon, lat in ring:
                if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                    raise CoverageError(
                        f"Coverage position ({lon}, {lat}) is not WGS84 longitude, latitude."
                    )
        return coverage

    def rings_bng(self) -> list[list[Point]]:
        """Outer rings in British National Grid metres, one per polygon part.

        Holes are dropped: a hole never reduces what has to be fetched or built
        around the coverage.
        """
        return [
            [_WGS84_TO_BNG.transform(lon, lat) for lon, lat in ring]
            for ring in self._outer_rings_wgs84()
        ]

    def polygon_bng(self) -> Any:
        """The coverage as a shapely geometry in British National Grid metres, holes kept."""
        coordinates = self.geometry["coordinates"]
        polygons = [coordinates] if self.geometry["type"] == "Polygon" else coordinates

        def project(lonlat: np.ndarray) -> np.ndarray:
            x, y = _WGS84_TO_BNG.transform(lonlat[:, 0], lonlat[:, 1])
            return np.column_stack([x, y])

        try:
            parts = [
                shapely.Polygon(
                    [position[:2] for position in polygon[0]],
                    [[position[:2] for position in hole] for hole in polygon[1:]],
                )
                for polygon in polygons
            ]
        except (TypeError, ValueError, IndexError) as exc:
            raise CoverageError(f"Malformed coverage coordinates: {exc}") from exc
        return shapely.transform(shapely.union_all(parts), project)

    def _outer_rings_wgs84(self) -> list[list[Point]]:
        coordinates = self.geometry["coordinates"]
        polygons = [coordinates] if self.geometry["type"] == "Polygon" else coordinates
        try:
            return [
                [(float(position[0]), float(position[1])) for position in polygon[0]]
                for polygon in polygons
            ]
        except (TypeError, ValueError, IndexError, KeyError) as exc:
            raise CoverageError(f"Malformed coverage coordinates: {exc}") from exc


def _unwrap(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise CoverageError("Coverage GeoJSON must be an object.")
    kind = document.get("type")
    if kind == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list) or len(features) != 1:
            raise CoverageError("A coverage FeatureCollection must hold exactly one feature.")
        return _unwrap(features[0])
    if kind == "Feature":
        return _unwrap(document.get("geometry"))
    if kind in ("Polygon", "MultiPolygon") and document.get("coordinates"):
        return {"type": kind, "coordinates": document["coordinates"]}
    raise CoverageError(f"Coverage must be a Polygon or MultiPolygon, not {kind!r}.")
