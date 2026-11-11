// The settings store: the person's saved defaults, in browser storage only
// (spec #27, "Client app"). It holds Wake time, max walk and saved places;
// each is a field of `Settings` with its own reader in FIELDS. Saved places
// live only here, on the phone (user story 11): nothing sends them anywhere.
//
// Storage is wrapped so the app works without it: a storage accessor that
// throws (Safari's private mode, a blocked origin), a read that throws or
// returns junk, or a write that throws (quota) all fall back to the values held
// in memory for the session. Everything is one JSON object under SETTINGS_KEY.

import { MAX_WALK_CAP_MIN } from "../contract";

export const SETTINGS_KEY = "ciao-sun-settings";

export interface Settings {
  /** Saved default Wake time, local "HH:MM". */
  wakeTime: string;
  /** Saved max walk, whole minutes, 1 to MAX_WALK_CAP_MIN. */
  maxWalkMin: number;
  /** Saved places, in the order they were saved. */
  places: SavedPlace[];
}

/** A place the person saved, to use as the query origin. */
export interface SavedPlace {
  /** Stable within this phone's settings; never shown. */
  id: string;
  /** The person's name for it, non-empty. */
  name: string;
  lat: number;
  lon: number;
}

export const DEFAULT_SETTINGS: Readonly<Settings> = Object.freeze({
  wakeTime: "07:00",
  maxWalkMin: 15,
  places: Object.freeze([]) as unknown as SavedPlace[],
});

export type StorageLike = Pick<Storage, "getItem" | "setItem">;

const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Clamp a max walk to whole minutes in 1..MAX_WALK_CAP_MIN. */
export function clampMaxWalk(minutes: number): number {
  return Math.min(MAX_WALK_CAP_MIN, Math.max(1, Math.round(minutes)));
}

function readPlace(value: unknown): SavedPlace | undefined {
  if (!value || typeof value !== "object") return undefined;
  const { id, name, lat, lon } = value as Record<string, unknown>;
  if (typeof id !== "string" || !id || typeof name !== "string" || !name.trim()) return undefined;
  if (typeof lat !== "number" || typeof lon !== "number" || !(Math.abs(lat) <= 90) || !(Math.abs(lon) <= 180)) {
    return undefined;
  }
  return { id, name: name.trim(), lat, lon };
}

function readPlaces(value: unknown): SavedPlace[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const places: SavedPlace[] = [];
  for (const entry of value) {
    const place = readPlace(entry);
    if (place && !places.some((p) => p.id === place.id)) places.push(place);
  }
  return places;
}

/** Per field: the stored value if it is valid, else undefined. */
const FIELDS: { [K in keyof Settings]: (value: unknown) => Settings[K] | undefined } = {
  wakeTime: (value) => (typeof value === "string" && CLOCK.test(value) ? value : undefined),
  maxWalkMin: (value) => (typeof value === "number" && Number.isFinite(value) ? clampMaxWalk(value) : undefined),
  places: readPlaces,
};

function sanitise(raw: unknown): Settings {
  const stored = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const out = { ...DEFAULT_SETTINGS, places: [] } as Record<keyof Settings, unknown>;
  for (const key of Object.keys(FIELDS) as (keyof Settings)[]) {
    const value = FIELDS[key](stored[key]);
    if (value !== undefined) {
      out[key] = value;
    }
  }
  return out as unknown as Settings;
}

export interface SettingsStore {
  read(): Settings;
  /** Merge a change, save it if storage allows, and return the new settings. */
  update(change: Partial<Settings>): Settings;
  /** Whether the settings will outlive this page. */
  readonly persistent: boolean;
}

/**
 * Open the settings over a storage accessor, `() => window.localStorage` in
 * the app. The accessor is called inside a try, since merely reading
 * `localStorage` throws where storage is blocked.
 */
export function openSettings(storage: () => StorageLike | null | undefined): SettingsStore {
  let backing: StorageLike | null = null;
  try {
    backing = storage() ?? null;
  } catch {
    backing = null;
  }

  let current: Settings = sanitise({});
  if (backing) {
    try {
      const text = backing.getItem(SETTINGS_KEY);
      current = sanitise(text === null ? {} : JSON.parse(text));
    } catch {
      current = sanitise({});
    }
  }

  return {
    get persistent() {
      return backing !== null;
    },
    read: () => copy(current),
    update(change) {
      current = sanitise({ ...current, ...change });
      try {
        backing?.setItem(SETTINGS_KEY, JSON.stringify(current));
      } catch {
        // Kept in memory for the session.
      }
      return copy(current);
    },
  };
}

function copy(settings: Settings): Settings {
  return { ...settings, places: settings.places.map((place) => ({ ...place })) };
}
