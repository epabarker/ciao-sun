// The timeline bar: one spot's plan on its window's axis (spec #27, user
// story 46). Every segment comes from an Answer field:
//
//   walk      hatched, leave-by to leave-by + walkMin
//   sun       each of sunIntervals
//   low-sun   each of lowSunIntervals, a band along the bottom
//   stay      a fallback spot's "stay N min": arrival to arrival + stayMin
//   leave-by  a line at leaveBy
//
// Positions are percentages of axisStart..axisEnd, clipped to it. The Evening
// axis is the last 3 h before Nominal sunset, so a leave-by can fall before
// it: the line then sits at the axis start marked data-off-axis="before".

import type { AnswerWindow, Interval, Spot } from "../contract";
import { TIME_ZONE, toLocalIso } from "../solar/local-day";
import { h } from "./dom";
import { clockOf } from "./format";

export type SegmentKind = "walk" | "sun" | "low-sun" | "stay" | "leave-by";

const round = (x: number) => Math.round(x * 10_000) / 10_000;

/** Maps instants onto the axis, as percentages. */
export class Axis {
  readonly startMs: number;
  private readonly span: number;

  constructor(window: Pick<AnswerWindow, "axisStart" | "axisEnd">) {
    this.startMs = Date.parse(window.axisStart);
    this.span = Date.parse(window.axisEnd) - this.startMs;
  }

  at(ms: number): number {
    return Math.min(100, Math.max(0, ((ms - this.startMs) / this.span) * 100));
  }

  /** The [left, width] of a span of instants, clipped; undefined if it is off the axis. */
  place(fromMs: number, toMs: number): [number, number] | undefined {
    const left = this.at(fromMs);
    const right = this.at(toMs);
    return right > left ? [round(left), round(right - left)] : undefined;
  }
}

function segment(kind: SegmentKind, place: [number, number] | undefined): HTMLElement | null {
  if (!place) return null;
  return h("span", { class: `seg seg-${kind}`, "data-segment": kind, style: `left:${place[0]}%;width:${place[1]}%` });
}

function intervals(kind: SegmentKind, axis: Axis, list: readonly Interval[]): (HTMLElement | null)[] {
  return list.map((iv) => segment(kind, axis.place(Date.parse(iv.start), Date.parse(iv.end))));
}

/** The bar for one spot. */
export function timelineBar(spot: Spot, window: AnswerWindow): HTMLElement {
  const axis = new Axis(window);
  const leave = Date.parse(spot.leaveBy);
  const arrive = leave + spot.walkMin * 60_000;
  return h(
    "div",
    { class: "timeline", role: "img", "aria-label": timelineDescription(spot) },
    ...intervals("sun", axis, spot.sunIntervals),
    ...intervals("low-sun", axis, spot.lowSunIntervals),
    segment("walk", axis.place(leave, arrive)),
    spot.stayMin ? segment("stay", axis.place(arrive, arrive + spot.stayMin * 60_000)) : null,
    h("span", {
      class: "seg seg-leave-by",
      "data-segment": "leave-by",
      "data-off-axis": leave < axis.startMs ? "before" : undefined,
      style: `left:${round(axis.at(leave))}%`,
    }),
  );
}

function timelineDescription(spot: Spot): string {
  const sun = spot.sunIntervals.map((iv) => `${clockOf(iv.start)} to ${clockOf(iv.end)}`).join(", ");
  const stay = spot.stayMin ? `; stay ${spot.stayMin} min` : "";
  return `Leave ${clockOf(spot.leaveBy)}${stay}; sun in view ${sun || "never"}`;
}

/** The shared axis above the bars: its start, end and the whole hours between. */
export function axisScale(window: AnswerWindow): HTMLElement {
  const axis = new Axis(window);
  const start = Date.parse(window.axisStart);
  const end = Date.parse(window.axisEnd);
  const ticks: HTMLElement[] = [
    h("span", { class: "tick tick-start", style: "left:0%" }, clockOf(window.axisStart)),
  ];
  const hour = 3_600_000;
  for (let t = Math.ceil(start / hour) * hour; t < end; t += hour) {
    if (t - start < hour / 2 || end - t < hour / 2) continue;
    // Whole UTC hours are whole London hours: its offsets are whole hours.
    ticks.push(h("span", { class: "tick", style: `left:${round(axis.at(t))}%` }, clockOf(toLocalIso(t, TIME_ZONE))));
  }
  ticks.push(h("span", { class: "tick tick-end", style: "left:100%" }, clockOf(window.axisEnd)));
  return h("div", { class: "axis", "data-field": "axis" }, ...ticks);
}
