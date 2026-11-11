// The router: decoded tiles as one world, every Candidate and the joined walk
// graph, and walks over it from an origin.
//
// `ciao_sun.reference.world` is the reference. The distance formula, the
// snap and the walk rules are its own, expression for expression, so that both
// give the same whole metres. Terms follow GLOSSARY.md.

import { RADIANS_PER_DEGREE } from "../angles";
import { PROFILE_SAMPLES, type Tile, spotName } from "../tile/decode";

/** Walking speed, metres per minute. */
export const WALK_SPEED_M_PER_MIN = 80;
/** Mean Earth radius (IUGG), metres: the radius of every lat/lon distance (the haversine) and of the origin's local plane. */
export const DISTANCE_EARTH_RADIUS_M = 6_371_008.8;

// As Python's math.radians and numpy's radians: one multiplication by pi/180.
const radians = (degrees: number) => degrees * RADIANS_PER_DEGREE;

/** Great-circle (haversine) distance between two WGS84 positions, in metres. */
export function distanceM(latA: number, lonA: number, latB: number, lonB: number): number {
  const phiA = radians(latA);
  const phiB = radians(latB);
  const halfDphi = (phiB - phiA) / 2;
  const halfDlambda = radians(lonB - lonA) / 2;
  const h = Math.sin(halfDphi) ** 2 + Math.cos(phiA) * Math.cos(phiB) * Math.sin(halfDlambda) ** 2;
  return 2 * DISTANCE_EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/**
 * All Candidates of the tiles, in (grid ref, index) order, and the joined walk
 * graph. Element k of every Candidate column is Candidate k. Nodes are joined
 * on node id; two edges between the same pair of ids are one edge.
 */
export interface World {
  readonly gridRef: readonly string[];
  /** The Candidate's index within its tile. */
  readonly index: readonly number[];
  /** Spot name. */
  readonly name: readonly string[];
  readonly lat: Float64Array;
  readonly lon: Float64Array;
  /** Into the node columns below. */
  readonly node: Int32Array;
  readonly offsetCm: Float64Array;
  /** PROFILE_SAMPLES storage codes per Candidate, in Candidate order. */
  readonly profileCodes: Uint8Array;
  readonly nodeLat: Float64Array;
  readonly nodeLon: Float64Array;
  /** [node, node, length in cm], sorted by node ids. */
  readonly edges: readonly (readonly [number, number, number])[];
}

export function candidateCount(world: World): number {
  return world.gridRef.length;
}

/** "<grid ref>/<index>". */
export function candidateId(world: World, k: number): string {
  return `${world.gridRef[k]}/${world.index[k]}`;
}

/** The ascending order of candidateIds: by grid ref, then by index as a number. */
export function compareCandidates(world: World, a: number, b: number): number {
  const refA = world.gridRef[a]!;
  const refB = world.gridRef[b]!;
  if (refA !== refB) {
    return refA < refB ? -1 : 1;
  }
  return world.index[a]! - world.index[b]!;
}

/** Candidate k's Horizon profile storage codes: a view, not a copy. */
export function profileCodesOf(world: World, k: number): Uint8Array {
  return world.profileCodes.subarray(k * PROFILE_SAMPLES, (k + 1) * PROFILE_SAMPLES);
}

export function joinTiles(tiles: readonly Tile[]): World {
  const nodeOfId = new Map<number, number>();
  const nodeLat: number[] = [];
  const nodeLon: number[] = [];
  // Keyed "minId,maxId"; the value keeps the ids for sorting.
  const edgeLength = new Map<string, [number, number, number]>();
  const gridRef: string[] = [];
  const index: number[] = [];
  const name: string[] = [];
  const lat: number[] = [];
  const lon: number[] = [];
  const node: number[] = [];
  const offsetCm: number[] = [];
  const codes: Uint8Array[] = [];

  const sorted = [...tiles].sort((a, b) => (a.gridRef < b.gridRef ? -1 : a.gridRef > b.gridRef ? 1 : 0));
  for (const tile of sorted) {
    const g = tile.walkGraph;
    const c = tile.candidates;
    const local = new Int32Array(g.nodeId.length);
    for (let i = 0; i < g.nodeId.length; i++) {
      const id = g.nodeId[i]!;
      let n = nodeOfId.get(id);
      if (n === undefined) {
        n = nodeLat.length;
        nodeOfId.set(id, n);
        nodeLat.push(g.nodeLatE7[i]! / 1e7);
        nodeLon.push(g.nodeLonE7[i]! / 1e7);
      }
      local[i] = n;
    }
    for (let e = 0; e < g.edgeFrom.length; e++) {
      const a = g.nodeId[g.edgeFrom[e]!]!;
      const b = g.nodeId[g.edgeTo[e]!]!;
      const low = Math.min(a, b);
      const high = Math.max(a, b);
      const key = `${low},${high}`;
      if (!edgeLength.has(key)) {
        edgeLength.set(key, [low, high, g.edgeLengthCm[e]!]);
      }
    }
    const count = c.latE7.length;
    for (let k = 0; k < count; k++) {
      gridRef.push(tile.gridRef);
      index.push(k);
      name.push(spotName(tile, k));
      lat.push(c.latE7[k]! / 1e7);
      lon.push(c.lonE7[k]! / 1e7);
      node.push(local[c.nodeIndex[k]!]!);
      offsetCm.push(c.offsetCm[k]!);
    }
    codes.push(c.profileCodes.subarray(0, count * PROFILE_SAMPLES));
  }

  const profileCodes = new Uint8Array(gridRef.length * PROFILE_SAMPLES);
  let at = 0;
  for (const part of codes) {
    profileCodes.set(part, at);
    at += part.length;
  }
  const edges = [...edgeLength.values()]
    .sort((x, y) => x[0] - y[0] || x[1] - y[1])
    .map(([a, b, length]) => [nodeOfId.get(a)!, nodeOfId.get(b)!, length] as const);

  return {
    gridRef,
    index,
    name,
    lat: Float64Array.from(lat),
    lon: Float64Array.from(lon),
    node: Int32Array.from(node),
    offsetCm: Float64Array.from(offsetCm),
    profileCodes,
    nodeLat: Float64Array.from(nodeLat),
    nodeLon: Float64Array.from(nodeLon),
    edges,
  };
}

/** A binary min-heap of [distance, node], ordered as Python's heapq orders the tuples. */
class Queue {
  private readonly items: [number, number][] = [];

  get size(): number {
    return this.items.length;
  }

  private less(i: number, j: number): boolean {
    const a = this.items[i]!;
    const b = this.items[j]!;
    return a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);
  }

  private swap(i: number, j: number): void {
    const t = this.items[i]!;
    this.items[i] = this.items[j]!;
    this.items[j] = t;
  }

  push(item: [number, number]): void {
    const items = this.items;
    items.push(item);
    let i = items.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (!this.less(i, parent)) {
        break;
      }
      this.swap(i, parent);
      i = parent;
    }
  }

  pop(): [number, number] {
    const items = this.items;
    const top = items[0]!;
    const last = items.pop()!;
    if (items.length > 0) {
      items[0] = last;
      let i = 0;
      for (;;) {
        const left = 2 * i + 1;
        const right = left + 1;
        let smallest = i;
        if (left < items.length && this.less(left, smallest)) smallest = left;
        if (right < items.length && this.less(right, smallest)) smallest = right;
        if (smallest === i) break;
        this.swap(i, smallest);
        i = smallest;
      }
    }
    return top;
  }
}

