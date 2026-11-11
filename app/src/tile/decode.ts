// The tile decoder: the bytes of a published f1 tile file -> a Tile.
//
// docs/tile-format-f1.md is the specification, and `ciao_sun.tile_codec` the
// Python reader this one must agree with. Terms follow GLOSSARY.md.

import { GRID_REF } from "../ids";

/** The only format number this reader knows. */
export const FORMAT = 1;
/** Horizon profile samples per Candidate: sample i is at true azimuth i * 0.25 degrees. */
export const PROFILE_SAMPLES = 1440;
/** Degrees of true azimuth between two Horizon profile samples. */
export const PROFILE_STEP_DEG = 360 / PROFILE_SAMPLES;
/** The storage code has 228 codes, 0 to 227. */
export const CODE_COUNT = 228;

const FINE_TOP_CODE = 120;
const HEADER_BYTES = 28;
const NODE_ID_LIMIT = 2n ** 53n;

/** The bytes are not a valid f1 tile. */
export class TileFormatError extends Error {
  override name = "TileFormatError";
}

/** The tile is in a format this reader does not know: "this version can't read this data". */
export class UnsupportedFormatError extends TileFormatError {
  override name = "UnsupportedFormatError";
  readonly format: number;

  constructor(format: number) {
    super(`tile is format f${format}; this reader only understands f${FORMAT}`);
    this.format = format;
  }
}

/** A tile's Candidates: element k of every column, and row k of the profiles, is Candidate k. */
export interface Candidates {
  /** WGS84 latitude, degrees * 1e7. */
  readonly latE7: Int32Array;
  /** WGS84 longitude, degrees * 1e7. */
  readonly lonE7: Int32Array;
  /** Index, into the tile's walk-graph nodes, of the node the Candidate is snapped to. */
  readonly nodeIndex: Uint32Array;
  /** Centimetres between the Candidate and that node. */
  readonly offsetCm: Uint32Array;
  /** Index into the tile's Spot names. */
  readonly nameIndex: Uint32Array;
  /** Storage codes, PROFILE_SAMPLES per Candidate in Candidate order, azimuth delta undone. */
  readonly profileCodes: Uint8Array;
}

/** A tile's part of the walk graph. Edges are undirected and name nodes by index. */
export interface WalkGraph {
  /** Stable across the tiles of one build; below 2^53, so exact as a number. */
  readonly nodeId: Float64Array;
  readonly nodeLatE7: Int32Array;
  readonly nodeLonE7: Int32Array;
  readonly edgeFrom: Uint32Array;
  readonly edgeTo: Uint32Array;
  /** Centimetres along the path. */
  readonly edgeLengthCm: Uint32Array;
}

/** One 1 km tile, named by its OS grid reference (e.g. "ST5873"). */
export interface Tile {
  readonly gridRef: string;
  readonly names: readonly string[];
  readonly candidates: Candidates;
  readonly walkGraph: WalkGraph;
}

/** The Horizon profile angle, in degrees, of each storage code, indexed by code. */
export const DEGREES_BY_CODE: Readonly<Float64Array> = Float64Array.from({ length: CODE_COUNT }, (_, code) =>
  // The reference's own expressions, so both give the same double for every code.
  code <= FINE_TOP_CODE ? -2.0 + 0.1 * code : 10.0 + 0.5 * (code - FINE_TOP_CODE),
);

/** A storage code -> the Horizon profile angle it stands for, in degrees. */
export function codeToDegrees(code: number): number {
  const degrees = DEGREES_BY_CODE[code];
  if (degrees === undefined) {
    throw new TileFormatError(
      `storage code ${code} is not one of the ${CODE_COUNT} codes (0-${CODE_COUNT - 1})`,
    );
  }
  return degrees;
}

