# Tile format f1

This document specifies the Ciao Sun tile file, format `f1`. It is written so that a builder or a reader can be implemented from it in any language. Domain terms (Candidate, Horizon profile) follow `GLOSSARY.md`.

A tile holds everything date-independent about one 1 km square for one window: its Candidates, each Candidate's Horizon profile over the window's sector of azimuths, and the part of the walk graph that touches the square.

## Files and names

- Two files per 1 km British National Grid square: a **morning** tile and an **evening** tile. They hold the same Candidates and walk graph, and each holds only the Horizon profile samples its window can need (its **sector**, see [Horizon profiles](#horizon-profiles)). A query reads its own window's tiles only, which halves what it fetches (#62).
- The file is named by the square's OS grid reference, two letters and four digits, plus `.bin`: `ST5873.bin` is the square whose south-west corner is 358000 E, 173000 N.
- In a published build the files live at `<dataBase>/f1/<build>/tiles/morning/<grid ref>.bin` and `<dataBase>/f1/<build>/tiles/evening/<grid ref>.bin`.
- A square with no Candidates and no walk edges has no files.

## When the format number changes

The format number changes **only when an existing app could not read the bytes, or could not read the manifest schema**. Then it becomes `f2`, published under a new `f2/` prefix.

These are *not* format changes. Each is a new build in the same format:

- a fix or change to the horizon, Candidate or naming algorithm
- new survey data, or a new OpenStreetMap extract
- different coverage

A reader must check the format number before trusting any other byte, and must refuse a number it does not know.

## Layers

From the outside in:

1. **gzip.** The whole file is one gzip member (RFC 1952). A browser reads it with `DecompressionStream("gzip")`. The file is served as opaque bytes, with no `Content-Encoding`, so a cache holds exactly the published bytes.
2. **Payload.** The decompressed bytes, laid out as below.
3. **Azimuth delta.** Inside the payload, each Horizon profile is stored as differences between neighbouring azimuths (see [Horizon profiles](#horizon-profiles)).
4. **Storage code.** Each Horizon profile value is a one-byte code for an angle (see [The storage code](#the-storage-code)).

A builder should write the gzip header with a zero timestamp and no file name, so that the same tile always gives the same bytes.

## Payload conventions

- All integers are **little-endian**. Signed integers are two's complement.
- Types: `u8`, `u16`, `u32`, `u64` are unsigned integers of 8, 16, 32 and 64 bits; `i32` is a signed 32-bit integer.
- There is no padding and no alignment. Every section follows the previous one directly.
- Fields are stored **by column**: all latitudes, then all longitudes, and so on. Element `k` of every Candidate column belongs to Candidate `k`.
- Counts in the header fix the size of every section except the last (the Spot names), which is read to its end. The payload must end exactly there.

Units:

| Quantity | Stored as |
| --- | --- |
| Position | WGS84 latitude and longitude, each as `i32` degrees × 10⁷ (north and east positive). One unit is about 1 cm. |
| Distance | `u32` centimetres |
| Horizon profile angle | `u8` storage code |

A build of Great Britain converts its National Grid positions to latitude and longitude with OSTN15. The reader needs no map projection.

## Payload layout

`C`, `N`, `E` and `S` are the counts from the header.

### Header: 32 bytes

| Offset | Type | Field | Value |
| --- | --- | --- | --- |
| 0 | 4 bytes | Magic | ASCII `CSUN` (`43 53 55 4E`) |
| 4 | `u16` | Format number | `1` |
| 6 | 6 bytes | Grid reference | ASCII, e.g. `ST5873`; equals the file name without `.bin` |
| 12 | `u32` | `C` | number of Candidates |
| 16 | `u32` | `N` | number of walk-graph nodes |
| 20 | `u32` | `E` | number of walk-graph edges |
| 24 | `u32` | `S` | number of Spot names |
| 28 | `u16` | `F` | the sector's first Horizon profile sample, 0 – 1439 |
| 30 | `u16` | `P` | the number of samples in the sector, 1 – 1440 |

### Sections, in file order

| # | Section | Type | Elements | Bytes | Meaning |
| --- | --- | --- | --- | --- | --- |
| 1 | Candidate latitude | `i32` | `C` | 4`C` | degrees × 10⁷ |
| 2 | Candidate longitude | `i32` | `C` | 4`C` | degrees × 10⁷ |
| 3 | Candidate walk node | `u32` | `C` | 4`C` | index (0-based) of the node the Candidate is snapped to, into the node sections |
| 4 | Candidate offset | `u32` | `C` | 4`C` | centimetres between the Candidate and that node; added to any walk that ends at the Candidate |
| 5 | Candidate Spot name | `u32` | `C` | 4`C` | index (0-based) into the Spot names |
| 6 | Node id | `u64` | `N` | 8`N` | see [Walk graph](#walk-graph) |
| 7 | Node latitude | `i32` | `N` | 4`N` | degrees × 10⁷ |
| 8 | Node longitude | `i32` | `N` | 4`N` | degrees × 10⁷ |
| 9 | Edge from | `u32` | `E` | 4`E` | index (0-based) of one end node |
| 10 | Edge to | `u32` | `E` | 4`E` | index (0-based) of the other end node |
| 11 | Edge length | `u32` | `E` | 4`E` | centimetres along the path |
| 12 | Horizon profiles | `u8` | `PC` | `PC` | delta-coded storage codes, one row of `P` per Candidate, in Candidate order |
| 13 | Spot names | — | `S` entries | varies | each entry: `u16` byte length, then that many bytes of UTF-8; so a name is at most 65,535 bytes |

So the Horizon profiles start at byte `32 + 20C + 16N + 12E`, and the Spot names at `32 + (20 + P)C + 16N + 12E`.

### Candidates

A Candidate is identified within a build by its tile's grid reference and its 0-based index in that tile. The index is its position in every Candidate column and its row in the Horizon profiles.

The node a Candidate is snapped to is always in the same tile's node sections, even when the node lies outside the square.

Several Candidates usually share one Spot name. The name is stored once and each of them points at it.

### Walk graph

- Edges are undirected. Each edge appears once in a tile.
- Both end nodes of every edge in a tile are in that tile's node sections. A node can therefore lie outside the tile's square.
- An edge that crosses a tile boundary is written into both tiles.
- **Node ids are stable across the tiles of one build**: the same id in two tiles is the same node. A reader that loads several tiles joins their graphs on node id, and treats two edges with the same pair of end ids as one edge.
- Node ids are below 2⁵³, so a reader may hold them in an IEEE 754 double. Ids are unique within a tile. They mean nothing across builds.

## The storage code

A Horizon profile angle is the elevation, in degrees, of the highest obstruction in one direction. It is stored as one of 228 codes:

| Code `c` | Angle in degrees | Step |
| --- | --- | --- |
| 0 – 120 | `−2.0 + 0.1 × c` (−2.0° to 10.0°) | 0.1° |
| 121 – 227 | `10.0 + 0.5 × (c − 120)` (10.5° to 63.5°) | 0.5° |
| 228 – 255 | not used; a reader must refuse them | |

Some values: code 0 is −2.0°, code 20 is 0.0°, code 120 is 10.0°, code 121 is 10.5°, code 227 is 63.5°.

To encode an angle, a builder:

1. clamps it to the range: anything below −2.0° becomes code 0, anything above 63.5° becomes code 227;
2. otherwise takes the code whose angle is nearest. Between 10.0° and 10.5° that is code 120 below 10.25° and code 121 from there up.

The stored angle is therefore within 0.05° of the true one up to 10°, and within 0.25° above that.

## Horizon profiles

The full circle is 1,440 samples:

- Sample `i` (0 to 1439) is the Horizon profile at **true azimuth `i × 0.25°`**, measured clockwise from true north. Sample 0 is north, 360 is east, 720 is south, 1080 is west.
- Azimuths are true, not grid. The builder applies grid convergence; the reader never does.
- For an azimuth between two samples, a reader interpolates linearly between the two decoded angles. Sample 1439 is followed by sample 0.

A tile holds only its **sector**: the `P` samples `F, F + 1, …, F + P − 1`, counted mod 1440, so a sector may run on past north. A reader must refuse to use a sample outside the sector, rather than read it as an angle. The builder chooses each window's sector so that its scorer never needs one: the build's `manifest.json` records them (`sectors`), and a morning tile holds the morning sector, an evening tile the evening sector. A tile may hold the full circle (`F = 0`, `P = 1440`).

The sector's samples are stored as **differences along azimuth**. If `c[0] … c[P−1]` are one Candidate's storage codes for samples `F … F + P − 1`, the `P` stored bytes `d` are:

```
d[0] = c[0]
d[j] = (c[j] − c[j−1]) mod 256      for j = 1 … P − 1
```

To decode, a reader takes a running sum:

```
c[0] = d[0]
c[j] = (c[j−1] + d[j]) mod 256      for j = 1 … P − 1
```

Each Candidate's row starts afresh: nothing carries from one row to the next, and the sector's first sample is not differenced against its last. A falling profile gives bytes near 255: a step from code 25 down to code 20 is stored as 251.

## What a reader must refuse

A reader rejects the file, rather than returning a partial tile, when:

- it is not valid gzip, or the magic is wrong
- the format number is not one it knows (reported separately, as "this version can't read this data")
- the sector's first sample `F` is 1440 or more, or its count `P` is 0 or more than 1440
- the payload ends before its last field, or has bytes after it
- the grid reference is not two letters `A`–`Z` (never `I`) and four digits, or differs from the file name
- a Candidate's walk node index is `N` or more, or its Spot name index is `S` or more
- an edge's node index is `N` or more
- a node id is 2⁵³ or more, or two nodes in the tile share an id
- any decoded storage code is above 227
- a Spot name is not valid UTF-8

A builder must not write any of these.

## Worked example

Tile `ST5873` with one Candidate, two nodes, one edge and one Spot name, holding the full circle. The Candidate's Horizon profile is 0.0° (code 20) all round, except a ridge due east: samples 360, 361 and 362 hold codes 25, 130 and 25, which are 0.5°, 15.0° and 0.5°.

The payload is 1,550 bytes:

| Offset | Bytes (hex) | Field |
| --- | --- | --- |
| 0 | `43 53 55 4E` | magic `CSUN` |
| 4 | `01 00` | format 1 |
| 6 | `53 54 35 38 37 33` | grid reference `ST5873` |
| 12 | `01 00 00 00` | `C` = 1 |
| 16 | `02 00 00 00` | `N` = 2 |
| 20 | `01 00 00 00` | `E` = 1 |
| 24 | `01 00 00 00` | `S` = 1 |
| 28 | `00 00` | sector first sample `F` = 0 |
| 30 | `A0 05` | sector samples `P` = 1440 |
| 32 | `C8 45 AB 1E` | Candidate latitude 514541000 = 51.4541000° |
| 36 | `10 34 72 FE` | Candidate longitude −26070000 = −2.6070000° |
| 40 | `01 00 00 00` | Candidate walk node: index 1 |
| 44 | `DA 02 00 00` | Candidate offset 730 cm |
| 48 | `00 00 00 00` | Candidate Spot name: index 0 |
| 52 | `65 00 00 00 00 00 00 00` | node 0 id 101 |
| 60 | `07 00 00 00 00 01 00 00` | node 1 id 1099511627783 (2⁴⁰ + 7) |
| 68 | `E0 41 AB 1E` | node 0 latitude 514540000 |
| 72 | `68 55 AB 1E` | node 1 latitude 514545000 |
| 76 | `28 30 72 FE` | node 0 longitude −26071000 |
| 80 | `B0 43 72 FE` | node 1 longitude −26066000 |
| 84 | `00 00 00 00` | edge 0 from: index 0 |
| 88 | `01 00 00 00` | edge 0 to: index 1 |
| 92 | `8F 19 00 00` | edge 0 length 6543 cm |
| 96 | `14`, then `00` × 359 | profile deltas for samples 0 – 359: code 20, then no change |
| 456 | `05 69 97 FB` | samples 360 – 363: +5, +105, −105 (151), −5 (251) |
| 460 | `00` × 1076 | samples 364 – 1439: no change |
| 1536 | `0C 00` | Spot name 0 is 12 bytes long |
| 1538 | `42 72 61 6E 64 6F 6E 20 48 69 6C 6C` | `Brandon Hill` |

The published file is these 1,550 bytes, gzip-compressed.

## Not in the tile

The build's `manifest.json` carries the format number, the build id, the two windows' sectors, the list of tiles, attribution and licence. Anything that depends on the date (the sun's track, Sun minutes, ranking) is computed by the reader and is not stored.
