// The forecast adapter: the sky slot's category from Open-Meteo's UKMO
// forecast (spec #27, "Cloud category"). `ciao_sun.reference.cloud` is its
// reference, and both are held to fixtures/cloud/cases.json.
//
// It never throws and never waits long: offline, a failed or hung request,
// or a span the forecast does not cover gives "unavailable", and the sky
// slot falls back to manual entry. The span (the Morning window, or the last
// 3 h of the Evening window) is `cloudSpan` in `span.ts`.

import type { Sky } from "../contract";

export const FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
/** C below this is clear. */
export const CLEAR_BELOW_PCT = 25;
/** C at or above this is overcast; between the two, partly cloudy. */
export const OVERCAST_FROM_PCT = 80;
/** The request coordinate is rounded to 1/20 = 0.05 degrees: all of the position that leaves the phone. */
const CELLS_PER_DEG = 20;
/**
 * Open-Meteo's UKMO models reach "up to 8 days" (UKV 2 days, Global 7), so a
 * span ending later than this after now is not asked for. Nearer spans the
 * forecast does not reach are found from the data.
 */
const FORECAST_DAYS_MAX = 8;
const DEFAULT_TIMEOUT_MS = 8_000;
const MS_PER_HOUR = 3_600_000;
const MS_PER_DAY = 86_400_000;

/** The instants, in ms since the epoch, that C is averaged between. */
export interface CloudSpan {
  startMs: number;
  endMs: number;
}

/** The slice of the platform `fetch` the adapter uses; inject a fake in tests. */
export type FetchLike = (
  url: string,
  init?: { signal?: AbortSignal },
) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

export interface ForecastOptions {
  /** Defaults to the platform `fetch`. */
  fetch?: FetchLike;
  /** The clock `fetchedAtMs` and the horizon are read from. Defaults to `Date.now`. */
  now?: () => number;
  /** How long to wait for the response before giving up. */
  timeoutMs?: number;
}

export type UnavailableReason =
  /** fetch rejected: no network. */
  | "offline"
  /** No response within the timeout. */
  | "timed-out"
  /** A non-OK status, or a body that is not a forecast. */
  | "request-failed"
  /** The forecast does not cover the span (beyond the model's horizon). */
  | "past-horizon";

export type SkyForecast =
  | { status: "forecast"; sky: Sky; cloudCoverPct: number; fetchedAtMs: number }
  /** `fetchedAtMs` is set when a forecast came back but did not cover the span. */
  | { status: "unavailable"; reason: UnavailableReason; fetchedAtMs?: number };

/** Clear below 25 %, overcast from 80 %, partly cloudy between. */
export function cloudCategory(c: number): Sky {
  if (c < CLEAR_BELOW_PCT) return "clear";
  if (c < OVERCAST_FROM_PCT) return "partly";
  return "overcast";
}

/** The forecast's sky for the span at `place`. Resolves; never rejects. */
export async function forecastSky(
  place: { lat: number; lon: number },
  span: CloudSpan,
  options: ForecastOptions = {},
): Promise<SkyForecast> {
  try {
    const now = options.now ?? Date.now;
    if (span.endMs > now() + FORECAST_DAYS_MAX * MS_PER_DAY) {
      return { status: "unavailable", reason: "past-horizon" };
    }
    const fetch = options.fetch ?? ((url, init) => globalThis.fetch(url, init));
    const body = await withTimeout(
      (signal) => fetchJson(fetch, requestUrl(place, span), signal),
      options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    );
    if (body === "offline" || body === "timed-out" || body === "request-failed") {
      return { status: "unavailable", reason: body };
    }
    const fetchedAtMs = now();
    const hourly = hourlyCloudCover(body.value);
    if (!hourly) {
      return { status: "unavailable", reason: "request-failed" };
    }
    const c = meanCloudCover(hourly, span);
    if (c === null) {
      return { status: "unavailable", reason: "past-horizon", fetchedAtMs };
    }
    return { status: "forecast", sky: cloudCategory(c), cloudCoverPct: c, fetchedAtMs };
  } catch {
    return { status: "unavailable", reason: "request-failed" };
  }
}

