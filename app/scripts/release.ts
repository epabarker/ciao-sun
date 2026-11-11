// The release job (#54; spec #27, "Release and CI"). The tag workflow,
// `.github/workflows/release.yml`, runs this from `app/` on a `ciao-sun-v*`
// tag and attaches what it writes to the GitHub release; nothing else does.
// Run by Node as TypeScript (type stripping), so it names its imports with
// `.ts`, imports only types from `src/` and `test/` (values only from the
// import-free `src/ids.ts`), and reads JSON with fs.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import { parseArgs } from "node:util";
import { gzipSync } from "node:zlib";

import type { ReleaseConfig } from "../src/config/release.ts";
import { BUILD_ID, GRID_REF } from "../src/ids.ts";

export class ReleaseRefused extends Error {
  override name = "ReleaseRefused";
}

const TAG = /^ciao-sun-v(\d+\.\d+\.\d+)$/;

/** The version a tag releases: `ciao-sun-v<x.y.z>`, equal to `package.json`'s `version`. */
export function checkTag(tag: string, version: string): string {
  const match = TAG.exec(tag);
  if (!match) {
    throw new ReleaseRefused(`tag ${JSON.stringify(tag)} is not ciao-sun-v<x.y.z>`);
  }
  if (match[1] !== version) {
    throw new ReleaseRefused(
      `tag ${tag} is not app/package.json's version ${version}: the shell cache is named for that version, ` +
        "so bump it (npm version --no-git-tag-version <x.y.z>) and tag that commit",
    );
  }
  return version;
}

/** `release.json` as the app reads it (`src/config/release.ts`): any non-empty `dataBase`. */
export function checkPinShape(json: unknown): ReleaseConfig {
  const { dataBase, format, build } = (json ?? {}) as Record<string, unknown>;
  if (typeof dataBase !== "string" || dataBase === "") {
    throw new ReleaseRefused("release.json: dataBase must be a non-empty URL");
  }
  if (typeof format !== "number" || !Number.isInteger(format) || format < 1) {
    throw new ReleaseRefused("release.json: format must be a positive integer");
  }
  if (typeof build !== "string" || !BUILD_ID.test(build)) {
    throw new ReleaseRefused('release.json: build must be a build id like "20261111a"');
  }
  return { dataBase, format, build };
}

/** `release.json`, if it pins a build the site can fetch: an absolute https `dataBase`. */
export function checkPin(json: unknown): ReleaseConfig {
  const { dataBase, format, build } = checkPinShape(json);
  if (!URL.canParse(dataBase) || new URL(dataBase).protocol !== "https:") {
    throw new ReleaseRefused(
      `release.json: dataBase ${JSON.stringify(dataBase)} is not an absolute https URL. ` +
        "A relative dataBase (the committed synthetic build) is only served by the dev and preview servers; " +
        "pin the published build on the data subdomain (docs/data-refresh.md)",
    );
  }
  return { dataBase, format, build };
}

export type FetchLike = (url: string) => Promise<Response>;

/** `<dataBase>/f<format>/<build>/`, joined as the app's loader does (`src/loader/loader.ts`). */
export function buildUrl(pin: ReleaseConfig): string {
  const dataBase = pin.dataBase.endsWith("/") ? pin.dataBase : `${pin.dataBase}/`;
  return new URL(`f${pin.format}/${pin.build}/`, dataBase).href;
}

/**
 * A fetch that answers URLs under `dataBase` from `dir`, a directory in the
 * hosted layout, and 404s everything else: for rehearsing a release locally
 * (`--mirror`), and for the tests. The workflow never uses it.
 */
export function mirrorFetch(dataBase: string, dir: string): FetchLike {
  const prefix = dataBase.endsWith("/") ? dataBase : `${dataBase}/`;
  const root = resolve(dir);
  return async (url) => {
    const file = url.startsWith(prefix) ? resolve(root, decodeURIComponent(url.slice(prefix.length))) : "";
    if (!file.startsWith(root + sep) || !statSync(file, { throwIfNoEntry: false })?.isFile()) {
      return new Response(null, { status: 404 });
    }
    return new Response(readFileSync(file));
  };
}

