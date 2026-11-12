// The built bundle's service worker (#52): `npm run build` writes `sw.js`
// beside `index.html`, and installing it precaches every file the build wrote
// (MapLibre's lazily loaded chunk, stylesheet and worker included) under the
// spec's cache names. The bundle is built for real, into a temporary
// directory, and `sw.js` is run against a fake worker global.

import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { runInNewContext } from "node:vm";

import { build } from "vite";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import pkg from "../../package.json";
import pin from "../../release.json";

const APP = resolve(import.meta.dirname, "../..");
const ORIGIN = "https://edbarker.dev";

let outDir: string;

function filesIn(dir: string): string[] {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(dir, join(entry.parentPath, entry.name)).split("\\").join("/"))
    .sort();
}

/** Run `sw.js` in a fresh global and let it install and activate; the caches it leaves. */
async function installBuiltWorker() {
  const stores = new Map<string, Map<string, Response>>([["ciao-sun-shell-0.0.1", new Map()]]);
  const listeners = new Map<string, (event: unknown) => void>();
  const fetchFile = async (input: Request | string) => {
    const url = new Request(input).url;
    const shellFile = url.startsWith(`${ORIGIN}/ciao-sun/`) && join(outDir, url.slice(`${ORIGIN}/ciao-sun/`.length));
    // Anything else is the data host: what it serves doesn't matter to which cache it goes in.
    return new Response(shellFile && existsSync(shellFile) ? readFileSync(shellFile) : "{}");
  };
  const cacheOf = (name: string) => {
    let entries = stores.get(name);
    if (!entries) stores.set(name, (entries = new Map()));
    const store = entries;
    return {
      match: async (request: Request | string) => store.get(new Request(request).url),
      put: async (request: Request | string, response: Response) => void store.set(new Request(request).url, response),
      addAll: async (urls: string[]) => {
        for (const url of urls) store.set(url, await fetchFile(url));
      },
    };
  };
  const self = {
    location: { href: `${ORIGIN}/ciao-sun/sw.js` },
    caches: {
      open: async (name: string) => cacheOf(name),
      keys: async () => [...stores.keys()],
      delete: async (name: string) => stores.delete(name),
    },
    fetch: fetchFile,
    skipWaiting: async () => {},
    clients: { claim: async () => {} },
    addEventListener: (type: string, fn: (event: unknown) => void) => void listeners.set(type, fn),
  };
  runInNewContext(readFileSync(join(outDir, "sw.js"), "utf8"), { self, URL, Request, Response, Promise, Set });
  for (const type of ["install", "activate"]) {
    const pending: Promise<unknown>[] = [];
    listeners.get(type)?.({ waitUntil: (p: Promise<unknown>) => void pending.push(p) });
    await Promise.all(pending);
  }
  /** Fetch `url` through the worker, as a page it controls would. */
  async function request(url: string): Promise<Response | undefined> {
    let responded: Promise<Response> | undefined;
    listeners.get("fetch")?.({
      request: new Request(url),
      respondWith: (p: Promise<Response>) => void (responded = p),
      waitUntil: () => {},
    });
    return responded;
  }
  return { stores, request };
}

beforeAll(async () => {
  outDir = mkdtempSync(join(tmpdir(), "ciao-sun-build-"));
  await build({ root: APP, logLevel: "silent", build: { outDir, emptyOutDir: true } });
}, 120_000);

afterAll(() => rmSync(outDir, { recursive: true, force: true }));

describe("the built service worker", () => {
  it("is sw.js at the bundle's root, beside index.html", () => {
    const files = filesIn(outDir);
    expect(files).toContain("sw.js");
    expect(files).toContain("index.html");
  });

  it("precaches every file the build wrote, MapLibre's chunk, stylesheet and worker included", async () => {
    const { stores } = await installBuiltWorker();
    const shell = stores.get(`ciao-sun-shell-${pkg.version}`);
    const precached = [...(shell?.keys() ?? [])].map((url) => url.slice(`${ORIGIN}/ciao-sun/`.length)).sort();
    expect(precached).toEqual(filesIn(outDir).filter((file) => file !== "sw.js"));
    for (const pattern of [/^index\.html$/, /^assets\/maplibre-.*\.js$/, /^assets\/maplibre-.*\.css$/, /^assets\/maplibre-gl-worker-.*\.mjs$/]) {
      expect(precached.some((file) => pattern.test(file)), String(pattern)).toBe(true);
    }
  });

  it("names its caches ciao-sun-shell-<appVersion> and ciao-sun-data-f<format>-<build>, and clears older ones", async () => {
    const { stores, request } = await installBuiltWorker();
    const dataCache = `ciao-sun-data-f${pin.format}-${pin.build}`;
    expect([...stores.keys()].sort()).toEqual([dataCache, `ciao-sun-shell-${pkg.version}`]);
    // A relative dataBase (the synthetic pin) resolves under /ciao-sun/, as the page resolves it.
    const tile = new URL(`f${pin.format}/${pin.build}/tiles/morning/ST5873.bin`, new URL(pin.dataBase, `${ORIGIN}/ciao-sun/`)).href;
    expect((await request(tile))?.status).toBe(200);
    expect([...(stores.get(dataCache)?.keys() ?? [])].map((url) => url.slice(url.lastIndexOf(pin.build)))).toEqual([
      `${pin.build}/manifest.json`,
      `${pin.build}/tiles/morning/ST5873.bin`,
    ]);
  });
});
