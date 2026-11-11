// The Morning and Evening tabs, and the fixed copy under them (spec #27,
// "Client app / Copy"; #48). The app chooses the tab it opens on
// (`chooseWindow` in query/query.ts); a tap reports the window chosen.

import type { WindowName } from "../contract";
import { h } from "./dom";

export const TAB_LABELS: Record<WindowName, string> = { morning: "Morning", evening: "Evening" };

/** On both tabs. */
export const SAFETY_COPY =
  "No sunglasses and no brimmed hat, so the light reaches your eyes. Never stare at the sun.";

/** On the Evening tab only. There is no evening lamp. */
export const DIM_LIGHTS = "After sunset, dim the lights.";

export function renderTabs(current: WindowName, onSelect: (window: WindowName) => void): HTMLElement {
  return h(
    "nav",
    { class: "tabs", role: "tablist", "aria-label": "Window" },
    ...(Object.keys(TAB_LABELS) as WindowName[]).map((window) => {
      const tab = h(
        "button",
        { type: "button", class: "tab", role: "tab", "data-tab": window, "aria-selected": String(window === current) },
        TAB_LABELS[window],
      );
      tab.addEventListener("click", () => onSelect(window));
      return tab;
    }),
  );
}

/** The fixed copy for a tab, for the screen's footer. */
export function fixedCopy(window: WindowName): HTMLElement[] {
  const safety = h("p", { class: "fixed-copy mute", "data-field": "safety" }, SAFETY_COPY);
  if (window === "morning") return [safety];
  return [h("p", { class: "fixed-copy", "data-field": "dim-lights" }, DIM_LIGHTS), safety];
}
