// The release job (#54): `scripts/release.ts`, which the tag workflow calls.
// Everything here runs without GitHub: the pinned build is the committed
// synthetic one, read through a mirror of the data host.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";

import { afterAll, describe, expect, it } from "vitest";

import pkg from "../../package.json";
import pin from "../../release.json";
import {
  type ReleaseOptions,
  ReleaseRefused,
  checkBundle,
  checkPin,
  checkPinShape,
  checkTag,
  downloadBuild,
  mirrorFetch,
  pack,
  release,
  runParity,
  viteBuild,
} from "../../scripts/release.ts";

const APP = resolve(import.meta.dirname, "../..");
const SYNTHETIC = resolve(import.meta.dirname, "../../../fixtures/synthetic");
const PIN = { dataBase: "https://data.example.invalid/", format: 1, build: "20261111a" };
const scratch: string[] = [];

function tempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "ciao-sun-release-test-"));
  scratch.push(dir);
  return dir;
}

function filesIn(dir: string): string[] {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(dir, join(entry.parentPath, entry.name)).split("\\").join("/"))
    .sort();
}

afterAll(() => {
  for (const dir of scratch) rmSync(dir, { recursive: true, force: true });
});

describe("the tag", () => {
  it("is accepted when it names the app's version", () => {
    expect(checkTag("ciao-sun-v0.1.0", "0.1.0")).toBe("0.1.0");
    expect(checkTag("ciao-sun-v12.3.40", "12.3.40")).toBe("12.3.40");
  });

  it.each([
    ["ciao-sun-v0.1.1", "0.1.0"],
    ["ciao-sun-v1.0.0", "0.1.0"],
  ])("is refused when %s is not version %s", (tag, version) => {
    expect(() => checkTag(tag, version)).toThrow(ReleaseRefused);
    expect(() => checkTag(tag, version)).toThrow(/package\.json/);
  });

  it.each(["v0.1.0", "ciao-sun-v0.1", "ciao-sun-0.1.0", "ciao-sun-v0.1.0-rc1", "sunspot-v0.1.0", ""])(
    "is refused when it is %j, not ciao-sun-v<x.y.z>",
    (tag) => {
      expect(() => checkTag(tag, "0.1.0")).toThrow(ReleaseRefused);
    },
  );
});

describe("the pin", () => {
  const pin = { dataBase: "https://data.example.invalid/", format: 1, build: "20261111a" };

  it("is accepted with an absolute https dataBase", () => {
    expect(checkPin(pin)).toEqual(pin);
    expect(checkPin({ ...pin, dataBase: "https://data.example.invalid/ciao" })).toEqual({
      ...pin,
      dataBase: "https://data.example.invalid/ciao",
    });
  });

  it.each(["synthetic-data/", "/ciao-sun/synthetic-data/", "http://data.example.invalid/", "file:///tmp/x/", ""])(
    "is refused with dataBase %j",
    (dataBase) => {
      expect(() => checkPin({ ...pin, dataBase })).toThrow(ReleaseRefused);
    },
  );

  it.each([
    { ...pin, format: 0 },
    { ...pin, format: "1" },
    { ...pin, build: "2026-11-11.1" },
    { dataBase: pin.dataBase, format: 1 },
    null,
  ])("is refused when malformed: %j", (bad) => {
    expect(() => checkPin(bad)).toThrow(ReleaseRefused);
  });
});

