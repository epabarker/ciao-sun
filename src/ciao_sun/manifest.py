"""`manifest.json`: what a build is, what it was made from, and how to credit it.

One per build, beside `tiles/` and `basemap/`. The client renders all attribution from it and
hardcodes none. Its schema is part of format f1: a change an existing app could
not read is a format bump.

    {
      "format": 1,
      "build": "20261110a",                 UTC date plus a letter
      "licence": {"name", "spdx", "url"},   of the bundle: ODbL 1.0
      "attribution": [                      one per source, in display order
        {"source", "text", "licence", "licenceUrl"}
      ],
      "lidarSurveyYears": [2019, 2021],     years the EA LIDAR in the build was flown
      "inputs": [                           every line of the fetch lockfile
        {"kind", "source", "tile", "version", "url", "sha256", "bytes", "absent",
         "timestamp"}                       timestamp: OSM replication time, OSM only
      ],                                    kind "basemap": version is the Protomaps build date
      "basemap": {
        "protomapsBuild": "20260811",       the pinned Protomaps daily build
        "tilesetVersion": "4.15.1",         the Protomaps basemap version; styles follow its major
        "osmTimestamp",                     how fresh the OpenStreetMap data in the basemap is
        "minZoom", "maxZoom",               the zooms that have tiles
        "bounds": [west, south, east, north],   WGS84; no tile lies wholly outside it
        "tileCount", "bytes"
      },
      "coverage": {GeoJSON Polygon or MultiPolygon, WGS84},
      "horizon": {"nearReachM", "farReachM"},
      "sectors": {"morning": {"firstSample", "samples"}, "evening": {...}},
                                          the Horizon profile samples each window's tiles hold
      "tiles": {"ST5873": {"candidates", "morning": {"bytes", "sha256"},
                           "evening": {"bytes", "sha256"}}},   the tile index
      "buildChecks": {
        "profile": {"candidatesPerTile", "toleranceDeg", "storageHalfStepDeg",
                    "fractionWithin", "candidatesChecked"},
        "waterGuard": {"candidatesAllowed", "candidatesFound", "riverCandidatesToReview"}
      }
    }

A tile in the index is at `tiles/<window>/<grid ref>.bin` for each window
(`tile_file`); a square not in the index has no tiles. `buildChecks` are the
tolerances the build passed (`build_checks.py`).
A basemap tile is at `basemap/{z}/{x}/{y}.mvt`, an uncompressed Mapbox Vector
Tile, for every tile the `bounds` touch at `minZoom` to `maxZoom` (`basemap.py`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ciao_sun.basemap import ATTRIBUTION as PROTOMAPS_ATTRIBUTION
from ciao_sun.basemap import Basemap
from ciao_sun.coverage import Coverage
from ciao_sun.fetch import EA_PRODUCTS, LockedInput
from ciao_sun.tile_codec import FORMAT, Sector

MANIFEST_NAME = "manifest.json"

LICENCE = {
    "name": "Open Database License (ODbL) v1.0",
    "spdx": "ODbL-1.0",
    "url": "https://opendatacommons.org/licenses/odbl/1-0/",
}
_OGL = {
    "licence": "Open Government Licence v3.0",
    "licenceUrl": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
}
_ODBL = {"licence": LICENCE["name"], "licenceUrl": LICENCE["url"]}


def _attribution(inputs: Sequence[LockedInput]) -> list[dict[str, str]]:
    ea_year = max(entry.version for entry in inputs if entry.kind in EA_PRODUCTS)
    (terrain,) = [entry for entry in inputs if entry.kind == "terrain50"]
    # OS's copyright year is the release's: Terrain 50 versions are "YYYY-MM".
    os_year = (
        terrain.version[:4] if re.match(r"(19|20)\d\d", terrain.version) else terrain.fetched_at[:4]
    )
    return [
        {
            "source": "Environment Agency",
            "text": f"© Environment Agency copyright and/or database right {ea_year}. "
            "All rights reserved.",
            **_OGL,
        },
        {
            "source": "Ordnance Survey",
            "text": f"Contains OS data © Crown copyright and database right {os_year}",
            **_OGL,
        },
        {"source": "OpenStreetMap", "text": "© OpenStreetMap contributors", **_ODBL},
        # The basemap is OpenStreetMap data, built into tiles by Protomaps.
        {"source": "Protomaps", "text": PROTOMAPS_ATTRIBUTION, **_ODBL},
        # The sky slot's forecast, credited as the sky slot itself words it
        # (`SKY_CREDIT` in `app/src/ui/sky-slot.ts`): the Met Office's data is
        # CC BY-SA 4.0, Open-Meteo's service CC BY 4.0.
        {
            "source": "Met Office",
            "text": "Forecast data from the Met Office via Open-Meteo, "
            "cloud cover categorised by Ciao Sun",
            "licence": "CC BY-SA 4.0",
            "licenceUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        },
        {
            "source": "Open-Meteo",
            "text": "Weather data by Open-Meteo.com",
            "licence": "CC BY 4.0",
            "licenceUrl": "https://creativecommons.org/licenses/by/4.0/",
        },
    ]


def manifest_document(
    *,
    build_id: str,
    inputs: Sequence[LockedInput],
    osm_timestamp: str | None,
    lidar_survey_years: Sequence[int],
    coverage: Coverage,
    horizon: Mapping[str, float],
    tiles: Mapping[str, Mapping[str, Any]],
    build_checks: Mapping[str, Any],
    sectors: Mapping[str, Sector],
    basemap: Basemap | None = None,
) -> dict[str, Any]:
    """The manifest for one build. `tiles` is the tile index, keyed by grid ref."""
    listed = []
    for entry in inputs:
        line: dict[str, Any] = {
            "kind": entry.kind,
            "source": entry.source,
            "tile": entry.tile,
            "version": entry.version,
            "url": entry.url,
            "sha256": entry.sha256,
            "bytes": entry.bytes,
            "absent": entry.absent,
        }
        if entry.kind == "osm":
            line["timestamp"] = osm_timestamp
        listed.append(line)
    document: dict[str, Any] = {
        "format": FORMAT,
        "build": build_id,
        "licence": dict(LICENCE),
        "attribution": _attribution(inputs),
        "lidarSurveyYears": sorted(lidar_survey_years),
        "inputs": listed,
        "coverage": coverage.geometry,
        "horizon": dict(horizon),
        "sectors": {
            window: {"firstSample": sector.first, "samples": sector.samples}
            for window, sector in sectors.items()
        },
        "tiles": {grid_ref: dict(tiles[grid_ref]) for grid_ref in sorted(tiles)},
        "buildChecks": dict(build_checks),
    }
    if basemap is not None:
        (protomaps,) = [entry for entry in inputs if entry.kind == "basemap"]
        document["basemap"] = {
            "protomapsBuild": protomaps.version,
            "tilesetVersion": basemap.tileset_version,
            "osmTimestamp": basemap.osm_timestamp,
            "minZoom": basemap.min_zoom,
            "maxZoom": basemap.max_zoom,
            "bounds": list(basemap.bounds),
            "tileCount": basemap.tile_count,
            "bytes": basemap.bytes,
        }
    return document


def write_manifest(build_dir: Path, document: Mapping[str, Any]) -> Path:
    path = build_dir / MANIFEST_NAME
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def tile_file(build_dir: Path, window: str, grid_ref: str) -> Path:
    """Where a square's tile for a window lives in a build directory."""
    return build_dir / "tiles" / window / f"{grid_ref}.bin"


def manifest_sectors(manifest: Mapping[str, Any]) -> dict[str, Sector]:
    """The sector of Horizon profile samples each window's tiles hold."""
    return {
        window: Sector(int(entry["firstSample"]), int(entry["samples"]))
        for window, entry in manifest["sectors"].items()
    }


def read_manifest(build_dir: Path) -> dict[str, Any]:
    document = json.loads((build_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise ValueError(f"{build_dir / MANIFEST_NAME} is not a format {FORMAT} manifest.")
    return document
