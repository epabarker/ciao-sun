// The settings store: the person's saved defaults, in browser storage only
// (spec #27, "Client app"). It holds Wake time and max walk; saved places
// (#49) join `Settings` as another field with its own reader in FIELDS.
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
}

export const DEFAULT_SETTINGS: Readonly<Settings> = Object.freeze({ wakeTime: "07:00", maxWalkMin: 15 });

export type StorageLike = Pick<Storage, "getItem" | "setItem">;

const CLOCK = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Clamp a max walk to whole minutes in 1..MAX_WALK_CAP_MIN. */
export function clampMaxWalk(minutes: number): number {
  return Math.min(MAX_WALK_CAP_MIN, Math.max(1, Math.round(minutes)));
}

/** Per field: the stored value if it is valid, else undefined. */
const FIELDS: { [K in keyof Settings]: (value: unknown) => Settings[K] | undefined } = {
  wakeTime: (value) => (typeof value === "string" && CLOCK.test(value) ? value : undefined),
  maxWalkMin: (value) => (typeof value === "number" && Number.isFinite(value) ? clampMaxWalk(value) : undefined),
};

function sanitise(raw: unknown): Settings {
  const stored = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const out = { ...DEFAULT_SETTINGS } as Record<keyof Settings, unknown>;
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

  let current: Settings = { ...DEFAULT_SETTINGS };
  if (backing) {
    try {
      const text = backing.getItem(SETTINGS_KEY);
      current = sanitise(text === null ? {} : JSON.parse(text));
    } catch {
      current = { ...DEFAULT_SETTINGS };
    }
  }

  return {
    get persistent() {
      return backing !== null;
    },
    read: () => ({ ...current }),
    update(change) {
      current = sanitise({ ...current, ...change });
      try {
        backing?.setItem(SETTINGS_KEY, JSON.stringify(current));
      } catch {
        // Kept in memory for the session.
      }
      return { ...current };
    },
  };
}
