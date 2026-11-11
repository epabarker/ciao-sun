// The app: wires the release config, data loader, settings store, GPS and
// scorer to the answer screen. Every outside dependency is in AppDeps, so the
// tests run the whole screen over the synthetic build; `main.ts` passes the
// browser's.
//
// State flows one way: an event changes `state`, then `refresh()` asks the
// scorer (only when the query changed) and `draw()` re-renders the screen.

import type { ReleaseConfig } from "./config/release";
import type { Answer, Query, Sky, WindowName } from "./contract";
import { forecastCoordinate, forecastSky } from "./forecast/forecast";
import { cloudSpan } from "./forecast/span";
import { type Build, DataUnavailableError, openBuild } from "./loader/loader";
import { parseOrigin } from "./query/origin";
import { buildQuery, nextMorningDate } from "./query/query";
import { answer } from "./scorer/answer";
import { type SettingsStore, type StorageLike, clampMaxWalk, openSettings } from "./settings/store";
import { type Tile, UnsupportedFormatError } from "./tile/decode";
import { type Result, renderScreen } from "./ui/screen";
import { type OriginSlot, type SentenceState, renderSentence } from "./ui/sentence";

export interface AppDeps {
  config: ReleaseConfig;
  /**
   * Every request: the data host's, and the forecast's to Open-Meteo, which
   * passes an abort signal for its timeout.
   */
  fetch: (url: string, init?: { signal?: AbortSignal }) => Promise<Response>;
  /** How long the forecast is waited for; the forecast adapter's default if unset. */
  forecastTimeoutMs?: number;
  /** What a relative `dataBase` resolves against: the page URL. */
  baseUrl?: string;
  /** The settings' browser storage; may throw where storage is blocked. */
  storage: () => StorageLike | null | undefined;
  /** The clock, in ms since the epoch. */
  now: () => number;
  /** The GPS position; rejects when it is denied or unavailable. */
  locate: () => Promise<{ lat: number; lon: number }>;
}

export interface App {
  /** Resolves once every pending load and answer has been drawn. */
  idle(): Promise<void>;
}

/**
 * The scorer, given the build: the one place a query becomes an Answer. The
 * scorer decides `not-covered` from the manifest's coverage polygon.
 */
function score(query: Query, tiles: readonly Tile[], build: Build): Answer {
  return answer(query, tiles, build.manifest.coverage);
}

