// @vitest-environment happy-dom
//
// The whole Morning screen over the committed synthetic build, with the data
// host, the clock, GPS and browser storage injected.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type AppDeps, startApp } from "../../src/app";
import type { Answer, Query } from "../../src/contract";
import type { FetchLike } from "../../src/loader/loader";
import { answer } from "../../src/scorer/answer";
import { SETTINGS_KEY } from "../../src/settings/store";
import { decodeTile } from "../../src/tile/decode";

// happy-dom gives import.meta.url an http: scheme; the directory is still a path.
const SYNTHETIC = `${resolve(import.meta.dirname, "../../../fixtures/synthetic")}/`;
const BUILD = `${SYNTHETIC}f1/20261111a/`;
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };

function fixture(id: string): { query: Query; tiles: string[]; answer: Answer } {
  return JSON.parse(readFileSync(`${BUILD}fixtures/${id}.json`, "utf8"));
}

function host(override: Record<string, unknown> = {}) {
  const requested: string[] = [];
  const fetch: FetchLike = async (url) => {
    requested.push(url);
    const path = url.slice(PIN.dataBase.length);
    if (path in override) return new Response(JSON.stringify(override[path]));
    try {
      return new Response(readFileSync(SYNTHETIC + path));
    } catch {
      return new Response("", { status: 404 });
    }
  };
  return { fetch, requested, tiles: () => requested.filter((url) => url.includes("/tiles/")) };
}

class MemoryStorage {
  readonly items = new Map<string, string>();
  getItem = (key: string) => this.items.get(key) ?? null;
  setItem = (key: string, value: string) => void this.items.set(key, value);
}

// The winter solstice fixture asks at 07:30 on 21 Dec with a clear sky.
const WINTER = fixture("morning-winter-solstice");

function deps(overrides: Partial<AppDeps> = {}): AppDeps {
  const storage = new MemoryStorage();
  storage.setItem(SETTINGS_KEY, JSON.stringify({ wakeTime: WINTER.query.wakeTime, maxWalkMin: WINTER.query.maxWalkMin }));
  return {
    config: PIN,
    fetch: host().fetch,
    storage: () => storage,
    now: () => Date.parse("2026-12-20T21:00:00+00:00"),
    locate: async () => WINTER.query.origin,
    ...overrides,
  };
}

async function mount(d: AppDeps) {
  const root = document.createElement("div");
  const app = startApp(root, d);
  await app.idle();
  return { root, app };
}

const names = (root: HTMLElement) => [...root.querySelectorAll("[data-spot] [data-field=name]")].map((el) => el.textContent);

