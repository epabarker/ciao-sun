// @vitest-environment happy-dom
//
// The sky slot pre-filled from the forecast (#50), over the committed
// synthetic build. Open-Meteo is never called: the injected fetch serves the
// build and canned forecast responses from the same function, so every
// request the app makes is seen here.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type AppDeps, startApp } from "../../src/app";
import type { Query } from "../../src/contract";
import { FORECAST_URL } from "../../src/forecast/forecast";
import { SETTINGS_KEY } from "../../src/settings/store";

const SYNTHETIC = `${resolve(import.meta.dirname, "../../../fixtures/synthetic")}/`;
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };
// 07:30 on 21 Dec, clear: ranked spots with a 10 min target.
const WINTER = (
  JSON.parse(readFileSync(`${SYNTHETIC}f1/20261111a/fixtures/morning-winter-solstice.json`, "utf8")) as {
    query: Query;
  }
).query;
// 21:00 the evening before, in GMT.
const NOW = Date.parse("2026-12-20T21:00:00+00:00");

/** Open-Meteo's hourly cloud cover, the same value every hour of 21 and 22 Dec (UTC). */
function forecastOf(pct: number | null) {
  const first = Date.parse("2026-12-21T00:00:00Z") / 1000;
  const time = Array.from({ length: 48 }, (_, i) => first + i * 3600);
  return { hourly: { time, cloud_cover: time.map(() => pct) } };
}

type Forecast = (url: string) => Promise<Response>;

function host(forecast: Forecast) {
  const requested: string[] = [];
  const fetch = async (url: string) => {
    requested.push(url);
    if (url.startsWith(FORECAST_URL)) return forecast(url);
    try {
      return new Response(readFileSync(SYNTHETIC + url.slice(PIN.dataBase.length)));
    } catch {
      return new Response("", { status: 404 });
    }
  };
  return { fetch, requested, forecasts: () => requested.filter((url) => url.startsWith(FORECAST_URL)) };
}

const canned = (pct: number | null): Forecast => async () => new Response(JSON.stringify(forecastOf(pct)));

function deps(fetch: AppDeps["fetch"], overrides: Partial<AppDeps> = {}): AppDeps {
  const items = new Map([[SETTINGS_KEY, JSON.stringify({ wakeTime: WINTER.wakeTime, maxWalkMin: WINTER.maxWalkMin })]]);
  return {
    config: PIN,
    fetch,
    storage: () => ({ getItem: (k) => items.get(k) ?? null, setItem: (k, v) => void items.set(k, v) }),
    now: () => NOW,
    locate: async () => WINTER.origin,
    ...overrides,
  };
}

async function mount(d: AppDeps) {
  const root = document.createElement("div");
  const app = startApp(root, d);
  await app.idle();
  return { root, app };
}