export function startApp(root: HTMLElement, deps: AppDeps): App {
  const settings: SettingsStore = openSettings(deps.storage);
  const saved = settings.read();
  const window: WindowName = "morning";

  const state: SentenceState & { dateEdited: boolean } = {
    window,
    wakeTime: saved.wakeTime,
    savedWakeTime: saved.wakeTime,
    date: nextMorningDate(deps.now(), saved.wakeTime),
    dateEdited: false,
    sky: "clear",
    skySource: { kind: "unfilled" },
    maxWalkMin: saved.maxWalkMin,
    origin: { kind: "locating" },
  };
  let result: Result = { kind: "loading" };
  let build: Build | undefined;
  let pending: Promise<unknown> = Promise.resolve();
  let asked = 0;

  const track = (work: Promise<unknown>) => {
    pending = Promise.all([pending, work.catch(() => {})]);
  };

  const origin = (): { lat: number; lon: number } | undefined => {
    const slot = state.origin;
    if (slot.kind === "gps") return { lat: slot.lat, lon: slot.lon };
    if (slot.kind === "typed") return parseOrigin(slot.text);
    return undefined;
  };

  const draw = () => {
    renderScreen(root, { window, sentence: renderSentence(state, events), result });
  };

  const ask = async () => {
    // Every call supersedes the one before, even one that returns early.
    const ticket = ++asked;
    const at = origin();
    if (!build) {
      return; // Still opening, or refused: the result says which.
    }
    if (!at) {
      result = state.origin.kind === "locating" ? { kind: "loading" } : { kind: "need-origin" };
      return;
    }
    const query = buildQuery({ ...state, origin: at }, deps.now(), window);
    result = { kind: "loading" };
    draw();
    let next: Result;
    try {
      const area = await build.area(query.origin);
      // An origin outside the coverage needs no tiles: the scorer answers not-covered.
      next = { kind: "answer", answer: score(query, area.covered ? area.tiles : [], build) };
    } catch (error) {
      next = failure(error);
    }
    if (ticket === asked) {
      result = next;
    }
  };

  // The sky slot from the forecast. A request is keyed by what decides its
  // span and cell (window, date, Wake time and the 0.05 degree coordinate,
  // not `now`), and its answer is dropped if the key moved on or the slot was
  // set by hand meanwhile. A slot set by hand stays so until the window, date
  // or place changes. The query never waits for any of this.
  let forecastKey: string | undefined;
  let manualFor: { window: WindowName; date: string; place?: string } | undefined;
  const askForecast = () => {
    const at = origin();
    if (!at) return;
    const place = `${forecastCoordinate(at.lat)},${forecastCoordinate(at.lon)}`;
    if (state.skySource.kind === "manual" && manualFor?.window === window && manualFor.date === state.date) {
      manualFor.place ??= place;
      if (manualFor.place === place) return;
    }
    const key = `${window}|${state.date}|${state.wakeTime}|${place}`;
    if (key === forecastKey) return;
    forecastKey = key;
    const span = cloudSpan(buildQuery({ ...state, origin: at }, deps.now(), window));
    if (!span) {
      state.skySource = { kind: "unfilled" };
      return;
    }
    state.skySource = { kind: "pending" };
    track(
      forecastSky(at, span, { fetch: deps.fetch, now: deps.now, timeoutMs: deps.forecastTimeoutMs }).then((sky) => {
        if (key !== forecastKey || state.skySource.kind === "manual") return;
        if (sky.status === "forecast") {
          state.sky = sky.sky;
          state.skySource = { kind: "forecast", fetchedAtMs: sky.fetchedAtMs };
          refresh();
        } else {
          state.skySource = { kind: "unavailable", reason: sky.reason };
          draw();
        }
      }),
    );
  };

  const refresh = () => {
    askForecast();
    const work = ask().then(draw);
    track(work);
    draw();
  };

  const setOrigin = (slot: OriginSlot) => {
    state.origin = slot;
    refresh();
  };

  let locating = 0;
  const locate = () => {
    state.origin = { kind: "locating" };
    const id = ++locating;
    // A fix that arrives after the person typed a position, or asked again, is dropped.
    const current = () => id === locating && state.origin.kind === "locating";
    track(
      deps.locate().then(
        (at) => current() && setOrigin({ kind: "gps", lat: at.lat, lon: at.lon }),
        () => current() && setOrigin({ kind: "typed", text: "", reason: "Location unavailable: type a position." }),
      ),
    );
  };

  const events = {
    wakeTime(value: string) {
      state.wakeTime = value;
      if (!state.dateEdited) state.date = nextMorningDate(deps.now(), value);
      refresh();
    },
    saveWakeTime() {
      state.savedWakeTime = settings.update({ wakeTime: state.wakeTime }).wakeTime;
      draw();
    },
    date(value: string) {
      state.date = value;
      state.dateEdited = true;
      refresh();
    },
    sky(value: Sky) {
      state.sky = value;
      state.skySource = { kind: "manual" };
      manualFor = { window, date: state.date };
      refresh();
    },
    maxWalkMin(value: number) {
      state.maxWalkMin = settings.update({ maxWalkMin: clampMaxWalk(value) }).maxWalkMin;
      refresh();
    },
    typeOrigin(text: string) {
      setOrigin({ kind: "typed", text });
    },
    useGps() {
      locate();
      refresh();
    },
  };

  draw();
  locate();
  track(
    openBuild(deps.config, { fetch: deps.fetch, baseUrl: deps.baseUrl }).then(
      (opened) => {
        build = opened;
        refresh();
      },
      (error: unknown) => {
        result = failure(error);
        draw();
      },
    ),
  );

  return {
    async idle() {
      // Work started while waiting is waited for too.
      let seen: Promise<unknown>;
      do {
        seen = pending;
        await seen;
      } while (seen !== pending);
    },
  };
}

function failure(error: unknown): Result {
  if (error instanceof UnsupportedFormatError) {
    return { kind: "unreadable", format: error.format };
  }
  if (error instanceof DataUnavailableError) {
    return { kind: "unavailable" };
  }
  console.error(error);
  return { kind: "failed" };
}
