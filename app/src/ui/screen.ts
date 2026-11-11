// The answer screen's frame: the sentence at the top, the result below.
//
//   <div class="screen" data-window="morning">
//     <header class="top">   the Morning/Evening tabs and the sentence editor
//     <main class="sheet">   the result: the answer view or a message
//                            (#47 makes it a bottom sheet over the map)
//     <footer class="foot">  fixed copy (ui/tabs.ts: safety, dim the lights) and the About link
//     <section class="about"> the About the data sheet, while it is open
//
// `renderScreen` replaces the root's content on every state change; views are
// pure functions of state, and controls report through callbacks.

import type { Answer, Query, WindowName } from "../contract";
import { aboutLink } from "./about-view";
import { type AnswerContext, renderAnswer, message } from "./answer-view";
import { h } from "./dom";

export type Result =
  | { kind: "loading" }
  | { kind: "need-origin" }
  /** `query` is the Query the Answer answers; the view reads its date and `now`. */
  | { kind: "answer"; answer: Answer; query?: Query }
  /** The manifest or a tile is in a format this version can't read. */
  | { kind: "unreadable"; format: number }
  /** The data host could not be reached. */
  | { kind: "unavailable" }
  /** The scorer could not answer this query. */
  | { kind: "failed" };

export const UNREADABLE_TITLE = "This version can't read this data.";

export function renderResult(result: Result, context?: AnswerContext): Node {
  switch (result.kind) {
    case "loading":
      return message("loading", "Finding spots…");
    case "need-origin":
      return message("need-origin", "Where from?", "Location isn't available. Type a position as latitude, longitude.");
    case "answer":
      return renderAnswer(result.answer, { ...context, query: result.query ?? context?.query });
    case "unreadable":
      return message(
        "unreadable",
        UNREADABLE_TITLE,
        Number.isFinite(result.format)
          ? `The data is in format f${result.format}. Reload to pick up a newer version of Ciao Sun.`
          : "Reload to pick up a newer version of Ciao Sun.",
      );
    case "unavailable":
      return message("unavailable", "Can't reach the data.", "Check the connection and try again.");
    case "failed":
      return message("failed", "Something went wrong working out this answer.", "Try again, or change the sky, date or Wake time.");
  }
}

export interface ScreenParts {
  window: WindowName;
  /** The Morning and Evening tabs, above the sentence. */
  tabs?: Node;
  sentence: Node;
  result: Result;
  /** What an answer's messages can lead to, and the Query the answer is for. */
  answerContext?: AnswerContext;
  footer?: Node[];
  /** Opens the About sheet; the link is in the footer whatever the window. */
  onAbout: () => void;
  /** The About sheet, while it is open. */
  about?: Node;
}

export function renderScreen(root: HTMLElement, parts: ScreenParts): void {
  root.replaceChildren(
    h(
      "div",
      { class: "screen", "data-window": parts.window },
      h("header", { class: "top" }, parts.tabs, parts.sentence),
      h("main", { class: "sheet", "aria-live": "polite" }, renderResult(parts.result, parts.answerContext)),
      h("footer", { class: "foot" }, ...(parts.footer ?? []), aboutLink(parts.onAbout)),
      parts.about,
    ),
  );
}
