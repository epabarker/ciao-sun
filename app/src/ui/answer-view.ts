// The answer view: an Answer, as the ranked list or a status message. It
// renders Answer fields only and never recomputes scoring.
//
// Each status has a view in STATUS_VIEWS (#46, #48). A view gets the Answer
// and an AnswerContext: the Query it answers, read only for its date and
// `now`, and the actions a message offers. #47 moves the list into the map's
// bottom sheet and links rows to markers through `data-spot` (the candidateId).

import { PROTOCOLS_FACTOR } from "../about/about";
import type { Answer, Query, Spot, Status } from "../contract";
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

function targetBadge(spot: Spot, target: number | undefined): HTMLElement {
  return h(
    "span",
    { class: `badge ${spot.targetMet ? "met" : "unmet"}`, "data-field": "target", "data-met": String(spot.targetMet) },
    `${target ?? "?"} min target ${spot.targetMet ? "met" : "not met"}`,
  );
}

/**
 * One spot. A fallback spot (one with `stayMin`) says how long to stay where
 * a spot with sun says whether it meets the target.
 */
function spotRow(spot: Spot, rank: number | null, answer: Answer): HTMLElement {
  const foot =
    spot.stayMin === undefined
      ? [targetBadge(spot, answer.durationTargetMin), h("span", { class: "mute" }, `${spot.sunMinutes} min sun`)]
      : [h("span", { class: "badge stay", "data-field": "stay" }, stayLabel(spot.stayMin))];
  return h(
    "li",
    { class: "spot", "data-spot": spot.candidateId },
    h(
      "div",
      { class: "spot-head" },
      rank === null ? null : h("span", { class: "rank", "data-field": "rank" }, String(rank)),
      h(
        "div",
        { class: "spot-where" },
        h("span", { class: "spot-name", "data-field": "name" }, spot.name),
        h("span", { class: "spot-walk", "data-field": "walk" }, walkLabel(spot.walkMin)),
      ),
      h("span", { class: "spot-leave", "data-field": "leave-by" }, `Leave ${clockOf(spot.leaveBy)}`),
    ),
    answer.window ? timelineBar(spot, answer.window) : null,
    h("div", { class: "spot-foot" }, ...foot),
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

function rankedView(answer: Answer): Node {
  return h(
    "section",
    { class: "answer answer-ranked", "data-status": answer.status },
    lampNotice(answer),
    answer.window ? axisScale(answer.window) : null,
    h("ol", { class: "spots" }, ...answer.spots.map((spot, i) => spotRow(spot, i + 1, answer))),
    key(false),
    h("p", { class: "reason mute" }, RANKING_REASON),
  );
}

/**
 * The fallback: the nearest open spots, each with "stay N min", and the
 * nearest spot with sun beyond max walk when the Answer names one.
 */
function fallbackView(answer: Answer): Node {
  const beyond = answer.nearestSunBeyondLimit;
  return h(
    "section",
    { class: "answer answer-fallback", "data-status": answer.status },
    lampNotice(answer),
    h("p", { class: "message-title", "data-field": "fallback" }, fallbackLine(answer.durationTargetMin)),
    answer.window ? axisScale(answer.window) : null,
    h("ol", { class: "spots" }, ...answer.spots.map((spot, i) => spotRow(spot, i + 1, answer))),
    beyond
      ? h(
          "div",
          { class: "beyond", "data-field": "beyond" },
          h("p", { class: "beyond-title" }, "Sun beyond your max walk"),
          h("ul", { class: "spots" }, spotRow(beyond, null, answer)),
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
      answer.nominalSunset
        ? `Sunset is at ${clockOf(answer.nominalSunset)}, before your Evening window would start: 6 h after you wake, and not before solar noon.`
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
