// The app: wires the release config, data loader, settings store, GPS and
// scorer to the answer screen. Every outside dependency is in AppDeps, so the
// tests run the whole screen over the synthetic build; `main.ts` passes the
// browser's.
//
// State flows one way: an event changes `state`, then `refresh()` asks the
// scorer (only when the query changed) and `draw()` re-renders the screen.

import { readAbout } from "./about/about";
import type { ReleaseConfig } from "./config/release";
import type { Answer, Query, Sky, WindowName } from "./contract";
import { type Build, DataUnavailableError, type FetchLike, openBuild } from "./loader/loader";
import { parseOrigin } from "./query/origin";
import { buildQuery, nextMorningDate } from "./query/query";
import { answer } from "./scorer/answer";
import { type SavedPlace, type SettingsStore, type StorageLike, clampMaxWalk, openSettings } from "./settings/store";
import { type Tile, UnsupportedFormatError } from "./tile/decode";
import { renderAbout } from "./ui/about-view";
import { h } from "./ui/dom";
import { renderPlaces } from "./ui/places";
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

  const state: SentenceState & { dateEdited: boolean; placesOpen: boolean; placeDraft: string } = {
    window,
    wakeTime: saved.wakeTime,
    savedWakeTime: saved.wakeTime,
    date: nextMorningDate(deps.now(), saved.wakeTime),
    dateEdited: false,
    sky: "clear",
    maxWalkMin: saved.maxWalkMin,
    origin: { kind: "locating" },
    places: saved.places,
    placesOpen: false,
    placeDraft: "",
  };
  let result: Result = { kind: "loading" };
  let build: Build | undefined;
  let pending: Promise<unknown> = Promise.resolve();
  let asked = 0;
  let aboutOpen = false;

  const track = (work: Promise<unknown>) => {
    pending = Promise.all([pending, work.catch(() => {})]);
  };

  const origin = (): { lat: number; lon: number } | undefined => {
    const slot = state.origin;
    if (slot.kind === "gps") return { lat: slot.lat, lon: slot.lon };
    if (slot.kind === "typed") return parseOrigin(slot.text);
    if (slot.kind === "place") return { lat: slot.place.lat, lon: slot.place.lon };
    return undefined;
  };

  const draw = () => {
    const places = renderPlaces(
      {
        places: state.places,
        open: state.placesOpen,
        canSave: state.origin.kind !== "place" && origin() !== undefined,
        draft: state.placeDraft,
        persistent: settings.persistent,
      },
      placeEvents,
    );
    renderScreen(root, {
      window,
      sentence: h("div", { class: "ask" }, renderSentence(state, events), places),
      result,
      onAbout: () => setAbout(true),
      about: aboutOpen ? renderAbout(readAbout(build?.manifest), () => setAbout(false)) : undefined,
    });
  };

  const setAbout = (open: boolean) => {
    aboutOpen = open;
    draw();
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

  const refresh = () => {
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
        () =>
          current() &&
          setOrigin({
            kind: "typed",
            text: "",
            reason: state.places.length
              ? "Location unavailable: pick a saved place or type a position."
              : "Location unavailable: type a position.",
          }),
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
    usePlace(id: string) {
      const place = state.places.find((p) => p.id === id);
      if (place) setOrigin({ kind: "place", place });
    },
  };

  // Saved places: only ever written to the settings store (#49).
  const savePlaces = (places: SavedPlace[]) => {
    state.places = settings.update({ places }).places;
  };
  const placeEvents = {
    togglePlaces() {
      state.placesOpen = !state.placesOpen;
      draw();
    },
    draftPlace(name: string) {
      state.placeDraft = name;
    },
    savePlace() {
      const at = state.origin.kind === "place" ? undefined : origin();
      if (!at) return;
      const id = String(Math.max(0, ...state.places.map((p) => Number(p.id) || 0)) + 1);
      const name = state.placeDraft.trim() || `Place ${id}`;
      savePlaces([...state.places, { id, name, lat: at.lat, lon: at.lon }]);
      state.placeDraft = "";
      // The origin is unchanged, so no new query: "here" now says its name.
      const place = state.places.find((p) => p.id === id);
      if (place) state.origin = { kind: "place", place };
      draw();
    },
    renamePlace(id: string, name: string) {
      savePlaces(state.places.map((p) => (p.id === id ? { ...p, name } : p)));
      const slot = state.origin;
      const renamed = state.places.find((p) => p.id === id);
      if (slot.kind === "place" && slot.place.id === id && renamed) state.origin = { kind: "place", place: renamed };
      draw();
    },
    deletePlace(id: string) {
      savePlaces(state.places.filter((p) => p.id !== id));
      if (state.origin.kind === "place" && state.origin.place.id === id) {
        events.useGps();
      } else {
        draw();
      }
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