function change(el: Element | null, value: string) {
  const input = el as HTMLInputElement | HTMLSelectElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

const skySlot = (root: HTMLElement) => root.querySelector("[name=sky]") as HTMLSelectElement;
const credit = (root: HTMLElement) => root.querySelector("[data-field=sky-credit]");
const status = (root: HTMLElement) => root.querySelector("[data-status]")?.getAttribute("data-status");
const targets = (root: HTMLElement) =>
  [...root.querySelectorAll("[data-spot] [data-field=target]")].map((el) => el.textContent);

describe("the sky slot with a forecast", () => {
  it("pre-fills the adapter's category, and the query is asked with it", async () => {
    const { root } = await mount(deps(host(canned(90)).fetch));
    expect(skySlot(root).value).toBe("overcast");
    expect(skySlot(root).getAttribute("data-sky-source")).toBe("forecast");
    // Overcast: the fallback Answer, with its 30 min target.
    expect(status(root)).toBe("fallback");
  });

  it("shows when the forecast was fetched, with the Met Office and Open-Meteo credit and both licences", async () => {
    const { root } = await mount(deps(host(canned(10)).fetch));
    expect(skySlot(root).value).toBe("clear");
    const shown = credit(root);
    expect(shown).not.toBeNull();
    expect(shown!.querySelector("[data-field=fetched-at]")?.textContent).toBe("Forecast fetched 21:00");
    expect(shown!.querySelector("time")?.getAttribute("datetime")).toBe("2026-12-20T21:00:00+00:00");
    expect(shown!.textContent).toContain("Met Office via Open-Meteo");
    expect(shown!.textContent).toContain("cloud cover categorised by Ciao Sun");
    const links = [...shown!.querySelectorAll("a")].map((a) => [a.textContent, a.getAttribute("href")]);
    expect(links).toContainEqual(["CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"]);
    expect(links).toContainEqual(["CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"]);
  });

  it("shows the fetch time on the Europe/London clock", async () => {
    const summer = Date.parse("2026-06-20T20:00:00Z"); // 21:00 BST
    const first = Date.parse("2026-06-21T00:00:00Z") / 1000;
    const time = Array.from({ length: 24 }, (_, i) => first + i * 3600);
    const forecast: Forecast = async () => new Response(JSON.stringify({ hourly: { time, cloud_cover: time.map(() => 10) } }));
    const { root } = await mount(deps(host(forecast).fetch, { now: () => summer }));
    expect(credit(root)?.querySelector("[data-field=fetched-at]")?.textContent).toBe("Forecast fetched 21:00");
  });

  it("is overridden by hand: the Duration target follows and the credit goes", async () => {
    const { root, app } = await mount(deps(host(canned(10)).fetch));
    expect(status(root)).toBe("ranked");
    expect(targets(root).every((t) => t?.startsWith("10 min target"))).toBe(true);

    change(skySlot(root), "partly");
    await app.idle();
    expect(skySlot(root).value).toBe("partly");
    expect(skySlot(root).getAttribute("data-sky-source")).toBe("manual");
    expect(targets(root).length).toBeGreaterThan(0);
    expect(targets(root).every((t) => t?.startsWith("20 min target"))).toBe(true);
    expect(credit(root)).toBeNull();
  });

  it("keeps a manual override when the forecast arrives after it", async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((r) => (release = r));
    const forecast: Forecast = async (url) => {
      await held;
      return canned(90)(url);
    };
    const root = document.createElement("div");
    const app = startApp(root, deps(host(forecast).fetch));
    await new Promise((r) => setTimeout(r, 0));
    change(skySlot(root), "partly");
    release();
    await app.idle();
    expect(skySlot(root).value).toBe("partly");
    expect(skySlot(root).getAttribute("data-sky-source")).toBe("manual");
    expect(credit(root)).toBeNull();
  });

  it("asks again for another window's date, and fills the slot from that answer", async () => {
    const served = host(async (url) =>
      new Response(JSON.stringify(forecastOf(new URL(url).searchParams.get("start_date") === "2026-12-22" ? 90 : 10))),
    );
    const { root, app } = await mount(deps(served.fetch));
    expect(skySlot(root).value).toBe("clear");
    change(root.querySelector("[name=date]"), "2026-12-22");
    await app.idle();
    expect(served.forecasts().map((url) => new URL(url).searchParams.get("start_date"))).toEqual([
      "2026-12-21",
      "2026-12-22",
    ]);
    expect(skySlot(root).value).toBe("overcast");
    expect(credit(root)).not.toBeNull();
  });

  it("does not ask again when nothing about the window or place changed", async () => {
    const served = host(canned(10));
    const { root, app } = await mount(deps(served.fetch));
    change(root.querySelector("[name=maxWalkMin]"), "10");
    await app.idle();
    expect(served.forecasts()).toHaveLength(1);
  });
});

describe("the sky slot without a forecast", () => {
  const never: Forecast = () => new Promise(() => {});
  it.each([
    ["offline", (async () => Promise.reject(new TypeError("Failed to fetch"))) as Forecast],
    ["a failed request", (async () => new Response("", { status: 503 })) as Forecast],
    ["a timed-out request", never],
    ["a date past the forecast horizon", canned(null)],
  ])("is left for manual entry when %s, and the query still runs", async (_name, forecast) => {
    const { root, app } = await mount(deps(host(forecast).fetch, { forecastTimeoutMs: 20 }));
    expect(skySlot(root).disabled).toBe(false);
    expect(skySlot(root).getAttribute("data-sky-source")).toBe("unavailable");
    expect(root.querySelector("[data-field=sky-note]")?.textContent).toMatch(/set the sky by hand/);
    expect(credit(root)).toBeNull();
    expect(status(root)).toBe("ranked");
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);

    change(skySlot(root), "overcast");
    await app.idle();
    expect(status(root)).toBe("fallback");
    expect(credit(root)).toBeNull();
  });

  it("does not ask for a date beyond the forecast's reach", async () => {
    const served = host(canned(10));
    const { root, app } = await mount(deps(served.fetch));
    change(root.querySelector("[name=date]"), "2027-01-15");
    await app.idle();
    expect(served.forecasts()).toHaveLength(1);
    expect(skySlot(root).getAttribute("data-sky-source")).toBe("unavailable");
    expect(credit(root)).toBeNull();
  });
});

describe("the forecast request and the GPS position", () => {
  it("carries only the 0.05 degree coordinate, and the raw position is in no request", async () => {
    // Off the 0.05 degree grid, so the raw position and the rounded one differ.
    const gps = { lat: 51.4723, lon: -2.6049 };
    const served = host(canned(10));
    await mount(deps(served.fetch, { locate: async () => gps }));
    expect(served.forecasts()).toHaveLength(1);
    const params = new URL(served.forecasts()[0]!).searchParams;
    expect([params.get("latitude"), params.get("longitude")]).toEqual(["51.45", "-2.60"]);
    for (const url of served.requested) {
      expect(url).not.toContain("51.472");
      expect(url).not.toContain("2.604");
    }
  });
});
