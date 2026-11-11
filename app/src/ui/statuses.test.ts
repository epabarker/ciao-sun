// @vitest-environment happy-dom
//
// The non-ranked statuses and the lamp notice, rendered from given Answer
// objects (spec #27, "Testing Decisions / UI"; #48). Every number on screen is
// an Answer field; the Query is read only for its date and `now`.

import { describe, expect, it, vi } from "vitest";

import type { Answer, Query, Spot } from "../contract";
import { type AnswerContext, renderAnswer } from "./answer-view";

// A winter Evening: Nominal sunset 16:31, so the axis is 13:31-16:31, and the
// window starts at 14:00, before which nothing is drawn. One minute is 1/1.8 %.
const evening = {
  start: "2027-01-15T14:00:00+00:00",
  end: "2027-01-15T16:31:00+00:00",
  axisStart: "2027-01-15T13:31:00+00:00",
  axisEnd: "2027-01-15T16:31:00+00:00",
};

function spot(overrides: Partial<Spot>): Spot {
  return {
    candidateId: "ST5873/32",
    name: "East Street",
    lat: 51.4589203,
    lon: -2.6036053,
    walkMetres: 160,
    walkMin: 2,
    leaveBy: "2027-01-15T14:00:00+00:00",
    sunIntervals: [{ start: "2027-01-15T14:00:00+00:00", end: "2027-01-15T15:58:00+00:00" }],
    lowSunIntervals: [{ start: "2027-01-15T14:00:00+00:00", end: "2027-01-15T15:58:00+00:00" }],
    sunMinutes: 118,
    lowSunMinutes: 118,
    skyOpenness: 0.999,
    targetMet: true,
    lastSun: "2027-01-15T15:57:00+00:00",
    ...overrides,
  };
}

const overcast: Answer = {
  status: "fallback",
  window: evening,
  nominalSunrise: "2027-01-15T08:09:00+00:00",
  nominalSunset: "2027-01-15T16:31:00+00:00",
  solarNoon: "2027-01-15T12:20:00+00:00",
  durationTargetMin: 30,
  spots: [
    spot({ stayMin: 28 }),
    spot({ candidateId: "ST5773/26", name: "West Row", walkMetres: 50, walkMin: 0.625, stayMin: 30 }),
  ],
};

function render(answer: Answer, context?: AnswerContext): HTMLElement {
  const root = document.createElement("div");
  root.append(renderAnswer(answer, context));
  return root;
}

const percent = (value: string) => Number.parseFloat(value);

function segments(row: Element, kind: string): [number, number][] {
  return [...row.querySelectorAll(`[data-segment="${kind}"]`)].map((el) => {
    const style = (el as HTMLElement).style;
    return [percent(style.left), percent(style.width)];
  });
}

const text = (root: Element, field: string) => root.querySelector(`[data-field=${field}]`)?.textContent;

describe("fallback", () => {
  it('says "open sky still counts, aim for N min outside" with the Duration target', () => {
    const root = render(overcast);
    expect(root.querySelector("[data-status]")?.getAttribute("data-status")).toBe("fallback");
    expect(text(root, "fallback")).toBe("Open sky still counts, aim for 30 min outside.");
  });

  it('lists the nearest spots in the Answer\'s order, each with "stay N min" in place of a target badge', () => {
    const rows = [...render(overcast).querySelectorAll("[data-spot]")];
    expect(rows.map((row) => row.getAttribute("data-spot"))).toEqual(["ST5873/32", "ST5773/26"]);
    expect(rows.map((row) => text(row, "name"))).toEqual(["East Street", "West Row"]);
    expect(rows.map((row) => text(row, "leave-by"))).toEqual(["Leave 14:00", "Leave 14:00"]);
    expect(rows.map((row) => text(row, "stay"))).toEqual(["Stay 28 min", "Stay 30 min"]);
    expect(rows.map((row) => row.querySelector("[data-field=target]"))).toEqual([null, null]);
  });

  it('draws the "stay N min" block on the bar, from arrival for stayMin', () => {
    const [first] = [...render(overcast).querySelectorAll("[data-spot]")];
    // Leave 14:00 is 29 min in: 16.1111 %; the 2 min walk ends at 17.2222 %,
    // and the 28 min stay is 15.5556 % from there.
    expect(segments(first!, "walk")).toEqual([[16.1111, 1.1111]]);
    expect(segments(first!, "stay")).toEqual([[17.2222, 15.5556]]);
  });

  it("says the walk alone meets the target when the stay is 0", () => {
    const row = render({ ...overcast, spots: [spot({ walkMin: 11.25, stayMin: 0 })] }).querySelector("[data-spot]")!;
    expect(text(row, "stay")).toBe("The walk alone meets the target");
    expect(segments(row, "stay")).toEqual([]);
  });

  it("names the nearest spot with sun beyond max walk when the Answer has one", () => {
    const beyond = spot({
      candidateId: "ST5873/5",
      name: "Sunny Field",
      walkMin: 12.5,
      leaveBy: "2027-01-15T15:20:00+00:00",
      sunMinutes: 104,
      targetMet: true,
    });
    const root = render({ ...overcast, durationTargetMin: 10, nearestSunBeyondLimit: beyond });
    const section = root.querySelector("[data-field=beyond]")!;
    expect(section.textContent).toContain("Sun beyond your max walk");
    expect(text(section, "name")).toBe("Sunny Field");
    expect(text(section, "walk")).toBe("13 min walk");
    expect(text(section, "leave-by")).toBe("Leave 15:20");
    expect(text(section, "target")).toBe("10 min target met");
    expect(section.querySelector("[data-field=stay]")).toBeNull();
    // It is not one of the numbered fallback spots.
    expect(root.querySelectorAll("ol [data-spot]")).toHaveLength(2);
    expect(section.querySelector("[data-field=rank]")).toBeNull();
  });

  it("names none when the Answer has none", () => {
    expect(render(overcast).querySelector("[data-field=beyond]")).toBeNull();
  });
});

