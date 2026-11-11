// @vitest-environment happy-dom
//
// The map-first screen over the committed synthetic build. MapLibre needs
// WebGL, which happy-dom lacks, so the map is a fake MapFactory that records
// what the screen asks of it; `src/map/style.test.ts` covers the style.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type AppDeps, startApp } from "../../src/app";
import type { Answer, Query } from "../../src/contract";
import type { FetchLike } from "../../src/loader/loader";
import type { MapFactory, MapMarkers, MapOptions } from "../../src/map/map";
import { SETTINGS_KEY } from "../../src/settings/store";

const SYNTHETIC = `${resolve(import.meta.dirname, "../../../fixtures/synthetic")}/`;
const BUILD = `${SYNTHETIC}f1/20261111a/`;
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };
const MANIFEST_PATH = "f1/20261111a/manifest.json";
const MANIFEST = JSON.parse(readFileSync(`${BUILD}manifest.json`, "utf8"));

function fixture(id: string): { query: Query; answer: Answer } {
  return JSON.parse(readFileSync(`${BUILD}fixtures/${id}.json`, "utf8"));
}

// The winter solstice fixture asks at 07:30 on 21 Dec with a clear sky.
const WINTER = fixture("morning-winter-solstice");

function host(override: Record<string, unknown> = {}): FetchLike {
  return async (url) => {
    const path = url.slice(PIN.dataBase.length);
    if (path in override) return new Response(JSON.stringify(override[path]));
    try {
      return new Response(readFileSync(SYNTHETIC + path));
    } catch {
      return new Response("", { status: 404 });
    }
  };
}

class MemoryStorage {
  readonly items = new Map<string, string>();
  getItem = (key: string) => this.items.get(key) ?? null;
  setItem = (key: string, value: string) => void this.items.set(key, value);
}

/** A map that records what it is asked to show; `tap` is a tap on a marker. */
function fakeMap() {
  const made: { container: HTMLElement; options: MapOptions }[] = [];
  const shown: MapMarkers[] = [];
  const highlighted: (string | undefined)[] = [];
  const factory: MapFactory = async (container, options) => {
    made.push({ container, options });
    return {
      show: (markers) => void shown.push(markers),
      highlight: (id) => void highlighted.push(id),
    };
  };
  return {
    factory,
    made,
    shown,
    highlighted,
    last: () => shown.at(-1),
    tap: (id: string) => made[0]!.options.onSelect(id),
  };
}

function deps(overrides: Partial<AppDeps> = {}): AppDeps {
  const storage = new MemoryStorage();
  storage.setItem(SETTINGS_KEY, JSON.stringify({ wakeTime: WINTER.query.wakeTime, maxWalkMin: WINTER.query.maxWalkMin }));
  return {
    config: PIN,
    fetch: host(),
    storage: () => storage,
    now: () => Date.parse("2026-12-20T21:00:00+00:00"),
    locate: async () => WINTER.query.origin,
    ...overrides,
  };
}

async function mount(d: AppDeps) {
  const root = document.createElement("div");
  document.body.append(root);
  const app = startApp(root, d);
  await app.idle();
  return { root, app };
}

const rowIds = (root: HTMLElement) => [...root.querySelectorAll("[data-spot]")].map((row) => row.getAttribute("data-spot"));
const row = (root: HTMLElement, id: string) => root.querySelector(`[data-spot="${id}"]`);
const tapRow = (root: HTMLElement, id: string) =>
  (row(root, id)?.querySelector("[data-action=select-spot]") as HTMLButtonElement).click();
const selectedIds = (root: HTMLElement) =>
  [...root.querySelectorAll("[data-spot][aria-current=true]")].map((el) => el.getAttribute("data-spot"));
const sheetSnap = (root: HTMLElement) => root.querySelector(".sheet")?.getAttribute("data-sheet");
const handle = (root: HTMLElement) => root.querySelector("[data-action=sheet]") as HTMLButtonElement;

/** A finger on the sheet's handle, from one screen height to another. */
function drag(el: Element, fromY: number, toY: number) {
  const at = (type: string, clientY: number) =>
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerId: 1, clientY }));
  at("pointerdown", fromY);
  at("pointermove", (fromY + toY) / 2);
  at("pointermove", toY);
  at("pointerup", toY);
  el.dispatchEvent(new MouseEvent("click", { bubbles: true })); // the browser's click after the drag
}
const sunTimes = (root: HTMLElement, id: string) =>
  row(root, id)?.querySelector("[data-field=sun-times]")?.textContent ?? undefined;

