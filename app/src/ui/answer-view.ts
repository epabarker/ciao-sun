// The answer view: an Answer, as the ranked list or a status message. It
// renders Answer fields only and never recomputes scoring.
//
// Each status has a view in STATUS_VIEWS (#46, #48). A view gets the Answer
// and an AnswerContext: the Query it answers, read only for its date and
// `now`; the actions a message offers; and the highlighted spot.
// Rows link to the map's markers through `data-spot` (the candidateId): a tap
// on a row's head (`data-action="select-spot"`) highlights the spot, and the
// highlighted row (`aria-current`) shows its sun times (#47). Ranked and
// fallback rows both link; the spot beyond max walk has no marker, so its row
// does not.

import { PROTOCOLS_FACTOR } from "../about/about";
import type { Answer, Interval, Query, Spot, Status } from "../contract";
import { morningWindowOver } from "../query/query";
import { h } from "./dom";
import { clockOf, dateLabel, walkLabel } from "./format";
import { axisScale, timelineBar } from "./timeline";

export const RANKING_REASON = `Ranked by low-sun minutes. ${PROTOCOLS_FACTOR}.`;

export const LAMP_NOTICE = "Sunrise is more than an hour after you wake: switch on a bright lamp when you get up.";
export const LAMP_ONLY_TITLE = "No daylight in your Morning window.";
export const LAMP_ONLY_ADVICE = "Switch on a bright lamp when you get up.";
export const WINDOW_OVER_TITLE = "Morning window has ended.";
export const EVENING_OVER_TITLE = "Evening window has ended.";

/** What a message can send the person to. */
export interface AnswerActions {
  planTomorrowMorning(): void;
  showEvening(): void;
}

export interface AnswerContext {
  /** The Query the Answer answers. */
  query?: Query;
  actions?: AnswerActions;
  /** The highlighted spot's candidateId. */
  selected?: string;
}

export type StatusView = (answer: Answer, context: AnswerContext) => Node;

/** "Open sky still counts, aim for N min outside." */
export function fallbackLine(targetMin: number | undefined): string {
  return `Open sky still counts, aim for ${targetMin ?? "?"} min outside.`;
}

/** A fallback spot's "stay N min". */
export function stayLabel(stayMin: number): string {
  return stayMin > 0 ? `Stay ${stayMin} min` : "The walk alone meets the target";
}

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

function targetBadge(spot: Spot, target: number | undefined): HTMLElement {
  return h(
    "span",
    { class: `badge ${spot.targetMet ? "met" : "unmet"}`, "data-field": "target", "data-met": String(spot.targetMet) },
    `${target ?? "?"} min target ${spot.targetMet ? "met" : "not met"}`,
  );
}

/**
 * One spot. A numbered row (`rank`) has a marker on the map, and a tap on its
 * head highlights it there; `selected` is whether it is the highlighted one.
 * A fallback spot (one with `stayMin`) says how long to stay where a spot
 * with sun says whether it meets the target.
 */
function spotRow(spot: Spot, rank: number | null, answer: Answer, selected: boolean): HTMLElement {
  const foot =
    spot.stayMin === undefined
      ? [targetBadge(spot, answer.durationTargetMin), h("span", { class: "mute" }, `${spot.sunMinutes} min sun`)]
      : [h("span", { class: "badge stay", "data-field": "stay" }, stayLabel(spot.stayMin))];
  const where = [
    h(
      "span",
      { class: "spot-where" },
      h("span", { class: "spot-name", "data-field": "name" }, spot.name),
      h("span", { class: "spot-walk", "data-field": "walk" }, walkLabel(spot.walkMin)),
    ),
    h("span", { class: "spot-leave", "data-field": "leave-by" }, `Leave ${clockOf(spot.leaveBy)}`),
  ];
  const head =
    rank === null
      ? h("div", { class: "spot-head" }, ...where)
      : h(
          // A tap on the head highlights the spot, here and on the map (#47).
          "button",
          { type: "button", class: "spot-head", "data-action": "select-spot", "aria-expanded": String(selected) },
          h("span", { class: "rank", "data-field": "rank" }, String(rank)),
          ...where,
        );
  return h(
    "li",
    { class: "spot", "data-spot": spot.candidateId, "aria-current": selected ? "true" : undefined },
    head,
    answer.window ? timelineBar(spot, answer.window) : null,
    h("div", { class: "spot-foot" }, ...foot),
    selected ? sunTimes(spot) : null,
  );
}

function numberedRows(answer: Answer, selected: string | undefined): HTMLElement {
  return h(
    "ol",
    { class: "spots" },
    ...answer.spots.map((spot, i) => spotRow(spot, i + 1, answer, spot.candidateId === selected)),
  );
}

/** The lamp suggestion, on a Morning Answer that says lamp. */
function lampNotice(answer: Answer): HTMLElement | null {
  return answer.lamp === true ? h("p", { class: "notice", "data-field": "lamp" }, LAMP_NOTICE) : null;
}

function key(withStay: boolean): HTMLElement {
  return h(
    "p",
    { class: "key mute" },
    h("i", { class: "key-walk" }),
    "walk ",
    withStay ? h("i", { class: "key-stay" }) : null,
    withStay ? "stay " : null,
    h("i", { class: "key-sun" }),
    "sun in view ",
    h("i", { class: "key-low" }),
    "low sun ",
    h("i", { class: "key-leave" }),
    "leave",
  );
}