/** "51.4723" -> "51.45": the coordinate as the request carries it. */
export function forecastCoordinate(x: number): string {
  return (Math.floor(x * CELLS_PER_DEG + 0.5) / CELLS_PER_DEG).toFixed(2);
}

function requestUrl(place: { lat: number; lon: number }, span: CloudSpan): string {
  // Hours are UTC instants (unixtime), so the dates asked for are the UTC
  // dates of the hours that bracket the span.
  const utcDate = (ms: number) => new Date(ms).toISOString().slice(0, 10);
  const params = new URLSearchParams({
    latitude: forecastCoordinate(place.lat),
    longitude: forecastCoordinate(place.lon),
    hourly: "cloud_cover",
    models: "ukmo_seamless",
    timeformat: "unixtime",
    timezone: "GMT",
    start_date: utcDate(Math.floor(span.startMs / MS_PER_HOUR) * MS_PER_HOUR),
    end_date: utcDate(Math.ceil(span.endMs / MS_PER_HOUR) * MS_PER_HOUR),
  });
  return `${FORECAST_URL}?${params}`;
}

type Fetched = { value: unknown } | "offline" | "request-failed";

async function fetchJson(fetch: FetchLike, url: string, signal: AbortSignal): Promise<Fetched> {
  let response;
  try {
    response = await fetch(url, { signal });
  } catch {
    return "offline";
  }
  if (!response.ok) return "request-failed";
  try {
    return { value: await response.json() };
  } catch {
    return "request-failed";
  }
}

async function withTimeout<T>(
  run: (signal: AbortSignal) => Promise<T>,
  timeoutMs: number,
): Promise<T | "timed-out"> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<"timed-out">((resolve) => {
    timer = setTimeout(() => {
      controller.abort();
      resolve("timed-out");
    }, timeoutMs);
  });
  try {
    return await Promise.race([run(controller.signal), timeout]);
  } finally {
    clearTimeout(timer);
  }
}

interface Hourly {
  /** Seconds since the epoch. */
  time: unknown[];
  cloud_cover: unknown[];
}

function hourlyCloudCover(body: unknown): Hourly | null {
  if (typeof body !== "object" || body === null) return null;
  const hourly = (body as { hourly?: unknown }).hourly;
  if (typeof hourly !== "object" || hourly === null) return null;
  const { time, cloud_cover } = hourly as { time?: unknown; cloud_cover?: unknown };
  if (!Array.isArray(time) || !Array.isArray(cloud_cover) || time.length !== cloud_cover.length) {
    return null;
  }
  return { time, cloud_cover };
}

const isNumber = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/**
 * C over the span: the time-weighted mean of cloud cover interpolated
 * linearly between the hours, or null if the hours do not cover the span (an
 * hour at or before its start, one at or after its end, and a number for
 * every hour between). The reference's expression, step for step.
 */
function meanCloudCover(hourly: Hourly, span: CloudSpan): number | null {
  const { time: t, cloud_cover: v } = hourly;
  const s = span.startMs / 1000;
  const e = span.endMs / 1000;
  let first = -1;
  for (let i = t.length - 1; i >= 0; i--) {
    const ti = t[i];
    if (isNumber(ti) && ti <= s) {
      first = i;
      break;
    }
  }
  const last = t.findIndex((tj) => isNumber(tj) && tj >= e);
  if (first < 0 || last < 0 || !(s < e)) return null;
  const times: number[] = [];
  const values: number[] = [];
  for (let k = first; k <= last; k++) {
    const tk = t[k];
    const vk = v[k];
    if (!isNumber(tk) || !isNumber(vk)) return null;
    if (times.length > 0 && tk <= times[times.length - 1]!) return null;
    times.push(tk);
    values.push(vk);
  }

  let area = 0;
  for (let k = 0; k + 1 < times.length; k++) {
    const t0 = times[k]!;
    const t1 = times[k + 1]!;
    const v0 = values[k]!;
    const v1 = values[k + 1]!;
    const a = Math.max(t0, s);
    const b = Math.min(t1, e);
    if (b <= a) continue;
    const va = v0 + ((v1 - v0) * (a - t0)) / (t1 - t0);
    const vb = v0 + ((v1 - v0) * (b - t0)) / (t1 - t0);
    area += ((b - a) * (va + vb)) / 2;
  }
  return area / (e - s);
}
