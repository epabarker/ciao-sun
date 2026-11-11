// The bottom sheet: the result, pulled up over the map. It rests at one of
// three stops; a drag on its handle follows the finger and snaps to the
// nearest stop on release, and a tap on the handle steps through them.
//
//   <main class="sheet" data-sheet="peek|half|full">
//     <button class="sheet-handle" data-action="sheet">   the grab bar
//     <div class="sheet-body">                            the result, scrolling
//
// The stop is the app's state, so it survives redraws. Its heights are in
// style.css (`--sheet-h`); `stopHeight` mirrors them for the drag.

import { type Child, h } from "./dom";

export type SheetStop = "peek" | "half" | "full";

const STOPS: readonly SheetStop[] = ["peek", "half", "full"];

/** The next stop for a tap on the handle: up, and from the top back down. */
const TAP: Record<SheetStop, SheetStop> = { peek: "half", half: "full", full: "peek" };

/** A stop's height in px for a viewport `height` px tall; as style.css's `--sheet-h`. */
export function stopHeight(stop: SheetStop, height: number): number {
  switch (stop) {
    case "peek":
      return 176;
    case "half":
      return Math.round(height * 0.5);
    case "full":
      return height - 64;
  }
}

/** Movement under this many px is a tap, not a drag. */
const DRAG_SLOP_PX = 6;
/** A click this soon after a drag ends is the drag's own. */
const CLICK_AFTER_DRAG_MS = 400;
let dragEndedAt = -Infinity;

export function bottomSheet(stop: SheetStop, onStop: (stop: SheetStop) => void, ...content: Child[]): HTMLElement {
  const viewport = () => window.innerHeight;
  const handle = h(
    "button",
    { type: "button", class: "sheet-handle", "data-action": "sheet", "aria-label": "Pull the list up or down" },
    h("span", { class: "sheet-grip" }),
  );
  const sheet = h(
    "main",
    { class: "sheet", "data-sheet": stop, "aria-live": "polite" },
    handle,
    h("div", { class: "sheet-body" }, ...content),
  );

  let drag: { pointer: number; fromY: number; fromHeight: number; height: number; moved: boolean } | undefined;
  const follow = (height: number) => document.documentElement.style.setProperty("--sheet-h", `${height}px`);

  handle.addEventListener("pointerdown", (event) => {
    drag = { pointer: event.pointerId, fromY: event.clientY, fromHeight: stopHeight(stop, viewport()), height: 0, moved: false };
    drag.height = drag.fromHeight;
    handle.setPointerCapture?.(event.pointerId);
  });
  handle.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointer) return;
    const dy = drag.fromY - event.clientY;
    if (!drag.moved && Math.abs(dy) < DRAG_SLOP_PX) return;
    drag.moved = true;
    drag.height = Math.min(Math.max(drag.fromHeight + dy, 0), viewport());
    follow(drag.height);
  });
  const release = (event: PointerEvent) => {
    if (!drag || event.pointerId !== drag.pointer) return;
    const { moved, height } = drag;
    drag = undefined;
    document.documentElement.style.removeProperty("--sheet-h");
    if (!moved) return;
    dragEndedAt = Date.now();
    const vh = viewport();
    const nearest = STOPS.reduce((best, next) =>
      Math.abs(stopHeight(next, vh) - height) < Math.abs(stopHeight(best, vh) - height) ? next : best,
    );
    onStop(nearest);
  };
  handle.addEventListener("pointerup", release);
  handle.addEventListener("pointercancel", release);
  handle.addEventListener("click", () => {
    // The click that ends a drag is not a tap. It may land on the handle of
    // the sheet redrawn at the new stop, so the drag's end is kept across sheets.
    if (Date.now() - dragEndedAt < CLICK_AFTER_DRAG_MS) return;
    onStop(TAP[stop]);
  });
  return sheet;
}
