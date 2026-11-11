import { describe, expect, it } from "vitest";

import type { Manifest } from "../loader/loader";
import { listYears, readAbout } from "./about";

const base: Manifest = { format: 1, build: "20261111a", coverage: { type: "Polygon", coordinates: [] }, tiles: {} };

describe("readAbout", () => {
  it("is undefined until a manifest is loaded", () => {
    expect(readAbout(undefined)).toBeUndefined();
  });

  it("leaves out malformed fields instead of throwing", () => {
    const about = readAbout({
      ...base,
      licence: { spdx: "ODbL-1.0" },
      attribution: [
        { source: "Environment Agency", text: "© EA" },
        { source: "No text" },
        "not an entry",
        { source: "OSM", text: "© OpenStreetMap contributors", licence: "ODbL", licenceUrl: "javascript:alert(1)" },
      ],
      lidarSurveyYears: [2021, "2019", 2019.5, 2018],
    });
    expect(about).toEqual({
      build: "20261111a",
      licence: undefined,
      credits: [
        { source: "Environment Agency", text: "© EA", licence: undefined, licenceUrl: undefined },
        { source: "OSM", text: "© OpenStreetMap contributors", licence: "ODbL", licenceUrl: undefined },
      ],
      surveyYears: [2018, 2021],
    });
  });

  it("has no credits or years when the manifest has none", () => {
    expect(readAbout(base)).toEqual({ build: "20261111a", licence: undefined, credits: [], surveyYears: [] });
  });
});

describe("listYears", () => {
  it("joins years as prose", () => {
    expect(listYears([2019])).toBe("2019");
    expect(listYears([2019, 2021])).toBe("2019 and 2021");
    expect(listYears([2017, 2019, 2021])).toBe("2017, 2019 and 2021");
  });
});