describe("downloading the pinned build", () => {
  it("fetches the manifest, the fixtures index, every fixture and only the tiles they name", async () => {
    const requested: string[] = [];
    const mirror = mirrorFetch(PIN.dataBase, SYNTHETIC);
    const fetch = (url: string) => (requested.push(url), mirror(url));
    const dir = tempDir();

    const got = await downloadBuild(PIN, fetch, dir);

    const build = "https://data.example.invalid/f1/20261111a/";
    const index = JSON.parse(readFileSync(join(SYNTHETIC, "f1/20261111a/fixtures/index.json"), "utf8"));
    const fixtures = index.fixtures.map((entry: { file: string }) => `${build}fixtures/${entry.file}`);
    expect(fixtures).toHaveLength(15);
    expect(requested.sort()).toEqual(
      [
        `${build}manifest.json`,
        `${build}fixtures/index.json`,
        ...fixtures,
        `${build}tiles/ST5773.bin`,
        `${build}tiles/ST5873.bin`,
      ].sort(),
    );
    expect(got).toEqual({ buildDir: join(dir, "f1/20261111a"), fixtures: 15, tiles: 2 });
    const written = filesIn(dir);
    expect(written).toHaveLength(15 + 4);
    for (const file of written) {
      expect(readFileSync(join(dir, file)), file).toEqual(readFileSync(join(SYNTHETIC, file)));
    }
  });

  it("joins a dataBase with no trailing slash as the app does", async () => {
    const requested: string[] = [];
    const mirror = mirrorFetch("https://data.example.invalid/ciao/", SYNTHETIC);
    await downloadBuild({ ...PIN, dataBase: "https://data.example.invalid/ciao" }, (url) => (requested.push(url), mirror(url)), tempDir());
    expect(requested[0]).toBe("https://data.example.invalid/ciao/f1/20261111a/manifest.json");
  });

  it("refuses a build with no manifest: an interrupted publish is not a whole build", async () => {
    const copy = tempDir();
    cpSync(SYNTHETIC, copy, { recursive: true });
    rmSync(join(copy, "f1/20261111a/manifest.json"));
    await expect(downloadBuild(PIN, mirrorFetch(PIN.dataBase, copy), tempDir())).rejects.toThrow(
      /manifest\.json: HTTP 404.*not a whole build/,
    );
  });

  it("refuses a build whose manifest or index is another build's", async () => {
    await expect(
      downloadBuild({ ...PIN, build: "20261111b" }, mirrorFetch(PIN.dataBase, join(tempDir(), "x")), tempDir()),
    ).rejects.toThrow(ReleaseRefused);
    const copy = tempDir();
    cpSync(SYNTHETIC, copy, { recursive: true });
    cpSync(join(copy, "f1/20261111a"), join(copy, "f1/20261111b"), { recursive: true });
    await expect(downloadBuild({ ...PIN, build: "20261111b" }, mirrorFetch(PIN.dataBase, copy), tempDir())).rejects.toThrow(
      /manifest\.json is f1\/20261111a, not the pinned f1\/20261111b/,
    );
  });

  it("refuses an index that names a file outside the build", async () => {
    const copy = tempDir();
    cpSync(SYNTHETIC, copy, { recursive: true });
    const path = join(copy, "f1/20261111a/fixtures/index.json");
    const index = JSON.parse(readFileSync(path, "utf8"));
    index.fixtures[0].tiles = ["../../../evil"];
    writeFileSync(path, JSON.stringify(index));
    await expect(downloadBuild(PIN, mirrorFetch(PIN.dataBase, copy), tempDir())).rejects.toThrow(/grid ref/);
  });
});

/** A copy of the synthetic build with one fixture's reference Answer changed, so the JS can't match it. */
function tamperedBuild(): string {
  const copy = tempDir();
  cpSync(SYNTHETIC, copy, { recursive: true });
  const path = join(copy, "f1/20261111a/fixtures/morning-winter-solstice.json");
  const fixture = JSON.parse(readFileSync(path, "utf8"));
  fixture.answer.spots[0].walkMin += 1;
  writeFileSync(path, JSON.stringify(fixture));
  return copy;
}