/**
 * The walk from the origin to every Candidate in whole metres; -1 where it
 * exceeds `limitM`.
 *
 * The origin is snapped to the nearest point of the nearest walk edge, each
 * edge taken as the straight line between its nodes, on a local flat plane
 * centred on the origin. The walk starts at that point (getting to it is not
 * counted), splits the snapped edge's length in the same proportion, follows
 * the shortest path over the graph (Dijkstra), and ends with the Candidate's
 * offset from its node. Centimetres round half up to metres.
 */
export function walkMetres(world: World, originLat: number, originLon: number, limitM: number): Int32Array {
  const walks = new Int32Array(candidateCount(world)).fill(-1);
  if (world.edges.length === 0) {
    return walks;
  }

  // Local plane: metres east and north of the origin.
  const cosLat = Math.cos(radians(originLat));
  const nodes = world.nodeLat.length;
  const x = new Float64Array(nodes);
  const y = new Float64Array(nodes);
  for (let n = 0; n < nodes; n++) {
    x[n] = radians(world.nodeLon[n]! - originLon) * cosLat * DISTANCE_EARTH_RADIUS_M;
    y[n] = radians(world.nodeLat[n]! - originLat) * DISTANCE_EARTH_RADIUS_M;
  }

  let bestAway = Infinity;
  let snapped = 0;
  let fraction = 0;
  world.edges.forEach(([a, b], e) => {
    const dx = x[b]! - x[a]!;
    const dy = y[b]! - y[a]!;
    const span = dx * dx + dy * dy;
    const t = span === 0 ? 0 : Math.min(1, Math.max(0, -(x[a]! * dx + y[a]! * dy) / span));
    const away = Math.hypot(x[a]! + t * dx, y[a]! + t * dy);
    if (away < bestAway) {
      bestAway = away;
      snapped = e;
      fraction = t;
    }
  });

  const neighbours = new Map<number, [number, number][]>();
  const link = (from: number, to: number, length: number) => {
    let list = neighbours.get(from);
    if (!list) {
      list = [];
      neighbours.set(from, list);
    }
    list.push([to, length]);
  };
  for (const [a, b, length] of world.edges) {
    link(a, b, length);
    link(b, a, length);
  }

  const [a, b, length] = world.edges[snapped]!;
  const limitCm = limitM * 100;
  const reached = new Map<number, number>();
  const queue = new Queue();
  queue.push([fraction * length, a]);
  queue.push([(1 - fraction) * length, b]);
  while (queue.size > 0) {
    const [soFar, n] = queue.pop();
    if (reached.has(n) || soFar > limitCm) {
      continue;
    }
    reached.set(n, soFar);
    for (const [other, step] of neighbours.get(n) ?? []) {
      if (!reached.has(other)) {
        queue.push([soFar + step, other]);
      }
    }
  }

  for (let k = 0; k < walks.length; k++) {
    const distance = reached.get(world.node[k]!);
    if (distance !== undefined) {
      const metres = Math.floor((distance + world.offsetCm[k]!) / 100 + 0.5);
      if (metres <= limitM) {
        walks[k] = metres;
      }
    }
  }
  return walks;
}