describe("an evening leave-by before the axis", () => {
  // The Evening axis is always the last 3 h before Nominal sunset, so a
  // departure for a long sunny stretch can fall before it.
  const early = {
    ...overcast,
    status: "ranked" as const,
    spots: [spot({ leaveBy: "2027-01-15T13:20:00+00:00", walkMin: 6 })],
  };

  it("is marked as off the axis at its start, and its time is still given", () => {
    const row = render(early).querySelector("[data-spot]")!;
    const line = row.querySelector("[data-segment=leave-by]") as HTMLElement;
    expect(percent(line.style.left)).toBe(0);
    expect(line.getAttribute("data-off-axis")).toBe("before");
    expect(text(row, "leave-by")).toBe("Leave 13:20");
  });

  it("draws none of a walk that is over before the axis starts", () => {
    const row = render(early).querySelector("[data-spot]")!;
    expect(segments(row, "walk")).toEqual([]);
  });

  it("leaves a leave-by on the axis unmarked", () => {
    const line = render(overcast).querySelector("[data-segment=leave-by]")!;
    expect(line.hasAttribute("data-off-axis")).toBe(false);
  });
});

describe("the evening axis", () => {
  it("spans the last 3 h before Nominal sunset", () => {
    const axis = render(overcast).querySelector("[data-field=axis]")!;
    const ticks = [...axis.children].map((tick) => tick.textContent);
    expect(ticks[0]).toBe("13:31");
    expect(ticks.at(-1)).toBe("16:31");
  });
});

// A December morning: Wake time 07:00, Nominal sunrise 08:13.
const morningQuery: Query = {
  window: "morning",
  date: "2026-12-21",
  wakeTime: "07:00",
  origin: { lat: 51.4589084, lon: -2.6059081 },
  maxWalkMin: 15,
  sky: "clear",
};
const morningWindow = {
  start: "2026-12-21T08:13:00+00:00",
  end: "2026-12-21T10:00:00+00:00",
  axisStart: "2026-12-21T07:00:00+00:00",
  axisEnd: "2026-12-21T10:00:00+00:00",
};

describe("the lamp notice", () => {
  const lampRanked: Answer = {
    status: "ranked",
    window: morningWindow,
    durationTargetMin: 10,
    lamp: true,
    spots: [spot({ leaveBy: "2026-12-21T08:30:00+00:00", sunIntervals: [], lowSunIntervals: [] })],
  };

  it("suggests the lamp above a ranked Morning list when the Answer says lamp", () => {
    const root = render(lampRanked, { query: morningQuery });
    expect(text(root, "lamp")).toBe(LAMP_TEXT);
    expect(root.querySelectorAll("[data-spot]")).toHaveLength(1);
  });

  it("suggests the lamp on a Morning fallback too", () => {
    const root = render({ ...lampRanked, status: "fallback", spots: [spot({ stayMin: 8 })] });
    expect(text(root, "lamp")).toBe(LAMP_TEXT);
  });

  it("is absent when the Answer says no lamp, or has no lamp at all, as in the evening", () => {
    expect(render({ ...lampRanked, lamp: false }).querySelector("[data-field=lamp]")).toBeNull();
    expect(render(overcast).querySelector("[data-field=lamp]")).toBeNull();
  });
});

const LAMP_TEXT = "Sunrise is more than an hour after you wake: switch on a bright lamp when you get up.";