const FIXTURE_FILE = /^[a-z0-9]+(-[a-z0-9]+)*\.json$/;

interface IndexEntry {
  file: unknown;
  tiles: unknown;
}

export interface Downloaded {
  /** `<dir>/f<format>/<build>`: the build directory in the hosted layout. */
  buildDir: string;
  fixtures: number;
  tiles: number;
}

/**
 * The pinned build's manifest, `fixtures/index.json`, every fixture and the
 * tiles they name, written byte for byte under `dir` in the hosted layout
 * (docs/fixtures.md). The manifest comes first: `publish` uploads it last, so
 * a build with one is whole.
 */
export async function downloadBuild(pin: ReleaseConfig, fetch: FetchLike, dir: string): Promise<Downloaded> {
  const url = buildUrl(pin);
  const buildDir = join(dir, `f${pin.format}`, pin.build);
  const get = async (path: string): Promise<Uint8Array> => {
    let response: Response;
    try {
      response = await fetch(url + path);
    } catch (cause) {
      throw new ReleaseRefused(`${url}${path}: ${String(cause)}`, { cause });
    }
    if (!response.ok) {
      const whole = path === "manifest.json" ? ": the pinned build is not published, or not a whole build" : "";
      throw new ReleaseRefused(`${url}${path}: HTTP ${response.status}${whole}`);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    mkdirSync(dirname(join(buildDir, path)), { recursive: true });
    writeFileSync(join(buildDir, path), bytes);
    return bytes;
  };
  const json = async <T>(path: string): Promise<T> => {
    const document = JSON.parse(new TextDecoder().decode(await get(path))) as T & { format: unknown; build: unknown };
    if (document.format !== pin.format || document.build !== pin.build) {
      throw new ReleaseRefused(
        `${path} is f${String(document.format)}/${String(document.build)}, not the pinned f${pin.format}/${pin.build}`,
      );
    }
    return document;
  };

  await json<object>("manifest.json");
  const index = await json<{ fixtures: unknown }>("fixtures/index.json");
  if (!Array.isArray(index.fixtures) || index.fixtures.length === 0) {
    throw new ReleaseRefused("fixtures/index.json lists no fixtures");
  }
  const entries = index.fixtures as IndexEntry[];
  const files: string[] = [];
  const tiles = new Set<string>();
  for (const { file, tiles: names } of entries) {
    if (typeof file !== "string" || !FIXTURE_FILE.test(file) || file === "index.json") {
      throw new ReleaseRefused(`fixtures/index.json: ${JSON.stringify(file)} is not a fixture file name`);
    }
    files.push(file);
    for (const gridRef of Array.isArray(names) ? names : [names]) {
      if (typeof gridRef !== "string" || !GRID_REF.test(gridRef)) {
        throw new ReleaseRefused(`fixtures/index.json: ${JSON.stringify(gridRef)} is not a grid ref`);
      }
      tiles.add(gridRef);
    }
  }
  for (const file of files) await get(`fixtures/${file}`);
  for (const gridRef of [...tiles].sort()) await get(`tiles/${gridRef}.bin`);
  return { buildDir, fixtures: files.length, tiles: tiles.size };
}

/** The golden-fixture harness; its per-fixture Answer test is named by `ANSWER_TEST`. */
const HARNESS = "test/parity/fixtures.test.ts";
const ANSWER_TEST = "has the reference's Answer";

interface VitestReport {
  success: boolean;
  numTotalTests: number;
  numFailedTests: number;
  numPendingTests: number;
  numTodoTests: number;
  testResults: { assertionResults: { ancestorTitles: string[]; title: string; status: string }[] }[];
}

/**
 * Runs the golden-fixture harness (`test/parity/fixtures.test.ts`) over the
 * build downloaded into `dataBaseDir`, and refuses unless every test passed,
 * none was skipped, and the JS's Answer was checked for each of the
 * `fixtures` the index listed.
 */
export function runParity(
  appDir: string,
  dataBaseDir: string,
  pin: ReleaseConfig,
  fixtures: number,
  echo = false,
): { fixtures: number; tests: number } {
  const report = join(dataBaseDir, "parity-report.json");
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith("VITEST")));
  const run = spawnSync(
    process.execPath,
    [
      join(appDir, "node_modules/vitest/vitest.mjs"),
      "run",
      HARNESS,
      "--reporter=default",
      "--reporter=json",
      `--outputFile.json=${report}`,
    ],
    {
      cwd: appDir,
      stdio: echo ? ["ignore", "inherit", "inherit"] : "ignore",
      env: {
        ...env,
        CIAO_SUN_FIXTURES_DATA_BASE: dataBaseDir,
        CIAO_SUN_FIXTURES_BUILD: pin.build,
        CIAO_SUN_FIXTURES_FORMAT: String(pin.format),
      },
    },
  );
  if (!existsSync(report)) {
    throw new ReleaseRefused(`the parity run wrote no report (exit ${run.status ?? run.signal})`);
  }
  const result = JSON.parse(readFileSync(report, "utf8")) as VitestReport;
  const suite = `golden fixtures of build f${pin.format}/${pin.build}`;
  const tests = result.testResults.flatMap((file) => file.assertionResults);
  if (result.numFailedTests > 0 || !result.success || run.status !== 0) {
    throw new ReleaseRefused(`${result.numFailedTests} of ${result.numTotalTests} parity tests failed over ${suite}`);
  }
  if (result.numPendingTests + result.numTodoTests > 0) {
    throw new ReleaseRefused(`${result.numPendingTests + result.numTodoTests} parity tests were skipped over ${suite}`);
  }
  const answers = tests.filter(
    (test) => test.ancestorTitles[0] === suite && test.title === ANSWER_TEST && test.status === "passed",
  ).length;
  if (answers !== fixtures) {
    throw new ReleaseRefused(`the JS Answer was checked for ${answers} of ${fixtures} fixtures of ${suite}`);
  }
  return { fixtures, tests: result.numTotalTests };
}

