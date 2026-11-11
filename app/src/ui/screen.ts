// The answer screen's frame: the sentence at the top, the result below.
//
//   <div class="screen" data-window="morning">
//     <header class="top">   the sentence editor (and, from #48, the tabs)
//     <main class="sheet">   the result: the answer view or a message
//                            (#47 makes it a bottom sheet over the map)
//     <footer class="foot">  fixed copy (#48 safety copy) and the About link
//     <section class="about"> the About the data sheet, while it is open
//
// `renderScreen` replaces the root's content on every state change; views are
// pure functions of state, and controls report through callbacks.

import type { Answer, WindowName } from "../contract";
import { aboutLink } from "./about-view";
import { renderAnswer, message } from "./answer-view";
import { h } from "./dom";

export type Result =
  | { kind: "loading" }
  | { kind: "need-origin" }
  | { kind: "answer"; answer: Answer }
  /** The manifest or a tile is in a format this version can't read. */
  | { kind: "unreadable"; format: number }
  /** The data host could not be reached. */
  | { kind: "unavailable" }
  /** The scorer could not answer this query. */
  | { kind: "failed" };

export const UNREADABLE_TITLE = "This version can't read this data.";

export function renderResult(result: Result): Node {
  switch (result.kind) {
    case "loading":
      return message("loading", "Finding spots…");
    case "need-origin":
      return message("need-origin", "Where from?", "Location isn't available. Type a position as latitude, longitude.");
    case "answer":
      return renderAnswer(result.answer);
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
  sentence: Node;
  result: Result;
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
      h("header", { class: "top" }, parts.sentence),
      h("main", { class: "sheet", "aria-live": "polite" }, renderResult(parts.result)),
      h("footer", { class: "foot" }, ...(parts.footer ?? []), aboutLink(parts.onAbout)),
      parts.about,
    ),
  );
}