function change(el: Element | null, value: string) {
  const input = el as HTMLInputElement | HTMLSelectElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("Morning screen over a local build", () => {
  it("renders the spots the JS scorer returns, with leave-by and target-met matching the Answer", async () => {
    const { root } = await mount(deps());
    const tiles = await Promise.all(
      WINTER.tiles.map(async (ref) => decodeTile(new Uint8Array(readFileSync(`${BUILD}tiles/${ref}.bin`)), ref)),
    );
    const expected = answer(WINTER.query, tiles);
    expect(expected.spots.length).toBeGreaterThan(0);

    const rows = [...root.querySelectorAll("[data-spot]")];
    expect(rows.map((row) => row.getAttribute("data-spot"))).toEqual(expected.spots.map((s) => s.candidateId));
    expect(rows.map((row) => row.querySelector("[data-field=leave-by]")?.textContent)).toEqual(
      expected.spots.map((s) => `Leave ${s.leaveBy.slice(11, 16)}`),
    );
    expect(rows.map((row) => row.querySelector("[data-field=target]")?.getAttribute("data-met"))).toEqual(
      expected.spots.map((s) => String(s.targetMet)),
    );
    // And the scorer's Answer is the reference's.
    expect(expected.spots.map((s) => s.candidateId)).toEqual(WINTER.answer.spots.map((s) => s.candidateId));
  });

  it("writes the query as one sentence, defaulting to the next Morning window's date", async () => {
    const { root } = await mount(deps());
    const sentence = root.querySelector("[data-field=sentence]")!;
    expect(sentence.textContent).toMatch(/I wake at.*on.*the sky looks.*and I'll walk up to.*min from/s);
    expect((root.querySelector("[name=wakeTime]") as HTMLInputElement).value).toBe("07:30");
    expect((root.querySelector("[name=date]") as HTMLInputElement).value).toBe("2026-12-21");
    expect((root.querySelector("[name=maxWalkMin]") as HTMLSelectElement).value).toBe("15");
  });

  it('shows "this version can\'t read this data" for an unknown manifest format, and loads no tiles', async () => {
    const manifest = JSON.parse(readFileSync(`${BUILD}manifest.json`, "utf8"));
    const served = host({ "f1/20261111a/manifest.json": { ...manifest, format: 2 } });
    const { root } = await mount(deps({ fetch: served.fetch }));
    expect(root.textContent).toMatch(/this version can't read this data/i);
    expect(root.querySelectorAll("[data-spot]")).toHaveLength(0);
    expect(served.tiles()).toEqual([]);
  });

  it('shows "not covered here" for an origin outside the coverage, and loads no tiles', async () => {
    const served = host();
    const outside = fixture("morning-not-covered").query.origin;
    const { root } = await mount(deps({ fetch: served.fetch, locate: async () => outside }));
    expect(root.textContent).toMatch(/not covered here/i);
    expect(served.tiles()).toEqual([]);
  });

  it("shows an overcast sky's fallback Answer as that status, not as a failure", async () => {
    const { root, app } = await mount(deps());
    change(root.querySelector("[name=sky]"), "overcast");
    await app.idle();
    expect(root.querySelector("[data-status]")?.getAttribute("data-status")).toBe("fallback");
  });

  it("falls back to a typed origin when GPS is unavailable", async () => {
    const { root, app } = await mount(deps({ locate: async () => Promise.reject(new Error("denied")) }));
    expect(root.querySelectorAll("[data-spot]")).toHaveLength(0);
    const typed = root.querySelector("[name=origin]");
    expect(typed).not.toBeNull();
    change(typed, `${WINTER.query.origin.lat}, ${WINTER.query.origin.lon}`);
    await app.idle();
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it("keeps a typed origin when a GPS fix arrives after it", async () => {
    let fix: (at: { lat: number; lon: number }) => void = () => {};
    const late = new Promise<{ lat: number; lon: number }>((resolve) => (fix = resolve));
    const root = document.createElement("div");
    const app = startApp(root, deps({ locate: () => late }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    (root.querySelector("[data-action=type-origin]") as HTMLButtonElement).click();
    change(root.querySelector("[name=origin]"), `${WINTER.query.origin.lat}, ${WINTER.query.origin.lon}`);
    fix(fixture("morning-not-covered").query.origin);
    await app.idle();
    expect(root.textContent).not.toMatch(/not covered here/i);
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });
});

describe("saved settings", () => {
  it("keep max walk across a reload", async () => {
    const storage = new MemoryStorage();
    const first = await mount(deps({ storage: () => storage }));
    change(first.root.querySelector("[name=maxWalkMin]"), "10");
    await first.app.idle();
    const reloaded = await mount(deps({ storage: () => storage }));
    expect((reloaded.root.querySelector("[name=maxWalkMin]") as HTMLSelectElement).value).toBe("10");
  });

  it("override Wake time for one query without changing the saved default", async () => {
    const storage = new MemoryStorage();
    const first = await mount(deps({ storage: () => storage }));
    change(first.root.querySelector("[name=wakeTime]"), "08:15");
    await first.app.idle();
    expect((first.root.querySelector("[name=wakeTime]") as HTMLInputElement).value).toBe("08:15");
    const reloaded = await mount(deps({ storage: () => storage }));
    expect((reloaded.root.querySelector("[name=wakeTime]") as HTMLInputElement).value).toBe("07:00");
  });

  it("keep Wake time across a reload once it is saved as the usual one", async () => {
    const storage = new MemoryStorage();
    const first = await mount(deps({ storage: () => storage }));
    change(first.root.querySelector("[name=wakeTime]"), "06:45");
    await first.app.idle();
    (first.root.querySelector("[data-action=save-wake]") as HTMLButtonElement).click();
    await first.app.idle();
    expect(first.root.querySelector("[data-action=save-wake]")).toBeNull();
    const reloaded = await mount(deps({ storage: () => storage }));
    expect((reloaded.root.querySelector("[name=wakeTime]") as HTMLInputElement).value).toBe("06:45");
  });

  it("the app still answers with browser storage unavailable", async () => {
    const { root } = await mount(
      deps({
        storage: () => {
          throw new DOMException("blocked", "SecurityError");
        },
      }),
    );
    // Defaults: Wake time 07:00, 15 min.
    expect((root.querySelector("[name=wakeTime]") as HTMLInputElement).value).toBe("07:00");
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });
});
