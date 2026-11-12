// The service worker, driven through its install, activate and fetch events
// with a fake Cache API and a fake network (spec #27, "Service worker"; #52).
//
// Seams under test (this ticket's): the worker's event handlers here; the
// page's registration and reload-on-foreground in `register.test.ts`; the
// built `sw.js` and its precache in `test/sw/build.test.ts`.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { type WorkerConfig, type WorkerScope, serveCiaoSun } from "./worker";

const SW_URL = "https://edbarker.dev/ciao-sun/sw.js";
const PIN = { dataBase: "https://data.example/", format: 1, build: "20261111a" };
const DATA = "https://data.example/f1/20261111a/";
const CONFIG: WorkerConfig = {
  appVersion: "0.2.0",
  precache: ["index.html", "assets/index-abc123.js", "assets/maplibre-def456.js"],
  pin: PIN,
};
const SHELL_CACHE = "ciao-sun-shell-0.2.0";
const DATA_CACHE = "ciao-sun-data-f1-20261111a";

const SYNTHETIC = resolve(import.meta.dirname, "../../../fixtures/synthetic/f1/20261111a");

class FakeCache {
  readonly entries = new Map<string, Response>();
  constructor(private readonly network: FakeNetwork) {}
  async match(request: Request | string, options?: { ignoreVary?: boolean }): Promise<Response | undefined> {
    void options;
    const stored = this.entries.get(new Request(request).url);
    const copy = stored?.clone();
    // The Cache API keeps a response's redirected flag; Node's clone() drops one set by a test.
    if (copy && stored?.redirected) Object.defineProperty(copy, "redirected", { value: true });
    return copy;
  }
  async put(request: Request | string, response: Response): Promise<void> {
    this.entries.set(new Request(request).url, response);
  }
  async addAll(requests: string[]): Promise<void> {
    const responses = await Promise.all(requests.map((url) => this.network.fetch(url)));
    if (responses.some((response) => !response.ok)) throw new TypeError("addAll: a request failed");
    requests.forEach((url, i) => this.entries.set(url, responses[i]!));
  }
}

class FakeCaches {
  readonly stores = new Map<string, FakeCache>();
  constructor(private readonly network: FakeNetwork) {}
  async open(name: string): Promise<FakeCache> {
    let cache = this.stores.get(name);
    if (!cache) this.stores.set(name, (cache = new FakeCache(this.network)));
    return cache;
  }
  async keys(): Promise<string[]> {
    return [...this.stores.keys()];
  }
  async delete(name: string): Promise<boolean> {
    return this.stores.delete(name);
  }
}

/** A host serving `files` (URL -> body); offline, every request fails. */
class FakeNetwork {
  offline = false;
  readonly requested: string[] = [];
  constructor(private readonly files: Record<string, BodyInit | (() => Response)>) {}
  fetch = async (input: Request | string): Promise<Response> => {
    const url = new Request(input).url;
    this.requested.push(url);
    if (this.offline) throw new TypeError("Failed to fetch");
    const file = this.files[url];
    if (file === undefined) return new Response("not found", { status: 404 });
    return typeof file === "function" ? file() : new Response(file);
  };
}

interface Listener {
  (event: unknown): void;
}

function worker(files: Record<string, BodyInit | (() => Response)> = {}) {
  const network = new FakeNetwork({
    "https://edbarker.dev/ciao-sun/index.html": "<!doctype html><title>Ciao Sun</title>",
    "https://edbarker.dev/ciao-sun/assets/index-abc123.js": "console.log('app')",
    "https://edbarker.dev/ciao-sun/assets/maplibre-def456.js": "console.log('map')",
    ...files,
  });
  const caches = new FakeCaches(network);
  const listeners = new Map<string, Listener>();
  const calls: string[] = [];
  const scope: WorkerScope = {
    location: { href: SW_URL },
    caches,
    fetch: network.fetch,
    skipWaiting: async () => void calls.push("skipWaiting"),
    clients: { claim: async () => void calls.push("claim") },
    addEventListener: (type: string, listener: (event: never) => void) => void listeners.set(type, listener as Listener),
  };
  serveCiaoSun(scope, CONFIG);

  async function lifecycle(type: "install" | "activate"): Promise<void> {
    const pending: Promise<unknown>[] = [];
    listeners.get(type)?.({ waitUntil: (p: Promise<unknown>) => void pending.push(p) });
    await Promise.all(pending);
  }

  /** The response the worker gives, or undefined when it leaves the request to the browser. */
  async function request(url: string, init: RequestInit & { mode?: RequestMode } = {}): Promise<Response | undefined> {
    const { mode, ...rest } = init;
    const req = new Request(url, rest);
    // Node's Request can't be built with mode "navigate"; the worker only reads it.
    if (mode) Object.defineProperty(req, "mode", { value: mode });
    let responded: Promise<Response> | undefined;
    const pending: Promise<unknown>[] = [];
    listeners.get("fetch")?.({
      request: req,
      respondWith: (p: Promise<Response>) => void (responded = p),
      waitUntil: (p: Promise<unknown>) => void pending.push(p),
    });
    const response = await responded;
    await Promise.all(pending);
    return response;
  }

  return { network, caches, calls, lifecycle, request };
}

