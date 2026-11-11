// @vitest-environment happy-dom
//
// The About the data sheet, opened from the screen's footer, over the
// committed synthetic build and over a manifest whose credits differ from it.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type AppDeps, startApp } from "../../src/app";
import type { FetchLike } from "../../src/loader/loader";

const SYNTHETIC = `${resolve(import.meta.dirname, "../../../fixtures/synthetic")}/`;
const MANIFEST_PATH = "f1/20261111a/manifest.json";
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };
const SYNTHETIC_MANIFEST = JSON.parse(readFileSync(SYNTHETIC + MANIFEST_PATH, "utf8"));

function host(override: Record<string, unknown> = {}): FetchLike {
  return async (url) => {
    const path = url.slice(PIN.dataBase.length);
    if (path in override) return new Response(JSON.stringify(override[path]));
    try {
      return new Response(readFileSync(SYNTHETIC + path));
    } catch {
      return new Response("", { status: 404 });
    }
  };
}

function deps(overrides: Partial<AppDeps> = {}): AppDeps {
  return {
    config: PIN,
    fetch: host(),
    storage: () => null,
    now: () => Date.parse("2026-12-20T21:00:00+00:00"),
    locate: async () => ({ lat: 51.4645, lon: -2.5935 }),
    ...overrides,
  };
}

async function mount(d: AppDeps) {
  const root = document.createElement("div");
  const app = startApp(root, d);
  await app.idle();
  return { root, app };
}

function openAbout(root: HTMLElement) {
  const link = root.querySelector<HTMLButtonElement>("footer.foot [data-action=about]");
  expect(link?.textContent).toBe("About the data");
  link?.click();
  const sheet = root.querySelector<HTMLElement>("[data-sheet=about]");
  expect(sheet).not.toBeNull();
  return sheet as HTMLElement;
}

// Ed's ruling on the #27 review: the data host sees which tiles a query loads.
const PRIVACY =
  "Map and data tiles are fetched from our data host, so it sees roughly which area you're looking at, never your exact position.";

const credits = (sheet: HTMLElement) => [...sheet.querySelectorAll("[data-credit]")].map((el) => el.textContent);

