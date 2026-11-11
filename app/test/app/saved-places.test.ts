// @vitest-environment happy-dom
//
// Saved places (#49): saved, renamed and deleted on the phone only, and
// picked as the origin when GPS is denied or when planning from elsewhere.
// The whole screen over the committed synthetic build, as morning.test.ts.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type AppDeps, startApp } from "../../src/app";
import type { Query } from "../../src/contract";
import { FORECAST_URL } from "../../src/forecast/forecast";
import type { FetchLike } from "../../src/loader/loader";
import { SETTINGS_KEY } from "../../src/settings/store";

const SYNTHETIC = `${resolve(import.meta.dirname, "../../../fixtures/synthetic")}/`;
const BUILD = `${SYNTHETIC}f1/20261111a/`;
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };

function query(id: string): Query {
  return JSON.parse(readFileSync(`${BUILD}fixtures/${id}.json`, "utf8")).query;
}

// Inside the coverage (the winter solstice fixture's origin) and outside it.
const WINTER = query("morning-winter-solstice");
const INSIDE = WINTER.origin;
const OUTSIDE = query("morning-not-covered").origin;

function host() {
  const requested: string[] = [];
  const fetch: FetchLike = async (url) => {
    requested.push(url);
    try {
      return new Response(readFileSync(SYNTHETIC + url.slice(PIN.dataBase.length)));
    } catch {
      return new Response("", { status: 404 });
    }
  };
  return { fetch, requested };
}

class MemoryStorage {
  readonly items = new Map<string, string>();
  getItem = (key: string) => this.items.get(key) ?? null;
  setItem = (key: string, value: string) => void this.items.set(key, value);
}

const DENIED = () => Promise.reject(new Error("denied"));

function deps(storage: MemoryStorage, overrides: Partial<AppDeps> = {}): AppDeps {
  return {
    config: PIN,
    fetch: host().fetch,
    storage: () => storage,
    now: () => Date.parse("2026-12-20T21:00:00+00:00"),
    locate: async () => INSIDE,
    ...overrides,
  };
}

function withSettings(settings: Record<string, unknown>): MemoryStorage {
  const storage = new MemoryStorage();
  storage.setItem(
    SETTINGS_KEY,
    JSON.stringify({ wakeTime: WINTER.wakeTime, maxWalkMin: WINTER.maxWalkMin, ...settings }),
  );
  return storage;
}

async function mount(d: AppDeps) {
  const root = document.createElement("div");
  const app = startApp(root, d);
  await app.idle();
  openPlaces(root);
  return { root, app };
}

/** The saved places list opens from a link under the sentence. */
function openPlaces(root: HTMLElement) {
  const toggle = root.querySelector("[data-action=toggle-places]");
  if (toggle?.getAttribute("aria-expanded") === "false") (toggle as HTMLButtonElement).click();
}

