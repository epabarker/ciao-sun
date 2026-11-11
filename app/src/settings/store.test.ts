import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS, SETTINGS_KEY, openSettings } from "./store";

/** A browser Storage, kept in a Map so a "reload" can open it again. */
class MemoryStorage implements Pick<Storage, "getItem" | "setItem" | "removeItem"> {
  readonly items = new Map<string, string>();
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.items.set(key, value);
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
}

describe("settings store", () => {
  it("starts from Wake time 07:00 and a 15 min max walk", () => {
    expect(openSettings(() => new MemoryStorage()).read()).toEqual({ wakeTime: "07:00", maxWalkMin: 15, places: [] });
    expect(DEFAULT_SETTINGS).toEqual({ wakeTime: "07:00", maxWalkMin: 15, places: [] });
  });

  it("keeps Wake time and max walk across a reload", () => {
    const storage = new MemoryStorage();
    openSettings(() => storage).update({ wakeTime: "06:15" });
    openSettings(() => storage).update({ maxWalkMin: 20 });
    expect(openSettings(() => storage).read()).toEqual({ wakeTime: "06:15", maxWalkMin: 20, places: [] });
  });

  it("caps max walk at 20 min and keeps it at least 1 min", () => {
    const settings = openSettings(() => new MemoryStorage());
    expect(settings.update({ maxWalkMin: 45 }).maxWalkMin).toBe(20);
    expect(settings.update({ maxWalkMin: 0 }).maxWalkMin).toBe(1);
  });

  it("ignores a stored value it can't read, field by field", () => {
    const storage = new MemoryStorage();
    storage.setItem(SETTINGS_KEY, JSON.stringify({ wakeTime: "7 o'clock", maxWalkMin: 10 }));
    expect(openSettings(() => storage).read()).toEqual({ wakeTime: "07:00", maxWalkMin: 10, places: [] });
    storage.setItem(SETTINGS_KEY, "{not json");
    expect(openSettings(() => storage).read()).toEqual(DEFAULT_SETTINGS);
  });

  it("works for the session when browser storage is unavailable", () => {
    const settings = openSettings(() => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    });
    expect(settings.read()).toEqual(DEFAULT_SETTINGS);
    expect(settings.update({ wakeTime: "08:00" })).toEqual({ wakeTime: "08:00", maxWalkMin: 15, places: [] });
    expect(settings.read().wakeTime).toBe("08:00");
    expect(settings.persistent).toBe(false);
  });

  it("keeps saved places across a reload", () => {
    const storage = new MemoryStorage();
    const home = { id: "1", name: "Home", lat: 51.4589, lon: -2.6052 };
    openSettings(() => storage).update({ places: [home] });
    expect(openSettings(() => storage).read().places).toEqual([home]);
  });

  it("drops a stored place it can't read and keeps the rest", () => {
    const storage = new MemoryStorage();
    const home = { id: "1", name: "Home", lat: 51.4589, lon: -2.6052 };
    storage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        places: [home, { id: "2", name: "Nowhere", lat: 95, lon: 0 }, { id: "3", lat: 51, lon: -2 }, "junk", { ...home }],
      }),
    );
    // Out of range, unnamed and junk entries go; a repeated id keeps its first place.
    expect(openSettings(() => storage).read().places).toEqual([home]);
    storage.setItem(SETTINGS_KEY, JSON.stringify({ places: "Home" }));
    expect(openSettings(() => storage).read().places).toEqual([]);
  });

  it("works for the session when storage refuses a write", () => {
    const full = new MemoryStorage();
    full.setItem = () => {
      throw new DOMException("quota", "QuotaExceededError");
    };
    const settings = openSettings(() => full);
    expect(settings.update({ maxWalkMin: 5 }).maxWalkMin).toBe(5);
    expect(settings.read().maxWalkMin).toBe(5);
  });
});