describe("installing the worker", () => {
  it("precaches the shell into ciao-sun-shell-<appVersion> and takes over without waiting", async () => {
    const sw = worker();
    await sw.lifecycle("install");
    const shell = sw.caches.stores.get(SHELL_CACHE);
    expect([...(shell?.entries.keys() ?? [])].sort()).toEqual([
      "https://edbarker.dev/ciao-sun/assets/index-abc123.js",
      "https://edbarker.dev/ciao-sun/assets/maplibre-def456.js",
      "https://edbarker.dev/ciao-sun/index.html",
    ]);
    expect(sw.calls).toContain("skipWaiting");
  });

  // The first visit's page asks for the manifest before the worker controls it.
  it("stores the pinned build's manifest, so the first visit's answer opens offline", async () => {
    const sw = worker({ [`${DATA}manifest.json`]: '{"format":1}' });
    await sw.lifecycle("install");
    sw.network.offline = true;
    expect(await (await sw.request(`${DATA}manifest.json`))?.text()).toBe('{"format":1}');
  });

  it("still installs when the data host can't be reached", async () => {
    const sw = worker();
    await sw.lifecycle("install");
    expect(sw.caches.stores.get(SHELL_CACHE)?.entries.size).toBe(3);
    expect(sw.calls).toContain("skipWaiting");
  });
});

describe("activating the worker after a version bump", () => {
  it("deletes every other ciao-sun- cache, keeps every cache that isn't ciao-sun-, and claims the pages", async () => {
    const sw = worker();
    for (const name of [
      "ciao-sun-shell-0.1.0",
      "ciao-sun-data-f1-20250101a",
      "ciao-sun-data-f0-20261111a",
      DATA_CACHE,
      "other-app",
      "ciao-sunny",
      "sunspot-shell-0.1.0",
    ]) {
      await sw.caches.open(name);
    }
    await sw.lifecycle("install");
    await sw.lifecycle("activate");
    expect((await sw.caches.keys()).sort()).toEqual([DATA_CACHE, SHELL_CACHE, "ciao-sunny", "other-app", "sunspot-shell-0.1.0"]);
    expect(sw.calls).toContain("claim");
  });
});

describe("serving the shell", () => {
  it("opens the app offline from the precache, at /ciao-sun/ and at its assets", async () => {
    const sw = worker();
    await sw.lifecycle("install");
    await sw.lifecycle("activate");
    sw.network.offline = true;
    const page = await sw.request("https://edbarker.dev/ciao-sun/", { mode: "navigate" });
    expect(await page?.text()).toBe("<!doctype html><title>Ciao Sun</title>");
    const withQuery = await sw.request("https://edbarker.dev/ciao-sun/?from=home", { mode: "navigate" });
    expect(await withQuery?.text()).toBe("<!doctype html><title>Ciao Sun</title>");
    const map = await sw.request("https://edbarker.dev/ciao-sun/assets/maplibre-def456.js");
    expect(await map?.text()).toBe("console.log('map')");
  });

  // A host that redirects /ciao-sun/index.html to /ciao-sun/ hands install a
  // redirected response, which a browser refuses as the answer to a navigation.
  it("opens the app when the host redirected index.html while it was precached", async () => {
    const sw = worker({
      "https://edbarker.dev/ciao-sun/index.html": () => {
        const response = new Response("<!doctype html><title>Ciao Sun</title>");
        Object.defineProperty(response, "redirected", { value: true });
        return response;
      },
    });
    await sw.lifecycle("install");
    const page = await sw.request("https://edbarker.dev/ciao-sun/", { mode: "navigate" });
    expect(page?.redirected).toBe(false);
    expect(await page?.text()).toBe("<!doctype html><title>Ciao Sun</title>");
  });

  it("leaves the site's other pages to the browser", async () => {
    const sw = worker();
    await sw.lifecycle("install");
    expect(await sw.request("https://edbarker.dev/", { mode: "navigate" })).toBeUndefined();
    expect(await sw.request("https://edbarker.dev/blog/", { mode: "navigate" })).toBeUndefined();
    expect(await sw.request("https://edbarker.dev/ciao-sunny/", { mode: "navigate" })).toBeUndefined();
  });
});

