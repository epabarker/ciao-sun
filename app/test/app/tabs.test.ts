// @vitest-environment happy-dom
//
// The Morning and Evening tabs over the committed synthetic build (#48): the
// tab the app opens on, the Evening tab's wording, axis and copy, and the
// "Morning window has ended" note's way on.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type AppDeps, startApp } from "../../src/app";
import type { FetchLike } from "../../src/loader/loader";
import { SETTINGS_KEY } from "../../src/settings/store";

const SYNTHETIC = `${resolve(import.meta.dirname, "../../../fixtures/synthetic")}/`;
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };
// The winter solstice fixture's origin; Nominal sunset there on 21 Dec is
// 16:04 GMT (the Python reference's sun_track).
const ORIGIN = { lat: 51.4589122, lon: -2.6051884 };

const fetch: FetchLike = async (url) => {
  try {
    return new Response(readFileSync(SYNTHETIC + url.slice(PIN.dataBase.length)));
  } catch {
    return new Response("", { status: 404 });
  }
};

function deps(nowIso: string): AppDeps {
  const items = new Map([[SETTINGS_KEY, JSON.stringify({ wakeTime: "07:30", maxWalkMin: 15 })]]);
  return {
    config: PIN,
    fetch,
    storage: () => ({ getItem: (k: string) => items.get(k) ?? null, setItem: (k: string, v: string) => void items.set(k, v) }),
    now: () => Date.parse(nowIso),
    locate: async () => ORIGIN,
  };
}

async function mount(nowIso: string) {
  const root = document.createElement("div");
  const app = startApp(root, deps(nowIso));
  await app.idle();
  return { root, app };
}

const selected = (root: HTMLElement) => root.querySelector("[role=tab][aria-selected=true]")?.getAttribute("data-tab");
const dateSlot = (root: HTMLElement) => (root.querySelector("[name=date]") as HTMLInputElement).value;

function change(el: Element | null, value: string) {
  const input = el as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("the tab the app opens on", () => {
  it("is today's Morning before the Morning window", async () => {
    const { root } = await mount("2026-12-21T06:00:00Z");
    expect([selected(root), dateSlot(root)]).toEqual(["morning", "2026-12-21"]);
  });

  it("is today's Evening during the day", async () => {
    const { root } = await mount("2026-12-21T12:00:00Z");
    expect([selected(root), dateSlot(root)]).toEqual(["evening", "2026-12-21"]);
  });

  it("is tomorrow's Morning after Nominal sunset", async () => {
    const { root } = await mount("2026-12-21T16:30:00Z");
    expect([selected(root), dateSlot(root)]).toEqual(["morning", "2026-12-22"]);
  });
});

describe("the Evening tab", () => {
  it("words the sentence for the evening", async () => {
    const { root } = await mount("2026-12-21T12:00:00Z");
    expect(root.querySelector("[data-field=sentence]")?.textContent).toMatch(/evening sky looks/);
  });

  it("draws its timeline over the last 3 h before Nominal sunset", async () => {
    const { root } = await mount("2026-12-21T12:00:00Z");
    const ticks = [...root.querySelectorAll("[data-field=axis] .tick")].map((tick) => tick.textContent);
    expect([ticks[0], ticks.at(-1)]).toEqual(["13:04", "16:04"]);
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it('says "After sunset, dim the lights." and the Morning tab does not', async () => {
    const { root, app } = await mount("2026-12-21T12:00:00Z");
    expect(root.querySelector("[data-field=dim-lights]")?.textContent).toBe("After sunset, dim the lights.");
    (root.querySelector("[data-tab=morning]") as HTMLButtonElement).click();
    await app.idle();
    expect(selected(root)).toBe("morning");
    expect(root.querySelector("[data-field=dim-lights]")).toBeNull();
  });

  it("has no lamp", async () => {
    const { root } = await mount("2026-12-21T12:00:00Z");
    expect(root.querySelector("[data-field=lamp]")).toBeNull();
  });
});

describe("the safety copy", () => {
  it("is on both tabs: no sunglasses, no brimmed hat, never stare at the sun", async () => {
    const { root, app } = await mount("2026-12-21T12:00:00Z");
    const safety = () => root.querySelector("[data-field=safety]")?.textContent ?? "";
    for (const tab of ["evening", "morning"]) {
      (root.querySelector(`[data-tab=${tab}]`) as HTMLButtonElement).click();
      await app.idle();
      expect(safety()).toMatch(/sunglasses/);
      expect(safety()).toMatch(/brimmed hat/);
      expect(safety()).toMatch(/never stare at the sun/i);
    }
  });
});

describe("switching tabs", () => {
  it("plans each tab's next window: the Morning tab after its window is tomorrow's", async () => {
    const { root, app } = await mount("2026-12-21T12:00:00Z");
    (root.querySelector("[data-tab=morning]") as HTMLButtonElement).click();
    await app.idle();
    expect(dateSlot(root)).toBe("2026-12-22");
    (root.querySelector("[data-tab=evening]") as HTMLButtonElement).click();
    await app.idle();
    expect(dateSlot(root)).toBe("2026-12-21");
  });
});

describe("a Morning window already over", () => {
  async function overMorning() {
    const mounted = await mount("2026-12-21T12:00:00Z");
    (mounted.root.querySelector("[data-tab=morning]") as HTMLButtonElement).click();
    await mounted.app.idle();
    change(mounted.root.querySelector("[name=date]"), "2026-12-21");
    await mounted.app.idle();
    return mounted;
  }

  it('says "Morning window has ended", without lamp advice', async () => {
    const { root } = await overMorning();
    expect(root.querySelector("[data-status]")?.getAttribute("data-status")).toBe("lamp-only");
    expect(root.querySelector("[data-field=window-over]")?.textContent).toBe("Morning window has ended.");
    expect(root.querySelector("[data-field=lamp]")).toBeNull();
  });

  it("leads to tomorrow's Morning", async () => {
    const { root, app } = await overMorning();
    (root.querySelector("[data-action=plan-tomorrow-morning]") as HTMLButtonElement).click();
    await app.idle();
    expect([selected(root), dateSlot(root)]).toEqual(["morning", "2026-12-22"]);
    expect(root.querySelectorAll("[data-spot]").length).toBeGreaterThan(0);
  });

  it("leads to the Evening tab", async () => {
    const { root, app } = await overMorning();
    (root.querySelector("[data-action=show-evening]") as HTMLButtonElement).click();
    await app.idle();
    expect([selected(root), dateSlot(root)]).toEqual(["evening", "2026-12-21"]);
  });
});