function rankedView(answer: Answer, { selected }: AnswerContext): Node {
  return h(
    "section",
    { class: "answer answer-ranked", "data-status": answer.status },
    lampNotice(answer),
    answer.window ? axisScale(answer.window) : null,
    numberedRows(answer, selected),
    key(false),
    h("p", { class: "reason mute" }, RANKING_REASON),
  );
}

/**
 * The fallback: the nearest open spots, each with "stay N min", and the
 * nearest spot with sun beyond max walk when the Answer names one.
 */
function fallbackView(answer: Answer, { selected }: AnswerContext): Node {
  const beyond = answer.nearestSunBeyondLimit;
  return h(
    "section",
    { class: "answer answer-fallback", "data-status": answer.status },
    lampNotice(answer),
    h("p", { class: "message-title", "data-field": "fallback" }, fallbackLine(answer.durationTargetMin)),
    answer.window ? axisScale(answer.window) : null,
    numberedRows(answer, selected),
    beyond
      ? h(
          "div",
          { class: "beyond", "data-field": "beyond" },
          h("p", { class: "beyond-title" }, "Sun beyond your max walk"),
          h("ul", { class: "spots" }, spotRow(beyond, null, answer, false)),
        )
      : null,
    key(true),
  );
}

/** "08:13", with the day when it is not the query's date. */
function timeOnDay(iso: string, date: string | undefined): string {
  const day = iso.slice(0, 10);
  return date === undefined || day === date ? clockOf(iso) : `${clockOf(iso)} on ${dateLabel(day)}`;
}

function actionButton(action: string, label: string, run: (() => void) | undefined): HTMLButtonElement {
  const button = h("button", { type: "button", class: "link", "data-action": action }, label);
  button.addEventListener("click", () => run?.());
  return button;
}

/**
 * Lamp-only: a Morning window with no minutes. When the Query shows the
 * window is already over, that is all it says, pointing on (#27, Ed's
 * ruling); otherwise the morning holds no daylight, and it gives the lamp and
 * the next outdoor light.
 */
function lampOnlyView(answer: Answer, { query, actions }: AnswerContext): Node {
  if (query !== undefined && morningWindowOver(query)) {
    return h(
      "section",
      { class: "answer message message-window-over", "data-status": answer.status, role: "status" },
      h("p", { class: "message-title", "data-field": "window-over" }, WINDOW_OVER_TITLE),
      h(
        "p",
        { class: "mute" },
        "Plan ",
        actionButton("plan-tomorrow-morning", "tomorrow's Morning", actions?.planTomorrowMorning),
        ", or see the ",
        actionButton("show-evening", "Evening tab", actions?.showEvening),
        ".",
      ),
    );
  }
  return h(
    "section",
    { class: "answer message message-lamp-only", "data-status": answer.status, role: "status" },
    h("p", { class: "message-title", "data-field": "lamp-only" }, LAMP_ONLY_TITLE),
    h("p", { "data-field": "lamp" }, LAMP_ONLY_ADVICE),
    answer.nextOutdoorLight
      ? h(
          "p",
          { class: "mute", "data-field": "next-light" },
          `Outdoor light is next available at ${timeOnDay(answer.nextOutdoorLight, query?.date)}.`,
        )
      : null,
  );
}

/**
 * No Evening window: it would start after Nominal sunset. When the Query was
 * asked at or after Nominal sunset that is because the evening is over, which
 * it says instead, pointing to tomorrow's Morning.
 */
function noEveningView(answer: Answer, { query, actions }: AnswerContext): Node {
  const sunset = answer.nominalSunset;
  if (query?.now !== undefined && sunset !== undefined && Date.parse(query.now) >= Date.parse(sunset)) {
    return h(
      "section",
      { class: "answer message message-no-evening-window", "data-status": answer.status, role: "status" },
      h("p", { class: "message-title", "data-field": "no-evening-window" }, EVENING_OVER_TITLE),
      h(
        "p",
        { class: "mute" },
        `Sunset was at ${clockOf(sunset)}. Plan `,
        actionButton("plan-tomorrow-morning", "tomorrow's Morning", actions?.planTomorrowMorning),
        ".",
      ),
    );
  }
  const when = query === undefined || query.now !== undefined ? "today" : `on ${dateLabel(query.date)}`;
  return h(
    "section",
    { class: "answer message message-no-evening-window", "data-status": answer.status, role: "status" },
    h("p", { class: "message-title", "data-field": "no-evening-window" }, `No Evening window ${when}.`),
    h(
      "p",
      { class: "mute" },
      sunset
        ? `Sunset is at ${clockOf(sunset)}, before your Evening window would start: 6 h after you wake, and not before solar noon.`
        : "The sun does not set on this day.",
    ),
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

export const STATUS_VIEWS: Record<Status, StatusView> = {
  ranked: rankedView,
  "not-covered": () =>
    message("not-covered", "Not covered here.", "Ciao Sun only knows the Bristol coverage. Choose an origin inside it."),
  fallback: fallbackView,
  "lamp-only": lampOnlyView,
  "no-evening-window": noEveningView,
};

/** The view for an Answer. */
export function renderAnswer(answer: Answer, context: AnswerContext = {}): Node {
  return STATUS_VIEWS[answer.status](answer, context);
}
