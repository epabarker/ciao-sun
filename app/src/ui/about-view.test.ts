// @vitest-environment happy-dom
//
// The About link is part of the screen's frame, so it is on both tabs.

import { describe, expect, it } from "vitest";

import type { WindowName } from "../contract";
import { renderScreen } from "./screen";

describe("About link", () => {
  it.each<WindowName>(["morning", "evening"])("is in the footer on the %s tab and opens the sheet", (window) => {
    const root = document.createElement("div");
    let opened = 0;
    renderScreen(root, {
      window,
      sentence: document.createTextNode(""),
      result: { kind: "loading" },
      onAbout: () => opened++,
    });
    const link = root.querySelector<HTMLButtonElement>(`.screen[data-window=${window}] footer.foot [data-action=about]`);
    expect(link?.textContent).toBe("About the data");
    link?.click();
    expect(opened).toBe(1);
  });
});