describe("About the data sheet", () => {
  it("shows the credits, survey years and licence of the synthetic build's manifest", async () => {
    const { root } = await mount(deps());
    const sheet = openAbout(root);

    expect(credits(sheet)).toEqual([
      "Environment Agency: © Environment Agency copyright and/or database right 2022. All rights reserved. Open Government Licence v3.0",
      "Ordnance Survey: Contains OS data © Crown copyright and database right 2026 Open Government Licence v3.0",
      "OpenStreetMap: © OpenStreetMap contributors Open Database License (ODbL) v1.0",
      "Protomaps: Protomaps © OpenStreetMap Open Database License (ODbL) v1.0",
      "Met Office: Forecast data from the Met Office via Open-Meteo, cloud cover categorised by Ciao Sun CC BY-SA 4.0",
      "Open-Meteo: Weather data by Open-Meteo.com CC BY 4.0",
    ]);
    expect(sheet.querySelector("[data-field=survey-years]")?.textContent).toBe(
      "The LIDAR in this build was flown in 2019 and 2021.",
    );
    expect(sheet.querySelector("[data-field=licence]")?.textContent).toBe(
      "The data bundle (build 20261111a) is licensed under the Open Database License (ODbL) v1.0.",
    );
    expect(sheet.querySelector<HTMLAnchorElement>("[data-field=licence] a")?.href).toBe(
      "https://opendatacommons.org/licenses/odbl/1-0/",
    );
    expect(sheet.querySelector("[data-field=privacy]")?.textContent).toBe(PRIVACY);
  });

  it("renders the credits, years and licence from the manifest it is given, not from the app", async () => {
    const manifest = {
      ...SYNTHETIC_MANIFEST,
      licence: { name: "Test Licence 9.9", spdx: "TEST-9.9", url: "https://licence.example/9.9" },
      attribution: [
        {
          source: "Environment Agency",
          text: "© Environment Agency copyright and/or database right 2031. All rights reserved.",
          licence: "Open Government Licence v3.0",
          licenceUrl: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        },
        {
          source: "Met Office",
          text: "Forecast data from the Met Office via Open-Meteo",
          licence: "CC BY 4.0",
          licenceUrl: "https://creativecommons.org/licenses/by/4.0/",
        },
      ],
      lidarSurveyYears: [2017],
    };
    const { root } = await mount(deps({ fetch: host({ [MANIFEST_PATH]: manifest }) }));
    const sheet = openAbout(root);

    expect(credits(sheet)).toEqual([
      "Environment Agency: © Environment Agency copyright and/or database right 2031. All rights reserved. Open Government Licence v3.0",
      "Met Office: Forecast data from the Met Office via Open-Meteo CC BY 4.0",
    ]);
    expect(sheet.textContent).not.toContain("database right 2022");
    expect(sheet.textContent).not.toContain("Ordnance Survey");
    expect(sheet.querySelector("[data-field=survey-years]")?.textContent).toBe(
      "The LIDAR in this build was flown in 2017.",
    );
    expect(sheet.querySelector("[data-field=licence]")?.textContent).toBe(
      "The data bundle (build 20261111a) is licensed under the Test Licence 9.9.",
    );
  });

  it("carries the five fixed caveats, with the ranking reason verbatim", async () => {
    const { root } = await mount(deps());
    const sheet = openAbout(root);
    const caveat = (key: string) => sheet.querySelector(`[data-caveat=${key}]`)?.textContent;

    expect(caveat("leaf")).toBe("Trees are treated as in full leaf all year, so winter sun may arrive a little earlier than shown.");
    expect(caveat("clutter")).toContain("Stand clear of hedges and walls right beside you.");
    expect(caveat("refraction")).toContain("First-sun times carry about ±1.5 min of refraction uncertainty");
    expect(sheet.querySelector("[data-caveat=ranking] [data-field=ranking-reason]")?.textContent?.trim()).toBe(
      "Protocols factor: untested in humans.",
    );
    expect(caveat("duration")).toContain("10, 20 and 30 min");
    expect(caveat("duration")).toContain("Light Protocol 1");
    expect(caveat("duration")).toContain("Sleep Protocol 1 says at least 5–10 min when clear, 15 when cloudy and 30 when densely overcast");
  });

  it("stays open while the answer changes, and closes from its Close button", async () => {
    const { root, app } = await mount(deps());
    openAbout(root);

    const sky = root.querySelector<HTMLSelectElement>("header.top select");
    expect(sky).not.toBeNull();
    (sky as HTMLSelectElement).value = "overcast";
    sky?.dispatchEvent(new Event("change", { bubbles: true }));
    await app.idle();
    expect(root.querySelector("[data-sheet=about]")).not.toBeNull();

    root.querySelector<HTMLButtonElement>("[data-action=close-about]")?.click();
    expect(root.querySelector("[data-sheet=about]")).toBeNull();
    expect(root.querySelector("footer.foot [data-action=about]")).not.toBeNull();
  });

  it("opens with the caveats but no credits when the data can't be reached", async () => {
    const { root } = await mount(deps({ fetch: async () => new Response("", { status: 503 }) }));
    expect(root.querySelector("[data-status=unavailable]")).not.toBeNull();
    const sheet = openAbout(root);

    expect(credits(sheet)).toEqual([]);
    expect(sheet.querySelector("[data-field=credits-pending]")?.textContent).toBe("Credits and the licence load with the data.");
    expect(sheet.querySelectorAll("[data-caveat]")).toHaveLength(5);
    expect(sheet.querySelector("[data-field=privacy]")?.textContent).toBe(PRIVACY);
  });
});
