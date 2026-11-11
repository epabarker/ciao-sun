// The answer view: an Answer, as the ranked list or a status message. It
// renders Answer fields only and never recomputes scoring.
//
// Each status has a view in STATUS_VIEWS. #46 writes `ranked` and
// `not-covered`; #48 writes the rest (fallback, lamp-only,
// no-evening-window) and the lamp notice, by replacing their entries.
// Rows link to the map's markers through `data-spot` (the candidateId): a tap
// on a row's head (`data-action="select-spot"`) highlights the spot, and the
// highlighted row (`aria-current`) shows its sun times (#47).

import type { Answer, Interval, Spot, Status } from "../contract";
import { h } from "./dom";
import { clockOf, walkLabel } from "./format";
import { axisScale, timelineBar } from "./timeline";

export const RANKING_REASON = "Ranked by low-sun minutes. Protocols factor: untested in humans.";

/** `selected` is the highlighted spot's candidateId. */
export type StatusView = (answer: Answer, selected?: string) => Node;

/** "08:16–10:30, 11:00–11:20": runs of minutes as clock ranges. */
function clockRanges(intervals: readonly Interval[]): string {
  return intervals.map((run) => `${clockOf(run.start)}–${clockOf(run.end)}`).join(", ");
}

/** The highlighted spot's sun times, from its Answer intervals. */
function sunTimes(spot: Spot): HTMLElement {
  const parts = [spot.sunIntervals.length ? `Sun in view ${clockRanges(spot.sunIntervals)}` : "No sun in view"];
  if (spot.lowSunIntervals.length) parts.push(`low sun ${clockRanges(spot.lowSunIntervals)}`);
  if (spot.lastSun) parts.push(`last sun ${clockOf(spot.lastSun)}`);
  return h("p", { class: "spot-sun", "data-field": "sun-times" }, parts.join(" · "));
}

function spotRow(spot: Spot, rank: number, answer: Answer, selected: boolean): HTMLElement {
  const target = answer.durationTargetMin;
  return h(
    "li",
    { class: "spot", "data-spot": spot.candidateId, "aria-current": selected ? "true" : undefined },
    h(
      // A tap on the head highlights the spot, here and on the map (#47).
      "button",
      { type: "button", class: "spot-head", "data-action": "select-spot", "aria-expanded": String(selected) },
      h("span", { class: "rank", "data-field": "rank" }, String(rank)),
      h(
        "span",
        { class: "spot-where" },
        h("span", { class: "spot-name", "data-field": "name" }, spot.name),
        h("span", { class: "spot-walk", "data-field": "walk" }, walkLabel(spot.walkMin)),
      ),
      h("span", { class: "spot-leave", "data-field": "leave-by" }, `Leave ${clockOf(spot.leaveBy)}`),
    ),
    answer.window ? timelineBar(spot, answer.window) : null,
    h(
      "div",
      { class: "spot-foot" },
      h(
        "span",
        { class: `badge ${spot.targetMet ? "met" : "unmet"}`, "data-field": "target", "data-met": String(spot.targetMet) },
        `${target ?? "?"} min target ${spot.targetMet ? "met" : "not met"}`,
      ),
      h("span", { class: "mute" }, `${spot.sunMinutes} min sun`),
    ),
    selected ? sunTimes(spot) : null,
  );
}

function rankedView(answer: Answer, selected?: string): Node {
  return h(
    "section",
    { class: "answer answer-ranked", "data-status": answer.status },
    answer.window ? axisScale(answer.window) : null,
    h("ol", { class: "spots" }, ...answer.spots.map((spot, i) => spotRow(spot, i + 1, answer, spot.candidateId === selected))),
    h(
      "p",
      { class: "key mute" },
      h("i", { class: "key-walk" }),
      "walk ",
      h("i", { class: "key-sun" }),
      "sun in view ",
      h("i", { class: "key-low" }),
      "low sun ",
      h("i", { class: "key-leave" }),
      "leave",
    ),
    h("p", { class: "reason mute" }, RANKING_REASON),
  );
}

/** A plain message in place of a list. */
export function message(kind: string, title: string, body?: string): HTMLElement {
  return h(
    "section",
    { class: `answer message message-${kind}`, "data-status": kind, role: "status" },
    h("p", { class: "message-title" }, title),
    body ? h("p", { class: "mute" }, body) : null,
  );
}

function notYetShown(answer: Answer): Node {
  return message(answer.status, "This answer can't be shown yet.");
}

export const STATUS_VIEWS: Record<Status, StatusView> = {
  ranked: rankedView,
  "not-covered": () =>
    message("not-covered", "Not covered here.", "Ciao Sun only knows the Bristol coverage. Choose an origin inside it."),
  fallback: notYetShown,
  "lamp-only": notYetShown,
  "no-evening-window": notYetShown,
};

/** The view for an Answer. */
export function renderAnswer(answer: Answer, selected?: string): Node {
  return STATUS_VIEWS[answer.status](answer, selected);
}