describe("Map-first screen", () => {
  it("puts the origin and the spots on the map, numbered in list order", async () => {
    const map = fakeMap();
    const { root } = await mount(deps({ map: map.factory }));
    const expected = WINTER.answer.spots;
    expect(expected.length).toBeGreaterThan(1);
    expect(rowIds(root)).toEqual(expected.map((s) => s.candidateId));
    expect(map.last()).toEqual({
      origin: WINTER.query.origin,
      spots: expected.map((s, i) => ({ id: s.candidateId, rank: i + 1, name: s.name, lat: s.lat, lon: s.lon })),
    });
  });

  it("draws the map from the build's z/x/y basemap, inside the manifest's bounds and zooms", async () => {
    const map = fakeMap();
    const { root } = await mount(deps({ map: map.factory }));
    expect(map.made).toHaveLength(1);
    expect(map.made[0]!.options.basemap).toEqual({
      tiles: "https://data.example/f1/20261111a/basemap/{z}/{x}/{y}.mvt",
      bounds: MANIFEST.basemap.bounds,
      minZoom: 10,
      maxZoom: 15,
    });
    // The map lives under the screen and survives its redraws.
    const container = map.made[0]!.container;
    expect(container.parentElement).toBe(root);
    const removed: Node[] = [];
    const watch = new MutationObserver((records) => records.forEach((r) => removed.push(...r.removedNodes)));
    watch.observe(root, { childList: true });
    (root.querySelector("[name=sky]") as HTMLSelectElement).dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise((settle) => setTimeout(settle, 0));
    watch.disconnect();
    expect(removed.length).toBeGreaterThan(0); // the screen was redrawn,
    expect(removed).not.toContain(container); // and the map never left the page
  });

  it("credits OpenStreetMap and Protomaps in the map's corner, in the manifest's words", async () => {
    const reworded = {
      ...MANIFEST,
      attribution: MANIFEST.attribution.map((line: { source: string; text: string }) => ({ ...line, text: `${line.text} (as built)` })),
    };
    const map = fakeMap();
    await mount(deps({ map: map.factory, fetch: host({ [MANIFEST_PATH]: reworded }) }));
    expect(map.made[0]!.options.credits).toEqual([
      { text: "© OpenStreetMap contributors (as built)", url: "https://opendatacommons.org/licenses/odbl/1-0/" },
      { text: "Protomaps © OpenStreetMap (as built)", url: "https://opendatacommons.org/licenses/odbl/1-0/" },
    ]);
  });

  it("draws the spots on a plain ground when the manifest has no basemap", async () => {
    const { basemap: _, ...bare } = MANIFEST;
    const map = fakeMap();
    await mount(deps({ map: map.factory, fetch: host({ [MANIFEST_PATH]: bare }) }));
    expect(map.made[0]!.options.basemap).toBeUndefined();
    expect(map.last()?.spots).toHaveLength(WINTER.answer.spots.length);
  });

  it("highlights a spot tapped in the list on the map, and shows its sun times", async () => {
    const map = fakeMap();
    const { root } = await mount(deps({ map: map.factory }));
    const [, second] = WINTER.answer.spots;
    const framed = map.shown.length;

    tapRow(root, second!.candidateId);

    expect(selectedIds(root)).toEqual([second!.candidateId]);
    expect(map.highlighted.at(-1)).toBe(second!.candidateId);
    expect(map.shown).toHaveLength(framed); // a highlight doesn't reframe the map
    // West Row has the sun in view 08:16-10:30, all of it low sun.
    expect(sunTimes(root, second!.candidateId)).toBe("Sun in view 08:16–10:30 · low sun 08:16–10:30");
    expect(sunTimes(root, WINTER.answer.spots[0]!.candidateId)).toBeUndefined();
  });

  it("highlights the row of a spot tapped on the map", async () => {
    const map = fakeMap();
    const { root } = await mount(deps({ map: map.factory }));
    const [first, second] = WINTER.answer.spots;
    tapRow(root, second!.candidateId);

    map.tap(first!.candidateId);

    expect(selectedIds(root)).toEqual([first!.candidateId]);
    expect(map.highlighted.at(-1)).toBe(first!.candidateId);
    expect(sunTimes(root, first!.candidateId)).toBe("Sun in view 08:16–10:30 · low sun 08:16–10:30");
  });

  it("clears the highlight when a new answer no longer has the spot", async () => {
    const map = fakeMap();
    const { root, app } = await mount(deps({ map: map.factory }));
    map.tap(WINTER.answer.spots[0]!.candidateId);
    const outside = fixture("morning-not-covered").query.origin;
    (root.querySelector("[data-action=type-origin]") as HTMLButtonElement).click();
    const typed = root.querySelector("[name=origin]") as HTMLInputElement;
    typed.value = `${outside.lat}, ${outside.lon}`;
    typed.dispatchEvent(new Event("change", { bubbles: true }));
    await app.idle();
    expect(map.last()).toEqual({ origin: outside, spots: [] });
    expect(map.highlighted.at(-1)).toBeUndefined();
  });

  it("holds the list in a bottom sheet that a tap on its handle pulls up and lets down", async () => {
    const { root } = await mount(deps({ map: fakeMap().factory }));
    expect(sheetSnap(root)).toBe("half");
    expect(root.querySelector(".sheet [data-spot]")).not.toBeNull();
    handle(root).click();
    expect(sheetSnap(root)).toBe("full");
    handle(root).click();
    expect(sheetSnap(root)).toBe("peek");
    handle(root).click();
    expect(sheetSnap(root)).toBe("half");
  });

  it("snaps the dragged sheet to the nearest stop, and keeps it there across redraws", async () => {
    const { root } = await mount(deps({ map: fakeMap().factory }));
    drag(handle(root), 700, 60); // up most of the screen
    expect(sheetSnap(root)).toBe("full");
    drag(handle(root), 100, 600); // down most of the screen
    expect(sheetSnap(root)).toBe("peek");
    (root.querySelector("[name=sky]") as HTMLSelectElement).dispatchEvent(new Event("change", { bubbles: true }));
    expect(sheetSnap(root)).toBe("peek");
  });

  it("raises a let-down sheet when a spot is tapped on the map, so its row shows", async () => {
    const map = fakeMap();
    const { root } = await mount(deps({ map: map.factory }));
    drag(handle(root), 100, 600);
    expect(sheetSnap(root)).toBe("peek");
    map.tap(WINTER.answer.spots[1]!.candidateId);
    expect(sheetSnap(root)).toBe("half");
  });

  it("still shows the list when no map can be made", async () => {
    const failing: MapFactory = async () => {
      throw new Error("WebGL is not available");
    };
    const { root } = await mount(deps({ map: failing }));
    expect(rowIds(root)).toEqual(WINTER.answer.spots.map((s) => s.candidateId));
  });
});