describe("caching the pinned build as it is fetched", () => {
  const tile = readFileSync(`${SYNTHETIC}/tiles/morning/ST5873.bin`);
  const basemapTile = readFileSync(`${SYNTHETIC}/basemap/10/504/340.mvt`);
  const manifest = readFileSync(`${SYNTHETIC}/manifest.json`);

  function dataWorker() {
    return worker({
      [`${DATA}manifest.json`]: manifest,
      [`${DATA}tiles/morning/ST5873.bin`]: () => new Response(tile, { headers: { Vary: "Origin" } }),
      [`${DATA}basemap/10/504/340.mvt`]: basemapTile,
    });
  }

  it("stores a data tile's bytes exactly as the published gzip tile file", async () => {
    const sw = dataWorker();
    const online = await sw.request(`${DATA}tiles/morning/ST5873.bin`);
    expect(Buffer.from(await online!.arrayBuffer()).equals(tile)).toBe(true);
    const cached = await sw.caches.stores.get(DATA_CACHE)?.match(`${DATA}tiles/morning/ST5873.bin`);
    expect(Buffer.from(await cached!.arrayBuffer()).equals(tile)).toBe(true);
    expect(tile.subarray(0, 2)).toEqual(Buffer.from([0x1f, 0x8b])); // the published file is gzip
  });

  it("answers the manifest, data tiles and basemap tiles already fetched while offline", async () => {
    const sw = dataWorker();
    for (const path of ["manifest.json", "tiles/morning/ST5873.bin", "basemap/10/504/340.mvt"]) await sw.request(DATA + path);
    sw.network.offline = true;
    const requestedOnline = sw.network.requested.length;
    expect(await (await sw.request(`${DATA}manifest.json`))?.text()).toBe(manifest.toString());
    expect(Buffer.from(await (await sw.request(`${DATA}tiles/morning/ST5873.bin`))!.arrayBuffer()).equals(tile)).toBe(true);
    const basemap = await sw.request(`${DATA}basemap/10/504/340.mvt`);
    expect(Buffer.from(await basemap!.arrayBuffer()).equals(basemapTile)).toBe(true);
    expect(sw.network.requested.length).toBe(requestedOnline); // nothing went to the network
  });

  it("doesn't store a failed response, so the tile is asked for again", async () => {
    const sw = dataWorker();
    const missing = await sw.request(`${DATA}tiles/morning/ST9999.bin`);
    expect(missing?.status).toBe(404);
    expect(await sw.caches.stores.get(DATA_CACHE)?.match(`${DATA}tiles/morning/ST9999.bin`)).toBeUndefined();
  });

  it("leaves another build's files to the browser", async () => {
    const sw = dataWorker();
    expect(await sw.request("https://data.example/f1/20250101a/tiles/morning/ST5873.bin")).toBeUndefined();
    expect(await sw.request("https://data.example/f2/20261111a/manifest.json")).toBeUndefined();
  });
});

describe("the forecast", () => {
  it("goes straight to the network and into neither cache", async () => {
    const forecast = "https://api.open-meteo.com/v1/forecast?latitude=51.45&longitude=-2.6&hourly=cloud_cover";
    const sw = worker({ [forecast]: '{"hourly":{}}' });
    await sw.lifecycle("install");
    await sw.lifecycle("activate");
    expect(await sw.request(forecast)).toBeUndefined();
    for (const cache of sw.caches.stores.values()) expect(await cache.match(forecast)).toBeUndefined();
  });
});

describe("a relative dataBase", () => {
  it("resolves against the worker's scope, as the page resolves it", async () => {
    const network = new FakeNetwork({ "https://edbarker.dev/ciao-sun/synthetic-data/f1/20261111a/manifest.json": "{}" });
    const caches = new FakeCaches(network);
    let onFetch: Listener | undefined;
    serveCiaoSun(
      {
        location: { href: SW_URL },
        caches,
        fetch: network.fetch,
        skipWaiting: async () => {},
        clients: { claim: async () => {} },
        addEventListener: (type: string, listener: (event: never) => void) => void (type === "fetch" && (onFetch = listener as Listener)),
      },
      { ...CONFIG, pin: { ...PIN, dataBase: "synthetic-data/" } },
    );
    let responded: Promise<Response> | undefined;
    onFetch?.({
      request: new Request("https://edbarker.dev/ciao-sun/synthetic-data/f1/20261111a/manifest.json"),
      respondWith: (p: Promise<Response>) => void (responded = p),
      waitUntil: () => {},
    });
    expect(await (await responded)?.text()).toBe("{}");
    expect(caches.stores.has(DATA_CACHE)).toBe(true);
  });
});
