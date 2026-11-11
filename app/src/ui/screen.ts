// The answer screen's frame: a full-screen map, the sentence over its top,
// and the result in a bottom sheet over the rest (#47).
//
//   <div class="map">          the map (MapLibre); made once, never redrawn
//   <div class="screen" data-window="morning">
//     <header class="top">     the sentence editor (and, from #48, the tabs)
//     <main class="sheet">     the bottom sheet (ui/sheet.ts): handle, then
//       <div class="sheet-body">
//         the result: the answer view or a message
//         <footer class="foot">  fixed copy (#48 safety copy) and the About link
//     <section class="about">  the About the data sheet, while it is open
//
// `renderScreen` replaces everything but the map on every state change; views
// are pure functions of state, and controls report through callbacks.

import type { Answer, WindowName } from "../contract";
import { aboutLink } from "./about-view";
import { renderAnswer, message } from "./answer-view";
import { h } from "./dom";
import { type SheetStop, bottomSheet } from "./sheet";

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

/** `selected` is the highlighted spot's candidateId. */
export function renderResult(result: Result, selected?: string): Node {
  switch (result.kind) {
    case "loading":
      return message("loading", "Finding spots…");
    case "need-origin":
      return message("need-origin", "Where from?", "Location isn't available. Type a position as latitude, longitude.");
    case "answer":
      return renderAnswer(result.answer, selected);
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
  /** The highlighted spot's candidateId, and a tap on a row. */
  selected?: string;
  onSelect?(id: string): void;
  /** Where the bottom sheet rests, and a drag or tap that moves it. */
  sheet?: SheetStop;
  onSheet?(stop: SheetStop): void;
}

/**
 * The map's container: the root's first child, made once and never
 * re-rendered, so the map lives across draws under the screen.
 */
export function mapContainer(root: HTMLElement): HTMLElement {
  let map = root.querySelector<HTMLElement>(":scope > .map");
  if (!map) {
    map = h("div", { class: "map" });
    root.prepend(map);
  }
  return map;
}

/** How much of the map the header and the bottom sheet cover, in px. */
export function screenInsets(root: HTMLElement): { top: number; bottom: number } {
  const top = root.querySelector(".top")?.getBoundingClientRect().bottom ?? 0;
  const sheet = root.querySelector(".sheet")?.getBoundingClientRect().top;
  return { top, bottom: sheet === undefined ? 0 : Math.max(0, window.innerHeight - sheet) };
}

export function renderScreen(root: HTMLElement, parts: ScreenParts): void {
  const next = h(
    "div",
    { class: "screen", "data-window": parts.window },
    h("header", { class: "top" }, parts.sentence),
    bottomSheet(
      parts.sheet ?? "half",
      (stop) => parts.onSheet?.(stop),
      renderResult(parts.result, parts.selected),
      h("footer", { class: "foot" }, ...(parts.footer ?? []), aboutLink(parts.onAbout)),
    ),
    parts.about,
  );
  next.addEventListener("click", (event) => {
    const head = (event.target as Element).closest?.("[data-action=select-spot]");
    const id = head?.closest("[data-spot]")?.getAttribute("data-spot");
    if (id) parts.onSelect?.(id);
  });
  // Everything but the map is replaced; the map's node never leaves the page.
  // The sheet keeps its scroll.
  const scrolled = root.querySelector(".sheet-body")?.scrollTop ?? 0;
  const map = root.querySelector(":scope > .map");
  for (const child of [...root.childNodes]) {
    if (child !== map) child.remove();
  }
  root.append(next);
  next.querySelector(".sheet-body")!.scrollTop = scrolled;
}