/** The Spot name of Candidate `candidate` of a tile. */
export function spotName(tile: Tile, candidate: number): string {
  const name = tile.names[tile.candidates.nameIndex[candidate] ?? -1];
  if (name === undefined) {
    throw new RangeError(`tile ${tile.gridRef} has no Candidate ${candidate}`);
  }
  return name;
}

/** The storage codes of one Candidate's Horizon profile: a view, not a copy. */
export function horizonProfileCodes(tile: Tile, candidate: number): Uint8Array {
  if (!(candidate >= 0 && candidate < tile.candidates.latE7.length)) {
    throw new RangeError(`tile ${tile.gridRef} has no Candidate ${candidate}`);
  }
  const start = candidate * PROFILE_SAMPLES;
  return tile.candidates.profileCodes.subarray(start, start + PROFILE_SAMPLES);
}

/** One Candidate's Horizon profile in degrees, by true azimuth sample. */
export function horizonProfileDegrees(tile: Tile, candidate: number): Float64Array {
  return Float64Array.from(horizonProfileCodes(tile, candidate), codeToDegrees);
}

async function gunzip(bytes: Uint8Array): Promise<Uint8Array> {
  try {
    // The platform's own gzip: tiles are served as opaque bytes, with no Content-Encoding.
    const stream = new Blob([bytes as Uint8Array<ArrayBuffer>])
      .stream()
      .pipeThrough(new DecompressionStream("gzip"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  } catch (cause) {
    throw new TileFormatError("tile is not valid gzip", { cause });
  }
}

/** Reads the payload front to back: little-endian, no padding, no alignment. */
class Cursor {
  private at = 0;
  private readonly view: DataView;

  constructor(private readonly payload: Uint8Array) {
    this.view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  }

  private advance(size: number): number {
    const start = this.at;
    if (start + size > this.payload.length) {
      throw new TileFormatError("tile is truncated");
    }
    this.at = start + size;
    return start;
  }

  bytes(size: number): Uint8Array {
    const start = this.advance(size);
    return this.payload.subarray(start, start + size);
  }

  u16(): number {
    return this.view.getUint16(this.advance(2), true);
  }

  u32(): number {
    return this.view.getUint32(this.advance(4), true);
  }

  i32Column(count: number): Int32Array {
    const start = this.advance(4 * count);
    return Int32Array.from({ length: count }, (_, k) => this.view.getInt32(start + 4 * k, true));
  }

  u32Column(count: number): Uint32Array {
    const start = this.advance(4 * count);
    return Uint32Array.from({ length: count }, (_, k) => this.view.getUint32(start + 4 * k, true));
  }

  u64Column(count: number): BigUint64Array {
    const start = this.advance(8 * count);
    return BigUint64Array.from({ length: count }, (_, k) =>
      this.view.getBigUint64(start + 8 * k, true),
    );
  }

  atEnd(): boolean {
    return this.at === this.payload.length;
  }
}

function checkIndexes(indexes: Uint32Array, limit: number, what: string): void {
  for (const index of indexes) {
    if (index >= limit) {
      throw new TileFormatError(`${what} ${index} is out of range (only ${limit} exist)`);
    }
  }
}

function nodeIds(raw: BigUint64Array): Float64Array {
  const ids = new Float64Array(raw.length);
  const seen = new Set<number>();
  raw.forEach((id, k) => {
    if (id >= NODE_ID_LIMIT) {
      throw new TileFormatError("walk node ids must be below 2^53");
    }
    ids[k] = Number(id);
    seen.add(ids[k]);
  });
  if (seen.size !== ids.length) {
    throw new TileFormatError("walk node ids must be unique within a tile");
  }
  return ids;
}

/** Undo the azimuth delta: a running sum mod 256 along each Candidate's row. */
function profileCodes(deltas: Uint8Array, candidates: number): Uint8Array {
  const codes = new Uint8Array(deltas.length);
  for (let row = 0; row < candidates; row++) {
    let code = 0; // each row starts afresh
    for (let i = row * PROFILE_SAMPLES, end = i + PROFILE_SAMPLES; i < end; i++) {
      code = (code + deltas[i]!) & 0xff;
      if (code >= CODE_COUNT) {
        throw new TileFormatError(
          `Horizon profile code ${code} is not one of the ${CODE_COUNT} storage codes`,
        );
      }
      codes[i] = code;
    }
  }
  return codes;
}

/**
 * The bytes of a published `.bin` file -> the tile.
 *
 * Rejects with `TileFormatError` for anything docs/tile-format-f1.md says a
 * reader must refuse, and with its subclass `UnsupportedFormatError` for a
 * format number other than 1. Pass `expectedGridRef` (the file name without
 * `.bin`) to also refuse a tile that is not the one its name says it is.
 */
export async function decodeTile(bytes: Uint8Array, expectedGridRef?: string): Promise<Tile> {
  const cursor = new Cursor(await gunzip(bytes));

  const magic = String.fromCharCode(...cursor.bytes(4));
  if (magic !== "CSUN") {
    throw new TileFormatError("not a Ciao Sun tile (bad magic)");
  }
  // Nothing after the format number is trusted until the number is known.
  const format = cursor.u16();
  if (format !== FORMAT) {
    throw new UnsupportedFormatError(format);
  }
  const gridRef = String.fromCharCode(...cursor.bytes(6));
  const candidateCount = cursor.u32();
  const nodeCount = cursor.u32();
  const edgeCount = cursor.u32();
  const nameCount = cursor.u32();

  const latE7 = cursor.i32Column(candidateCount);
  const lonE7 = cursor.i32Column(candidateCount);
  const nodeIndex = cursor.u32Column(candidateCount);
  const offsetCm = cursor.u32Column(candidateCount);
  const nameIndex = cursor.u32Column(candidateCount);
  const rawNodeId = cursor.u64Column(nodeCount);
  const nodeLatE7 = cursor.i32Column(nodeCount);
  const nodeLonE7 = cursor.i32Column(nodeCount);
  const edgeFrom = cursor.u32Column(edgeCount);
  const edgeTo = cursor.u32Column(edgeCount);
  const edgeLengthCm = cursor.u32Column(edgeCount);
  const deltas = cursor.bytes(candidateCount * PROFILE_SAMPLES);

  const utf8 = new TextDecoder("utf-8", { fatal: true });
  const names: string[] = [];
  for (let k = 0; k < nameCount; k++) {
    const encoded = cursor.bytes(cursor.u16());
    try {
      names.push(utf8.decode(encoded));
    } catch (cause) {
      throw new TileFormatError("Spot name is not valid UTF-8", { cause });
    }
  }
  if (!cursor.atEnd()) {
    throw new TileFormatError("tile has bytes after its last field");
  }

  if (!GRID_REF.test(gridRef)) {
    throw new TileFormatError(`${JSON.stringify(gridRef)} is not a 1 km OS grid ref`);
  }
  if (expectedGridRef !== undefined && expectedGridRef !== gridRef) {
    throw new TileFormatError(`${expectedGridRef}.bin holds tile ${gridRef}`);
  }
  checkIndexes(nodeIndex, nodeCount, "Candidate walk node index");
  checkIndexes(nameIndex, nameCount, "Candidate Spot name index");
  checkIndexes(edgeFrom, nodeCount, "edge 'from' node index");
  checkIndexes(edgeTo, nodeCount, "edge 'to' node index");

  return {
    gridRef,
    names,
    candidates: {
      latE7,
      lonE7,
      nodeIndex,
      offsetCm,
      nameIndex,
      profileCodes: profileCodes(deltas, candidateCount),
    },
    walkGraph: {
      nodeId: nodeIds(rawNodeId),
      nodeLatE7,
      nodeLonE7,
      edgeFrom,
      edgeTo,
      edgeLengthCm,
    },
  };
}