describe("lamp-only", () => {
  // Wake time 04:00 on a December morning: the window ends at 07:00, before
  // Nominal sunrise at 08:13, so it holds no daylight.
  const dark: Answer = { status: "lamp-only", lamp: true, nextOutdoorLight: "2026-12-21T08:13:00+00:00", spots: [] };
  const darkQuery: Query = { ...morningQuery, wakeTime: "04:00", now: "2026-12-21T04:30:00+00:00" };

  it("for a morning with no daylight, gives only the lamp message and when outdoor light is next available", () => {
    const root = render(dark, { query: darkQuery });
    expect(root.querySelector("[data-status]")?.getAttribute("data-status")).toBe("lamp-only");
    expect(text(root, "lamp-only")).toBe("No daylight in your Morning window.");
    expect(text(root, "lamp")).toBe("Switch on a bright lamp when you get up.");
    expect(text(root, "next-light")).toBe("Outdoor light is next available at 08:13.");
    expect(root.querySelectorAll("[data-spot]")).toHaveLength(0);
    expect(root.querySelector("[data-field=window-over]")).toBeNull();
  });

  it("names the day of the next outdoor light when it is not the query's date", () => {
    const root = render({ ...dark, nextOutdoorLight: "2026-12-22T08:14:00+00:00" }, { query: { ...darkQuery, now: undefined } });
    expect(text(root, "next-light")).toBe("Outdoor light is next available at 08:14 on Tue 22 Dec.");
  });

  describe("once now is past the Morning window", () => {
    // Wake time 07:00 and now 11:00: the window 08:13-10:00 had daylight, but it is over.
    const over: Answer = { status: "lamp-only", lamp: true, nextOutdoorLight: "2026-12-21T11:00:00+00:00", spots: [] };
    const overQuery: Query = { ...morningQuery, now: "2026-12-21T11:00:00+00:00" };

    it('says "Morning window has ended", with no lamp advice', () => {
      const root = render(over, { query: overQuery });
      expect(text(root, "window-over")).toBe("Morning window has ended.");
      expect(root.querySelector("[data-field=lamp]")).toBeNull();
      expect(root.textContent).not.toMatch(/lamp/i);
    });

    it("points to tomorrow's Morning and to the Evening tab", () => {
      const actions = { planTomorrowMorning: vi.fn(), showEvening: vi.fn() };
      const root = render(over, { query: overQuery, actions });
      (root.querySelector("[data-action=plan-tomorrow-morning]") as HTMLButtonElement).click();
      (root.querySelector("[data-action=show-evening]") as HTMLButtonElement).click();
      expect(actions.planTomorrowMorning).toHaveBeenCalledOnce();
      expect(actions.showEvening).toHaveBeenCalledOnce();
    });

    it("says so whatever the lamp rule gave, and also when the morning had no daylight either", () => {
      expect(text(render({ ...over, lamp: false }, { query: overQuery }), "window-over")).toBe(
        "Morning window has ended.",
      );
      const darkAndOver = { ...darkQuery, now: "2026-12-21T09:00:00+00:00" };
      expect(text(render(dark, { query: darkAndOver }), "window-over")).toBe("Morning window has ended.");
    });
  });
});

describe("no Evening window", () => {
  const none: Answer = {
    status: "no-evening-window",
    nominalSunrise: "2026-12-21T08:13:00+00:00",
    nominalSunset: "2026-12-21T16:04:00+00:00",
    solarNoon: "2026-12-21T12:08:00+00:00",
    spots: [],
  };
  const late: Query = { ...morningQuery, window: "evening", wakeTime: "11:00", now: "2026-12-21T09:00:00+00:00" };

  it("says there is no Evening window today, and when the sun sets", () => {
    const root = render(none, { query: late });
    expect(root.querySelector("[data-status]")?.getAttribute("data-status")).toBe("no-evening-window");
    expect(text(root, "no-evening-window")).toBe("No Evening window today.");
    expect(root.textContent).toContain("Sunset is at 16:04");
    expect(root.querySelectorAll("[data-spot]")).toHaveLength(0);
  });

  it("says the Evening window has ended when now is already past Nominal sunset, and leads to tomorrow's Morning", () => {
    const actions = { planTomorrowMorning: vi.fn(), showEvening: vi.fn() };
    const afterSunset = { ...late, wakeTime: "07:00", now: "2026-12-21T16:05:00+00:00" };
    const root = render(none, { query: afterSunset, actions });
    expect(text(root, "no-evening-window")).toBe("Evening window has ended.");
    expect(root.textContent).toContain("Sunset was at 16:04");
    expect(root.textContent).not.toContain("6 h after you wake");
    (root.querySelector("[data-action=plan-tomorrow-morning]") as HTMLButtonElement).click();
    expect(actions.planTomorrowMorning).toHaveBeenCalledOnce();
  });

  it("names the day when the query plans another one", () => {
    const root = render(none, { query: { ...late, now: undefined } });
    expect(text(root, "no-evening-window")).toBe("No Evening window on Mon 21 Dec.");
  });
});
