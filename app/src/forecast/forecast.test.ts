// The forecast adapter (#45), fed canned Open-Meteo responses through an
// injected fetch. The cases and their hand-worked categories are shared with
// the Python reference (tests/test_reference_cloud.py), so both languages give
// the same category for the same data.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Sky } from "../contract";
import { cloudCategory, forecastSky, type FetchLike } from "./forecast";

interface CloudCase {
  name: string;
  span: { start: string; end: string };
  response: unknown;
  category: Sky | null;
  meanCloudCover: number | null;
}

const shared = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../fixtures/cloud/cases.json", import.meta.url)), "utf8"),
) as {
  cases: CloudCase[];
  coordinates: { origin: { lat: number; lon: number }; request: { lat: string; lon: string } }[];
};

const BRISTOL = { lat: 51.4723, lon: -2.6049 };
const MORNING = { startMs: Date.parse("2026-12-21T08:13:00Z"), endMs: Date.parse("2026-12-21T10:00:00Z") };
const FETCHED_AT = Date.parse("2026-12-20T21:00:00Z");
const now = () => FETCHED_AT;

function respondWith(body: unknown, status = 200): FetchLike & { urls: string[] } {
  const urls: string[] = [];
  const fetch = async (url: string) => {
    urls.push(url);
    return { ok: status >= 200 && status < 300, status, json: async () => body };
  };
  return Object.assign(fetch, { urls });
}

function spanOf(c: CloudCase) {
  return { startMs: Date.parse(c.span.start), endMs: Date.parse(c.span.end) };
}

describe("the cloud category from a forecast", () => {
  it.each(shared.cases.map((c) => [c.name, c] as const))("%s", async (_name, c) => {
    const result = await forecastSky(BRISTOL, spanOf(c), { fetch: respondWith(c.response), now });
    if (c.category === null) {
      expect(result).toEqual({ status: "unavailable", reason: "past-horizon", fetchedAtMs: FETCHED_AT });
    } else {
      expect(result).toMatchObject({ status: "forecast", sky: c.category, fetchedAtMs: FETCHED_AT });
      expect(result.status === "forecast" && result.cloudCoverPct).toBeCloseTo(c.meanCloudCover!, 9);
    }
  });

  it.each([
    [0, "clear"],
    [24.99, "clear"],
    [25, "partly"],
    [79.99, "partly"],
    [80, "overcast"],
    [100, "overcast"],
  ] as const)("C = %s%% is %s", (c, sky) => {
    expect(cloudCategory(c)).toBe(sky);
  });
});

describe("the forecast request", () => {
  it.each(shared.coordinates.map((p) => [p.origin, p.request] as const))(
    "sends %o only as the 0.05 degree coordinate %o",
    async (origin, request) => {
      const fetch = respondWith(shared.cases[0]!.response);
      await forecastSky(origin, MORNING, { fetch, now });
      expect(fetch.urls).toHaveLength(1);
      const url = new URL(fetch.urls[0]!);
      expect(url.searchParams.get("latitude")).toBe(request.lat);
      expect(url.searchParams.get("longitude")).toBe(request.lon);
      // No more of the position than that leaves the phone.
      expect(fetch.urls[0]).not.toContain(String(origin.lat));
      expect(fetch.urls[0]).not.toContain(String(origin.lon));
      expect(fetch.urls[0]).not.toContain(String(origin.lat).slice(0, 6));
    },
  );

  it("asks Open-Meteo for UKMO hourly cloud cover as UTC instants over the span's UTC dates", async () => {
    const fetch = respondWith(shared.cases[0]!.response);
    const late = { startMs: Date.parse("2026-06-21T22:40:00Z"), endMs: Date.parse("2026-06-21T23:20:00Z") };
    await forecastSky(BRISTOL, late, { fetch, now: () => Date.parse("2026-06-21T12:00:00Z") });
    const url = new URL(fetch.urls[0]!);
    expect(url.origin + url.pathname).toBe("https://api.open-meteo.com/v1/forecast");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      latitude: "51.45",
      longitude: "-2.60",
      hourly: "cloud_cover",
      models: "ukmo_seamless",
      timeformat: "unixtime",
      timezone: "GMT",
      start_date: "2026-06-21",
      // 23:20 needs the 00:00 hour after it.
      end_date: "2026-06-22",
    });
  });
});

describe("falling back to manual entry", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("is unavailable offline, when fetch rejects", async () => {
    const fetch: FetchLike = async () => {
      throw new TypeError("Failed to fetch");
    };
    expect(await forecastSky(BRISTOL, MORNING, { fetch, now })).toEqual({ status: "unavailable", reason: "offline" });
  });

  it("is unavailable when fetch throws synchronously", async () => {
    const fetch: FetchLike = () => {
      throw new Error("no network stack");
    };
    expect(await forecastSky(BRISTOL, MORNING, { fetch, now })).toEqual({ status: "unavailable", reason: "offline" });
  });

  it("is unavailable when the request fails", async () => {
    const fetch = respondWith({ error: true, reason: "Parameter 'start_date' is out of allowed range" }, 400);
    expect(await forecastSky(BRISTOL, MORNING, { fetch, now })).toEqual({
      status: "unavailable",
      reason: "request-failed",
    });
  });

  it("is unavailable when the response is not JSON or not a forecast", async () => {
    const notJson: FetchLike = async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError("Unexpected token <");
      },
    });
    expect(await forecastSky(BRISTOL, MORNING, { fetch: notJson, now })).toEqual({
      status: "unavailable",
      reason: "request-failed",
    });
    for (const body of [null, {}, { hourly: { time: [1, 2], cloud_cover: [1] } }]) {
      expect(await forecastSky(BRISTOL, MORNING, { fetch: respondWith(body), now })).toEqual({
        status: "unavailable",
        reason: "request-failed",
      });
    }
  });

  it("is unavailable past the forecast horizon without a request", async () => {
    const fetch = respondWith(shared.cases[0]!.response);
    const later = { startMs: MORNING.startMs + 17 * 86_400_000, endMs: MORNING.endMs + 17 * 86_400_000 };
    expect(await forecastSky(BRISTOL, later, { fetch, now })).toEqual({ status: "unavailable", reason: "past-horizon" });
    expect(fetch.urls).toEqual([]);
  });

  it("is unavailable when the request hangs, after the timeout", async () => {
    vi.useFakeTimers();
    let aborted = false;
    const fetch: FetchLike = (_url, init) => {
      init?.signal?.addEventListener("abort", () => {
        aborted = true;
      });
      return new Promise(() => {});
    };
    const result = forecastSky(BRISTOL, MORNING, { fetch, now, timeoutMs: 5_000 });
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await result).toEqual({ status: "unavailable", reason: "timed-out" });
    expect(aborted).toBe(true);
  });
});