describe("the parity run over the pinned build", () => {
  it("passes when the JS gives every fixture's Answer", { timeout: 60_000 }, async () => {
    const dir = tempDir();
    const downloaded = await downloadBuild(PIN, mirrorFetch(PIN.dataBase, SYNTHETIC), dir);

    expect(runParity(APP, dir, PIN, downloaded.fixtures)).toEqual({ fixtures: 15, tests: 76 });
  });

  it("is refused when one fixture's Answer differs", { timeout: 60_000 }, async () => {
    const dir = tempDir();
    const downloaded = await downloadBuild(PIN, mirrorFetch(PIN.dataBase, tamperedBuild()), dir);

    expect(() => runParity(APP, dir, PIN, downloaded.fixtures)).toThrow(/1 of 76 parity tests failed/);
  });

  it("is refused when it checked fewer Answers than the index lists", { timeout: 60_000 }, async () => {
    const dir = tempDir();
    await downloadBuild(PIN, mirrorFetch(PIN.dataBase, SYNTHETIC), dir);

    expect(() => runParity(APP, dir, PIN, 16)).toThrow(/15 of 16 fixtures/);
  });
});

/** A bundle shaped like `npm run build`'s, carrying `pin` and version 0.1.0. */
function fakeBundle(pin: object = PIN, dir = tempDir()): string {
  mkdirSync(join(dir, "assets"), { recursive: true });
  writeFileSync(
    join(dir, "index.html"),
    '<!doctype html><script type="module" src="/ciao-sun/assets/index-Ab1.js"></script>' +
      '<link rel="stylesheet" href="/ciao-sun/assets/index-Cd2.css">',
  );
  writeFileSync(join(dir, "assets/index-Ab1.js"), `const e=${JSON.stringify(pin)};`);
  writeFileSync(join(dir, "assets/index-Cd2.css"), "body{}");
  writeFileSync(
    join(dir, "sw.js"),
    `(function(){const p=${JSON.stringify(pin)};` +
      'const s={appVersion:"0.1.0",precache:["assets/index-Ab1.js","assets/index-Cd2.css","index.html"]};})();',
  );
  return dir;
}