function change(el: Element | null, value: string) {
  expect(el).not.toBeNull();
  const input = el as HTMLInputElement | HTMLSelectElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function click(el: Element | null) {
  expect(el).not.toBeNull();
  (el as HTMLButtonElement).click();
}

const placeNames = (root: HTMLElement) =>
  [...root.querySelectorAll("[data-place] [name=place-name]")].map((el) => (el as HTMLInputElement).value);

/** The origin slot's words: what "here" says is in use. */
function originShown(root: HTMLElement): string {
  const choice = root.querySelector("[name=origin-choice]") as HTMLSelectElement | null;
  if (choice) return choice.selectedOptions[0]?.textContent ?? "";
  return root.querySelector("[data-action=type-origin]")?.textContent ?? "";
}

async function saveCurrentAs(root: HTMLElement, app: { idle(): Promise<void> }, name: string) {
  change(root.querySelector("[name=new-place-name]"), name);
  click(root.querySelector("[data-action=save-place]"));
  await app.idle();
}

const HOME = { id: "1", name: "Home", lat: INSIDE.lat, lon: INSIDE.lon };
const AWAY = { id: "2", name: "Aunt's", lat: OUTSIDE.lat, lon: OUTSIDE.lon };

describe("saved places", () => {
  it("save the current position under a name, and keep it across a reload", async () => {
    const storage = withSettings({});
    const first = await mount(deps(storage));
    await saveCurrentAs(first.root, first.app, "Home");
    expect(placeNames(first.root)).toEqual(["Home"]);

    const reloaded = await mount(deps(storage, { locate: DENIED }));
    expect(placeNames(reloaded.root)).toEqual(["Home"]);
    // Saved where the GPS put the person.
    const id = reloaded.root.querySelector("[data-place]")!.getAttribute("data-place")!;
    change(reloaded.root.querySelector("[name=origin-choice]"), `place:${id}`);
    await reloaded.app.idle();
    expect(reloaded.root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it("save a typed position under a name", async () => {
    const storage = withSettings({});
    const { root, app } = await mount(deps(storage, { locate: DENIED }));
    expect(root.querySelector("[data-action=save-place]")).toBeNull(); // Nothing to save yet.
    change(root.querySelector("[name=origin]"), `${OUTSIDE.lat}, ${OUTSIDE.lon}`);
    await app.idle();
    await saveCurrentAs(root, app, "Aunt's");
    expect(placeNames(root)).toEqual(["Aunt's"]);
    expect(originShown(root)).toBe("Aunt's");
  });

  it("rename and delete, and keep both across a reload", async () => {
    const storage = withSettings({ places: [HOME, AWAY] });
    const first = await mount(deps(storage));
    expect(placeNames(first.root)).toEqual(["Home", "Aunt's"]);
    change(first.root.querySelector("[data-place='1'] [name=place-name]"), "Flat");
    await first.app.idle();
    click(first.root.querySelector("[data-place='2'] [data-action=delete-place]"));
    await first.app.idle();
    expect(placeNames(first.root)).toEqual(["Flat"]);

    const reloaded = await mount(deps(storage));
    expect(placeNames(reloaded.root)).toEqual(["Flat"]);
  });

  it("a name can't be emptied", async () => {
    const storage = withSettings({ places: [HOME] });
    const { root, app } = await mount(deps(storage));
    change(root.querySelector("[data-place='1'] [name=place-name]"), "   ");
    await app.idle();
    expect(placeNames(root)).toEqual(["Home"]);
  });

  it("when GPS is denied, the sentence offers the saved places instead of failing", async () => {
    const storage = withSettings({ places: [HOME, AWAY] });
    const { root, app } = await mount(deps(storage, { locate: DENIED }));
    const choice = root.querySelector("[data-field=sentence] [name=origin-choice]") as HTMLSelectElement;
    expect(choice).not.toBeNull();
    const offered = [...choice.options].map((o) => o.textContent);
    expect(offered).toEqual(expect.arrayContaining(["Home", "Aunt's"]));
    expect(root.querySelector("[data-status=failed]")).toBeNull();

    change(choice, "place:1");
    await app.idle();
    expect(originShown(root)).toBe("Home");
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it("pick a saved place while GPS works, to plan from somewhere else, and go back to here", async () => {
    const storage = withSettings({ places: [AWAY] });
    const { root, app } = await mount(deps(storage));
    expect(originShown(root)).toBe("here");
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);

    change(root.querySelector("[name=origin-choice]"), "place:2");
    await app.idle();
    expect(originShown(root)).toBe("Aunt's");

    change(root.querySelector("[name=origin-choice]"), "here");
    await app.idle();
    expect(originShown(root)).toBe("here");
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it('a saved place outside the coverage gives "not covered here"', async () => {
    const storage = withSettings({ places: [AWAY] });
    const { root, app } = await mount(deps(storage, { locate: DENIED }));
    change(root.querySelector("[name=origin-choice]"), "place:2");
    await app.idle();
    expect(root.textContent).toMatch(/not covered here/i);
  });

  it("deleting the place in use goes back to here", async () => {
    const storage = withSettings({ places: [AWAY] });
    const { root, app } = await mount(deps(storage));
    change(root.querySelector("[name=origin-choice]"), "place:2");
    await app.idle();
    click(root.querySelector("[data-place='2'] [data-action=delete-place]"));
    await app.idle();
    expect(originShown(root)).toBe("here");
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it("work for the session when browser storage is unavailable, and say so", async () => {
    const { root, app } = await mount(
      deps(new MemoryStorage(), {
        storage: () => {
          throw new DOMException("blocked", "SecurityError");
        },
      }),
    );
    await saveCurrentAs(root, app, "Home");
    expect(placeNames(root)).toEqual(["Home"]);
    expect(root.querySelector("[data-field=places-note]")?.textContent).toMatch(/only until/i);
  });

  it("never send a saved place, its name or the GPS position in any request", async () => {
    const gps = { lat: 51.45437, lon: -2.59713 };
    const place = { id: "7", name: "Secret garden", lat: 51.46123, lon: -2.61789 };
    const served = host();
    const storage = withSettings({ places: [place] });
    const { root, app } = await mount(deps(storage, { fetch: served.fetch, locate: async () => gps }));
    await saveCurrentAs(root, app, "Where I stood");
    change(root.querySelector("[name=origin-choice]"), "place:7");
    await app.idle();
    change(root.querySelector("[data-place='7'] [name=place-name]"), "Renamed garden");
    await app.idle();

    expect(served.requested.length).toBeGreaterThan(0);
    const coordinate = (value: number) => [String(value), value.toFixed(4), value.toFixed(3), value.toFixed(2)];
    const secrets = [
      ...coordinate(gps.lat),
      ...coordinate(gps.lon),
      ...coordinate(place.lat),
      ...coordinate(place.lon),
      "Secret",
      "garden",
      "Where",
      "Renamed",
    ];
    // Both positions are in the 0.05 degree forecast cell (51.45, -2.60): the
    // one thing besides the build's files that may leave the phone (#50).
    const forecasts = served.requested.filter((url) => url.startsWith(FORECAST_URL));
    expect(forecasts.length).toBeGreaterThan(0);
    for (const url of served.requested) {
      let text = decodeURIComponent(url);
      if (url.startsWith(FORECAST_URL)) {
        const params = new URL(url).searchParams;
        expect([params.get("latitude"), params.get("longitude")]).toEqual(["51.45", "-2.60"]);
        params.delete("latitude");
        params.delete("longitude");
        text = decodeURIComponent(`${FORECAST_URL}?${params}`);
      } else {
        // Otherwise only the pinned build's files are fetched, at their own paths.
        expect(text.startsWith(`${PIN.dataBase}f1/${PIN.build}/`)).toBe(true);
      }
      for (const secret of secrets) expect(text).not.toContain(secret);
    }
  });
});