/** Every file under `dir`, relative, with "/" separators, sorted. */
function filesIn(dir: string): string[] {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => !entry.isDirectory())
    .map((entry) => relative(dir, join(entry.parentPath, entry.name)).split(sep).join("/"))
    .sort();
}

const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** A JS string literal of `value`, in any of the minifier's quotes. */
const literal = (value: string) => ["`", '"', "'"].map((q) => `${q}${escape(value)}${q}`).join("|").replace(/^/, "(?:") + ")";
/** An object key, quoted or not, and its colon. */
const key = (name: string) => `["']?${name}["']?\\s*:\\s*`;

const hasLiteral = (source: string, pattern: string) => new RegExp(pattern).test(source);

/**
 * The files of a built bundle (`npm run build`'s `dist/`), if it is the
 * self-contained bundle of this release: only `index.html`, `sw.js` and
 * `assets/`; every file the page links under `/ciao-sun/` present; every file
 * but `sw.js` in the worker's precache; and the pin and version it was tested
 * with in both `sw.js` and the page's script. Else refused.
 */
export function checkBundle(distDir: string, pin: ReleaseConfig, version: string): string[] {
  if (!statSync(distDir, { throwIfNoEntry: false })?.isDirectory()) {
    throw new ReleaseRefused(`no bundle at ${distDir}`);
  }
  const files = filesIn(distDir);
  const stray = files.filter((file) => file !== "index.html" && file !== "sw.js" && !/^assets\/[^/]+$/.test(file));
  if (stray.length > 0) {
    throw new ReleaseRefused(`the bundle holds files outside index.html, sw.js and assets/: ${stray.join(", ")}`);
  }
  for (const required of ["index.html", "sw.js"]) {
    if (!files.includes(required)) throw new ReleaseRefused(`the bundle has no ${required}`);
  }
  const read = (file: string) => readFileSync(join(distDir, file), "utf8");
  const page = read("index.html");
  const linked = [...page.matchAll(/(?:src|href)="\/ciao-sun\/([^"?#]+)"/g)].map((match) => match[1]!);
  const missing = linked.filter((file) => !files.includes(file));
  if (linked.length === 0 || missing.length > 0) {
    throw new ReleaseRefused(`index.html links files the bundle lacks: ${missing.join(", ") || "it links none"}`);
  }
  const sw = read("sw.js");
  const unprecached = files.filter((file) => file !== "sw.js" && !hasLiteral(sw, literal(file)));
  if (unprecached.length > 0) {
    throw new ReleaseRefused(`sw.js does not precache ${unprecached.join(", ")}`);
  }
  const pinned =
    `${key("dataBase")}${literal(pin.dataBase)}\\s*,\\s*${key("format")}${pin.format}\\s*,\\s*` +
    `${key("build")}${literal(pin.build)}`;
  const scripts = linked.filter((file) => file.endsWith(".js"));
  for (const [file, source] of [["sw.js", sw], ...scripts.map((file) => [file, read(file)])] as const) {
    if (!hasLiteral(source, pinned)) {
      throw new ReleaseRefused(
        `${file} does not carry the pin ${JSON.stringify(pin)}: rebuild after editing release.json`,
      );
    }
  }
  if (!hasLiteral(sw, `${key("appVersion")}${literal(version)}`)) {
    throw new ReleaseRefused(`sw.js is not version ${version}: rebuild after bumping package.json`);
  }
  return files;
}

/** One ustar header block for `name`. */
function tarHeader(name: string, size: number, mtime: number, directory: boolean): Buffer {
  if (Buffer.byteLength(name) > 100) throw new ReleaseRefused(`${name}: a bundle path longer than 100 bytes`);
  const header = Buffer.alloc(512);
  const field = (offset: number, length: number, value: string) => header.write(value, offset, length, "utf8");
  const octal = (offset: number, length: number, value: number) =>
    field(offset, length, `${value.toString(8).padStart(length - 1, "0")}\0`);
  field(0, 100, name);
  octal(100, 8, directory ? 0o755 : 0o644);
  octal(108, 8, 0);
  octal(116, 8, 0);
  octal(124, 12, size);
  octal(136, 12, mtime);
  field(148, 8, " ".repeat(8));
  field(156, 1, directory ? "5" : "0");
  field(257, 8, "ustar\u000000");
  let sum = 0;
  for (const byte of header) sum += byte;
  field(148, 8, `${sum.toString(8).padStart(6, "0")}\0 `);
  return header;
}

export interface Packed {
  tarball: string;
  checksum: string;
  sha256: string;
}

/**
 * Writes `ciao-sun-<version>.tar.gz` (the bundle's `files`, at the top level:
 * extract it into the site's `/ciao-sun/`) and `ciao-sun-<version>.tar.gz.sha256`
 * (one `sha256sum` line) into `outDir`.
 */
export function pack(distDir: string, files: readonly string[], version: string, outDir: string): Packed {
  const mtime = Math.floor(Date.now() / 1000);
  const blocks: Buffer[] = [];
  const directories = new Set<string>();
  for (const file of files) {
    const parent = file.includes("/") ? `${file.slice(0, file.lastIndexOf("/"))}/` : "";
    if (parent && !directories.has(parent)) {
      directories.add(parent);
      blocks.push(tarHeader(parent, 0, mtime, true));
    }
    const bytes = readFileSync(join(distDir, file));
    blocks.push(tarHeader(file, bytes.length, mtime, false), bytes, Buffer.alloc((512 - (bytes.length % 512)) % 512));
  }
  blocks.push(Buffer.alloc(1024));
  const name = `ciao-sun-${version}.tar.gz`;
  const gz = gzipSync(Buffer.concat(blocks), { level: 9 });
  const sha256 = createHash("sha256").update(gz).digest("hex");
  mkdirSync(outDir, { recursive: true });
  const tarball = join(outDir, name);
  const checksum = `${tarball}.sha256`;
  writeFileSync(tarball, gz);
  writeFileSync(checksum, `${sha256}  ${name}\n`);
  return { tarball, checksum, sha256 };
}

/** `npm run build`, into `distDir` rather than `dist/`. */
export function viteBuild(appDir: string, distDir: string, echo = false): void {
  const run = spawnSync(
    process.execPath,
    [join(appDir, "node_modules/vite/bin/vite.js"), "build", "--outDir", distDir, "--emptyOutDir"],
    { cwd: appDir, stdio: echo ? ["ignore", "inherit", "inherit"] : ["ignore", "ignore", "pipe"], encoding: "utf8" },
  );
  if (run.status !== 0) {
    throw new ReleaseRefused(`the bundle did not build (exit ${run.status ?? run.signal})${run.stderr ? `:\n${run.stderr}` : ""}`);
  }
}

export interface ReleaseOptions {
  /** `app/`, with its dependencies installed. */
  appDir: string;
  /** The pushed tag, e.g. `ciao-sun-v0.1.0`. */
  tag: string;
  /** `app/package.json`'s `version`. */
  version: string;
  /** `app/release.json`, parsed. */
  pinJson: unknown;
  /** Where the tarball and its checksum go; nothing is written there unless the release passes. */
  outDir: string;
  /** Reaches the data host. */
  fetch: FetchLike;
  /** Builds the bundle into the directory given. */
  buildBundle?: (distDir: string) => void;
  log?: (line: string) => void;
}

/**
 * The release, in order, stopping at the first refusal: the tag names the
 * app's version; the pin names an https data host; the pinned build's
 * fixtures and their tiles download; the JS passes every fixture; the bundle
 * builds and carries that pin and version; then, and only then, the tarball
 * and its SHA-256 are written to `outDir`.
 */
export async function release(options: ReleaseOptions): Promise<Packed> {
  const log = options.log ?? (() => {});
  // The harness's and Vite's own output is shown only when the release is logged (the command line).
  const echo = options.log !== undefined;
  const buildBundle = options.buildBundle ?? ((dist: string) => viteBuild(options.appDir, dist, echo));
  const version = checkTag(options.tag, options.version);
  log(`tag ${options.tag}: version ${version}`);
  const pin = checkPin(options.pinJson);
  log(`pin: f${pin.format}/${pin.build} at ${pin.dataBase}`);
  const work = mkdtempSync(join(tmpdir(), "ciao-sun-release-"));
  try {
    const downloaded = await downloadBuild(pin, options.fetch, join(work, "data-host"));
    log(`downloaded ${downloaded.fixtures} fixtures and ${downloaded.tiles} tiles from ${buildUrl(pin)}`);
    const parity = runParity(options.appDir, join(work, "data-host"), pin, downloaded.fixtures, echo);
    log(`parity: ${parity.tests} tests passed over ${parity.fixtures} fixtures`);
    const dist = join(work, "bundle");
    buildBundle(dist);
    const files = checkBundle(dist, pin, version);
    log(`bundle: ${files.length} files, carrying the pin and version ${version}`);
    const packed = pack(dist, files, version, options.outDir);
    log(`wrote ${packed.tarball}\nwrote ${packed.checksum}\nsha256 ${packed.sha256}`);
    return packed;
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
}

const USAGE = "usage: node scripts/release.ts --tag ciao-sun-v<x.y.z> --out <dir> [--mirror <dir>]";

/** The command line: `app/` is this script's parent directory. */
async function main(argv: string[]): Promise<number> {
  const { values } = parseArgs({
    args: argv,
    options: { tag: { type: "string" }, out: { type: "string" }, mirror: { type: "string" } },
    strict: true,
  });
  if (!values.tag || !values.out) {
    console.error(USAGE);
    return 2;
  }
  const appDir = resolve(import.meta.dirname, "..");
  const pinJson: unknown = JSON.parse(readFileSync(join(appDir, "release.json"), "utf8"));
  const { version } = JSON.parse(readFileSync(join(appDir, "package.json"), "utf8")) as { version: string };
  let fetch: FetchLike = (url) => globalThis.fetch(url);
  if (values.mirror) {
    // A rehearsal: the pin must still be an https host, but its files come from a local directory.
    const { dataBase } = checkPinShape(pinJson);
    fetch = mirrorFetch(dataBase, values.mirror);
    console.log(`rehearsal: reading ${dataBase} from ${resolve(values.mirror)}`);
  }
  try {
    await release({ appDir, tag: values.tag, version, pinJson, outDir: resolve(values.out), fetch, log: console.log });
  } catch (error) {
    if (!(error instanceof ReleaseRefused)) throw error;
    console.error(`release refused: ${error.message}`);
    return 1;
  }
  console.log("release ready");
  return 0;
}

if (import.meta.main) process.exitCode = await main(process.argv.slice(2));
