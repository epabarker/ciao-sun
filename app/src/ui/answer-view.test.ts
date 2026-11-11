// @vitest-environment happy-dom
//
// The answer view, driven by given Answer objects (spec #27, "Testing
// Decisions / UI"). The UI never recomputes scoring: every number on screen
// is an Answer field.

import { describe, expect, it } from "vitest";

import type { Answer, Spot } from "../contract";
import { renderAnswer } from "./answer-view";

const window_ = {
  start: "2026-09-23T07:00:00+01:00",
  end: "2026-09-23T10:00:00+01:00",
  axisStart: "2026-09-23T07:00:00+01:00",
  axisEnd: "2026-09-23T10:00:00+01:00",
};

function spot(overrides: Partial<Spot>): Spot {
  return {
    candidateId: "ST5873/1",
    name: "Ridge Road",
    lat: 51.4589,
    lon: -2.6052,
    walkMetres: 480,
    walkMin: 6,
    leaveBy: "2026-09-23T07:54:00+01:00",
    sunIntervals: [{ start: "2026-09-23T08:00:00+01:00", end: "2026-09-23T09:00:00+01:00" }],
    lowSunIntervals: [{ start: "2026-09-23T08:00:00+01:00", end: "2026-09-23T08:30:00+01:00" }],
    sunMinutes: 60,
    lowSunMinutes: 30,
    skyOpenness: 0.95,
    targetMet: true,
    ...overrides,
  };
}

// On the 180 min axis 07:00-10:00 one minute is 1/1.8 %.
const ranked: Answer = {
  status: "ranked",
  window: window_,
  durationTargetMin: 20,
  spots: [
    spot({}),
    spot({
      candidateId: "ST5773/40",
      name: "Brandon Hill",
      walkMetres: 1080,
      walkMin: 13.5,
      leaveBy: "2026-09-23T07:31:30+01:00",
      sunIntervals: [
        { start: "2026-09-23T07:45:00+01:00", end: "2026-09-23T07:54:00+01:00" },
        { start: "2026-09-23T08:24:00+01:00", end: "2026-09-23T10:00:00+01:00" },
      ],
      lowSunIntervals: [{ start: "2026-09-23T08:24:00+01:00", end: "2026-09-23T08:42:00+01:00" }],
      targetMet: false,
    }),
  ],
};

function render(answer: Answer): HTMLElement {
  const root = document.createElement("div");
  root.append(renderAnswer(answer));
  return root;
}

const percent = (value: string) => Number.parseFloat(value);

function segments(row: Element, kind: string): [number, number][] {
  return [...row.querySelectorAll(`[data-segment="${kind}"]`)].map((el) => {
    const style = (el as HTMLElement).style;
    return [percent(style.left), percent(style.width)];
  });
}

describe("ranked answer", () => {
  it("lists the spots in the Answer's order, numbered, with name, walk and leave-by", () => {
    const rows = [...render(ranked).querySelectorAll("[data-spot]")];
    expect(rows.map((row) => row.getAttribute("data-spot"))).toEqual(["ST5873/1", "ST5773/40"]);
    expect(rows.map((row) => row.querySelector("[data-field=rank]")?.textContent)).toEqual(["1", "2"]);
    expect(rows.map((row) => row.querySelector("[data-field=name]")?.textContent)).toEqual(["Ridge Road", "Brandon Hill"]);
    expect(rows.map((row) => row.querySelector("[data-field=walk]")?.textContent)).toEqual(["6 min walk", "14 min walk"]);
    expect(rows.map((row) => row.querySelector("[data-field=leave-by]")?.textContent)).toEqual([
      "Leave 07:54",
      "Leave 07:31",
    ]);
  });

  it("says whether each spot meets the Duration target", () => {
    const rows = [...render(ranked).querySelectorAll("[data-spot]")];
    expect(rows.map((row) => row.querySelector("[data-field=target]")?.textContent)).toEqual([
      "20 min target met",
      "20 min target not met",
    ]);
    expect(rows.map((row) => row.querySelector("[data-field=target]")?.getAttribute("data-met"))).toEqual([
      "true",
      "false",
    ]);
  });

  it("draws the walk hatched from leave-by to arrival on the window's axis", () => {
    const [first, second] = [...render(ranked).querySelectorAll("[data-spot]")];
    // 07:54 is 54 min in: 30 %; 6 min is 3.33 %.
    expect(segments(first!, "walk")).toEqual([[30, 3.3333]]);
    // 07:31:30 is 31.5 min in: 17.5 %; 13.5 min is 7.5 %.
    expect(segments(second!, "walk")).toEqual([[17.5, 7.5]]);
  });

  it("draws every sun-in-view interval and its low-sun part", () => {
    const [first, second] = [...render(ranked).querySelectorAll("[data-spot]")];
    expect(segments(first!, "sun")).toEqual([[33.3333, 33.3333]]);
    expect(segments(first!, "low-sun")).toEqual([[33.3333, 16.6667]]);
    expect(segments(second!, "sun")).toEqual([
      [25, 5],
      [46.6667, 53.3333],
    ]);
    expect(segments(second!, "low-sun")).toEqual([[46.6667, 10]]);
  });

  it("draws the leave-by line", () => {
    const [first, second] = [...render(ranked).querySelectorAll("[data-spot]")];
    const line = (row: Element) => percent((row.querySelector("[data-segment=leave-by]") as HTMLElement).style.left);
    expect(line(first!)).toBe(30);
    expect(line(second!)).toBe(17.5);
  });

  it("labels the window's axis with its start and end", () => {
    const axis = render(ranked).querySelector("[data-field=axis]");
    expect(axis?.textContent).toContain("07:00");
    expect(axis?.textContent).toContain("10:00");
  });

  it("gives the ranking's reason with its evidence label", () => {
    expect(render(ranked).textContent).toContain("Protocols factor: untested in humans");
  });

  it("clips a segment to the axis", () => {
    const early = {
      ...ranked,
      spots: [spot({ leaveBy: "2026-09-23T06:58:00+01:00", walkMin: 4 })],
    };
    const row = render(early).querySelector("[data-spot]")!;
    expect(segments(row, "walk")).toEqual([[0, 1.1111]]);
  });
});

describe("highlighted spot", () => {
  it("shows the highlighted spot's sun intervals as clock ranges, and no other row's", () => {
    const root = document.createElement("div");
    root.append(renderAnswer(ranked, "ST5773/40"));
    const times = [...root.querySelectorAll("[data-spot]")].map((row) => row.querySelector("[data-field=sun-times]")?.textContent);
    expect(times).toEqual([undefined, "Sun in view 07:45–07:54, 08:24–10:00 · low sun 08:24–08:42"]);
    expect(root.querySelector("[aria-current=true]")?.getAttribute("data-spot")).toBe("ST5773/40");
  });

  it("says when the highlighted spot has no sun in view", () => {
    const root = document.createElement("div");
    root.append(renderAnswer({ ...ranked, spots: [spot({ sunIntervals: [], lowSunIntervals: [] })] }, "ST5873/1"));
    expect(root.querySelector("[data-field=sun-times]")?.textContent).toBe("No sun in view");
  });
});

describe("not covered", () => {
  it('says "not covered here" and lists nothing', () => {
    const root = render({ status: "not-covered", spots: [] });
    expect(root.textContent).toMatch(/not covered here/i);
    expect(root.querySelectorAll("[data-spot]")).toHaveLength(0);
  });
});
