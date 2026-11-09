"""RESEARCH, throwaway. Mosaic OS Terrain 50 (ASCII grid, 10 km tiles) into one GB grid.

Input:  the extracted tiles from terr50_gagg_gb.zip (see fetch steps in far-horizon.md),
        i.e. a directory of `<TILE>.asc` files (200x200 cells, 50 m, EPSG:27700).
Output: a memmapped int16 .npy in decimetres, origin (0, 1300000) top-left, 50 m cells,
        14000 cols x 26000 rows, nodata -32768. ~728 MB on disk.

    uv run python -I build_terr50.py <asc_dir> <out.npy>
"""

import sys
from pathlib import Path

import numpy as np

ASC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
CELL, X0, Y1, NC, NR = 50, 0, 1_300_000, 14000, 26000

arr = np.lib.format.open_memmap(OUT, mode="w+", dtype=np.int16, shape=(NR, NC))
arr[:] = -32768
n = 0
for p in sorted(ASC.glob("*.asc")):
    hdr = {}
    with p.open() as f:
        for _ in range(6):
            pos = f.tell()
            line = f.readline().split()
            if line and line[0].lower() in {"ncols", "nrows", "xllcorner", "yllcorner", "cellsize",
                                            "nodata_value"}:
                hdr[line[0].lower()] = float(line[1])
            else:
                f.seek(pos)
                break
        z = np.loadtxt(f, dtype=np.float32)
    assert hdr["cellsize"] == CELL and z.shape == (int(hdr["nrows"]), int(hdr["ncols"])), p
    c0 = int((hdr["xllcorner"] - X0) // CELL)
    r0 = int((Y1 - (hdr["yllcorner"] + hdr["nrows"] * CELL)) // CELL)
    dm = np.round(z * 10).astype(np.int16)
    if "nodata_value" in hdr:
        dm[z == hdr["nodata_value"]] = -32768
    arr[r0 : r0 + z.shape[0], c0 : c0 + z.shape[1]] = dm
    n += 1
arr.flush()
print("tiles", n, "max m", arr.max() / 10)
