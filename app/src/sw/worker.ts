// The service worker's behaviour (spec #27, "Service worker"; #52). `entry.ts`
// installs it into the real worker global; the build writes that as
// `/ciao-sun/sw.js` with this release's precache list (`vite-sw.ts`).
//
// - install: precache the shell (`index.html` and every hashed asset of the
//   build, MapLibre's chunk, stylesheet and worker included) into
//   `ciao-sun-shell-<appVersion>`, and the pinned build's manifest if the data
//   host answers (the first visit asked for it before the worker was there),
//   then `skipWaiting`.
// - activate: delete every other `ciao-sun-*` cache, none that isn't one, then
//   `clients.claim`. The page reloads on its next foreground (`register.ts`).
// - fetch:
//   - a navigation inside the scope gets the precached `index.html`, and a
//     shell file its precached copy; either falls back to the network;
//   - a file of the pinned build (`<dataBase>/f<format>/<build>/...`: the
//     manifest, data tiles, basemap tiles) comes from
//     `ciao-sun-data-f<format>-<build>`, else from the network and is stored
//     there exactly as it came (a build is immutable, ADR 0002);
//   - everything else (the forecast, another build, the site's other pages)
//     is left to the browser and stored nowhere.

import type { ReleaseConfig } from "../config/release";
import { buildUrl } from "../loader/loader";

export interface WorkerConfig {
  /** `package.json`'s version: names the shell cache. */
  appVersion: string;
  /** The shell's files, relative to the worker's URL: `index.html`, `assets/...`. */
  precache: string[];
  /** The release's pin: which build's files are cached, and under what name. */
  pin: ReleaseConfig;
}

/** What the worker uses of a cache: the parts of the Cache API it calls. */
export interface CacheLike {
  match(request: Request | string, options?: { ignoreVary?: boolean }): Promise<Response | undefined>;
  put(request: Request | string, response: Response): Promise<void>;
  addAll(requests: string[]): Promise<void>;
}

/** What the worker uses of its global scope; the real one is `self`. */
export interface WorkerScope {
  location: { href: string };
  caches: {
    open(name: string): Promise<CacheLike>;
    keys(): Promise<string[]>;
    delete(name: string): Promise<boolean>;
  };
  fetch(request: Request): Promise<Response>;
  skipWaiting(): Promise<void>;
  clients: { claim(): Promise<void> };
  // The listener's event is the platform's ExtendableEvent or FetchEvent.
  addEventListener(type: string, listener: (event: never) => void): void;
}

interface ExtendableEventLike {
  waitUntil(promise: Promise<unknown>): void;
}

interface FetchEventLike extends ExtendableEventLike {
  request: Request;
  respondWith(response: Promise<Response>): void;
}

const PREFIX = "ciao-sun-";

export function shellCacheName(appVersion: string): string {
  return `${PREFIX}shell-${appVersion}`;
}

export function dataCacheName(pin: Pick<ReleaseConfig, "format" | "build">): string {
  return `${PREFIX}data-f${pin.format}-${pin.build}`;
}

export function serveCiaoSun(scope: WorkerScope, config: WorkerConfig): void {
  const shellCache = shellCacheName(config.appVersion);
  const dataCache = dataCacheName(config.pin);
  const appScope = new URL("./", scope.location.href).href;
  const indexUrl = new URL("index.html", scope.location.href).href;
  const shellUrls = new Set(config.precache.map((path) => new URL(path, scope.location.href).href));
  const dataPrefix = buildUrl(config.pin, scope.location.href);

  scope.addEventListener("install", (event: ExtendableEventLike) => {
    event.waitUntil(
      (async () => {
        const cache = await scope.caches.open(shellCache);
        await cache.addAll([...shellUrls]);
        // The first visit's page fetched the manifest before this worker controlled it.
        await fromData(new Request(`${dataPrefix}manifest.json`)).catch(() => {}); // fetched again when online
        await scope.skipWaiting();
      })(),
    );
  });

  scope.addEventListener("activate", (event: ExtendableEventLike) => {
    event.waitUntil(
      (async () => {
        const names = await scope.caches.keys();
        const stale = names.filter((name) => name.startsWith(PREFIX) && name !== shellCache && name !== dataCache);
        await Promise.all(stale.map((name) => scope.caches.delete(name)));
        await scope.clients.claim();
      })(),
    );
  });

  async function fromShell(request: Request, url: string): Promise<Response> {
    const cached = await (await scope.caches.open(shellCache)).match(url);
    if (!cached) return scope.fetch(request);
    // A host that redirected index.html while it was precached left a response
    // a browser refuses as a navigation's answer; the same page, unredirected.
    if (cached.redirected) {
      return new Response(cached.body, { status: cached.status, statusText: cached.statusText, headers: cached.headers });
    }
    return cached;
  }

  async function fromData(request: Request): Promise<Response> {
    const cache = await scope.caches.open(dataCache);
    // A build's files never change, so the Vary (R2 sends Origin) can't matter.
    const cached = await cache.match(request, { ignoreVary: true });
    if (cached) return cached;
    const response = await scope.fetch(request);
    if (response.status === 200) await cache.put(request, response.clone());
    return response;
  }

  scope.addEventListener("fetch", (event: FetchEventLike) => {
    const { request } = event;
    if (request.method !== "GET") return;
    const url = request.url.split("#")[0]!;
    if (request.mode === "navigate") {
      if (url.startsWith(appScope)) event.respondWith(fromShell(request, indexUrl));
    } else if (shellUrls.has(url)) {
      event.respondWith(fromShell(request, url));
    } else if (url.startsWith(dataPrefix)) {
      event.respondWith(fromData(request));
    }
  });
}