describe("the bundle", () => {
  it("is index.html, sw.js and assets/, precached by sw.js and carrying the pin", () => {
    expect(checkBundle(fakeBundle(), PIN, "0.1.0")).toEqual([
      "assets/index-Ab1.js",
      "assets/index-Cd2.css",
      "index.html",
      "sw.js",
    ]);
  });

  it.each([
    ["a file outside assets/", (dir: string) => writeFileSync(join(dir, "stray.txt"), ""), /stray\.txt/],
    ["no sw.js", (dir: string) => rmSync(join(dir, "sw.js")), /sw\.js/],
    ["a file sw.js does not precache", (dir: string) => writeFileSync(join(dir, "assets/late-Ef3.js"), ""), /sw\.js does not precache assets\/late-Ef3\.js/],
    ["a page link to a missing file", (dir: string) => rmSync(join(dir, "assets/index-Cd2.css")), /index-Cd2\.css/],
  ])("is refused with %s", (_case, spoil, message) => {
    const dir = fakeBundle();
    spoil(dir);
    expect(() => checkBundle(dir, PIN, "0.1.0")).toThrow(message);
  });

  it("is refused when it was built with another pin or version", () => {
    const other = fakeBundle({ dataBase: "synthetic-data/", format: 1, build: "20261111a" });
    expect(() => checkBundle(other, PIN, "0.1.0")).toThrow(/sw\.js does not carry the pin .*https:\/\/data\.example\.invalid\//);
    expect(() => checkBundle(fakeBundle(), PIN, "0.2.0")).toThrow(/0\.2\.0/);
  });

  it("packs into a tarball to extract at /ciao-sun/, with a sha256sum line", () => {
    const dist = fakeBundle();
    const out = tempDir();

    const packed = pack(dist, checkBundle(dist, PIN, "0.1.0"), "0.1.0", out);

    expect(packed.tarball).toBe(join(out, "ciao-sun-0.1.0.tar.gz"));
    expect(packed.checksum).toBe(join(out, "ciao-sun-0.1.0.tar.gz.sha256"));
    const digest = createHash("sha256").update(readFileSync(packed.tarball)).digest("hex");
    expect(packed.sha256).toBe(digest);
    expect(readFileSync(packed.checksum, "utf8")).toBe(`${digest}  ciao-sun-0.1.0.tar.gz\n`);
    expect(execFileSync("shasum", ["-a", "256", "-c", "ciao-sun-0.1.0.tar.gz.sha256"], { cwd: out, encoding: "utf8" })).toMatch(/OK/);
    // The system tar reads it, and gives back the bundle byte for byte.
    const listing = execFileSync("tar", ["-tzf", packed.tarball], { encoding: "utf8" }).trim().split("\n");
    expect(listing).toEqual(["assets/", "assets/index-Ab1.js", "assets/index-Cd2.css", "index.html", "sw.js"]);
    const site = tempDir();
    execFileSync("tar", ["-xzf", packed.tarball, "-C", site]);
    expect(filesIn(site)).toEqual(filesIn(dist));
    for (const file of filesIn(dist)) expect(readFileSync(join(site, file)), file).toEqual(readFileSync(join(dist, file)));
  });

  it("built for real carries release.json and package.json's version, and is self-contained", { timeout: 120_000 }, () => {
    const dist = join(tempDir(), "bundle");

    viteBuild(APP, dist);

    const files = checkBundle(dist, checkPinShape(pin), pkg.version);
    expect(files).toContain("index.html");
    expect(files).toContain("sw.js");
    expect(files.filter((file) => file.startsWith("assets/maplibre-")).length).toBeGreaterThanOrEqual(3);
  });
});

describe("a release", () => {
  const options = (overrides: Partial<ReleaseOptions> = {}) => {
    const calls = { fetch: 0, build: 0 };
    const mirror = mirrorFetch(PIN.dataBase, SYNTHETIC);
    const outDir = join(tempDir(), "out");
    return {
      calls,
      outDir,
      options: {
        appDir: APP,
        tag: "ciao-sun-v0.1.0",
        version: "0.1.0",
        pinJson: PIN,
        outDir,
        fetch: (url: string) => (calls.fetch++, mirror(url)),
        buildBundle: (dist: string) => (calls.build++, void fakeBundle(PIN, dist)),
        ...overrides,
      } satisfies ReleaseOptions,
    };
  };
  const written = (dir: string) => (statSync(dir, { throwIfNoEntry: false }) ? filesIn(dir) : []);

  it("on a build whose fixtures all pass writes the tarball and its checksum", { timeout: 60_000 }, async () => {
    const { options: o, outDir } = options();

    const packed = await release(o);

    expect(written(outDir)).toEqual(["ciao-sun-0.1.0.tar.gz", "ciao-sun-0.1.0.tar.gz.sha256"]);
    expect(packed.sha256).toMatch(/^[0-9a-f]{64}$/);
  });

  it("on a failing fixture writes nothing and builds nothing", { timeout: 60_000 }, async () => {
    const { options: o, outDir, calls } = options({ fetch: mirrorFetch(PIN.dataBase, tamperedBuild()) });

    await expect(release(o)).rejects.toThrow(/parity tests failed/);

    expect(written(outDir)).toEqual([]);
    expect(calls.build).toBe(0);
  });

  it("is refused with the committed pin, before anything is fetched", async () => {
    const { options: o, outDir, calls } = options({ pinJson: pin });

    await expect(release(o)).rejects.toThrow(/dataBase "synthetic-data\/" is not an absolute https URL/);

    expect(calls).toEqual({ fetch: 0, build: 0 });
    expect(written(outDir)).toEqual([]);
  });

  it("is refused on a tag that is not the version, before anything is fetched", async () => {
    const { options: o, outDir, calls } = options({ tag: "ciao-sun-v0.2.0" });

    await expect(release(o)).rejects.toThrow(/tag ciao-sun-v0\.2\.0 is not app\/package\.json's version 0\.1\.0/);

    expect(calls).toEqual({ fetch: 0, build: 0 });
    expect(written(outDir)).toEqual([]);
  });

  it("is refused when the bundle does not carry the pin it tested", { timeout: 60_000 }, async () => {
    const { options: o, outDir } = options({
      buildBundle: (dist) => void fakeBundle({ ...PIN, build: "20261110a" }, dist),
    });

    await expect(release(o)).rejects.toThrow(/does not carry the pin/);

    expect(written(outDir)).toEqual([]);
  });
});
