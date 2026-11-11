// The app: wires the release config, data loader, settings store, GPS and
// scorer to the answer screen. Every outside dependency is in AppDeps, so the
// tests run the whole screen over the synthetic build; `main.ts` passes the
// browser's.
//
// State flows one way: an event changes `state`, then `refresh()` asks the
// scorer (only when the query changed) and `draw()` re-renders the screen.

import type { ReleaseConfig } from "./config/release";
import type { Answer, Query, Sky, WindowName } from "./contract";
import { type Build, DataUnavailableError, type FetchLike, openBuild } from "./loader/loader";
import { parseOrigin } from "./query/origin";
import { buildQuery, nextMorningDate } from "./query/query";
import { answer } from "./scorer/answer";
import { type SettingsStore, type StorageLike, clampMaxWalk, openSettings } from "./settings/store";
import { type Tile, UnsupportedFormatError } from "./tile/decode";
import { type Result, renderScreen } from "./ui/screen";
import { type OriginSlot, type SentenceState, renderSentence } from "./ui/sentence";

export interface AppDeps {
  config: ReleaseConfig;
  fetch: FetchLike;
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

/** The scorer, given the build: the one place a query becomes an Answer. */
function score(query: Query, tiles: readonly Tile[], _build: Build): Answer {
  return answer(query, tiles); // #44: pass _build.manifest.coverage as the third argument, and drop the loader's not-covered short-circuit in `ask`.
}

const NOT_COVERED: Answer = { status: "not-covered", spots: [] };

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
    const at = origin();
    if (!build) {
      return; // Still opening, or refused: the result says which.
    }
    if (!at) {
      result = state.origin.kind === "locating" ? { kind: "loading" } : { kind: "need-origin" };
      return;
    }
    const query = buildQuery({ ...state, origin: at }, deps.now(), window);
    const ticket = ++asked;
    result = { kind: "loading" };
    draw();
    let next: Result;
    try {
      const area = await build.area(query.origin);
      next = area.covered ? { kind: "answer", answer: score(query, area.tiles, build) } : { kind: "answer", answer: NOT_COVERED };
    } catch (error) {
      next = failure(error);
    }
    if (ticket === asked) {
      result = next;
    }
  };

  const refresh = () => {
    const work = ask().then(draw);
    track(work);
    draw();
  };

  const setOrigin = (slot: OriginSlot) => {
    state.origin = slot;
    refresh();
  };

  const locate = () => {
    state.origin = { kind: "locating" };
    track(
      deps.locate().then(
        (at) => setOrigin({ kind: "gps", lat: at.lat, lon: at.lon }),
        () => setOrigin({ kind: "typed", text: "", reason: "Location unavailable: type a position." }),
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
