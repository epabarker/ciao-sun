// Writes `sw.js` into the bundle (#52): `src/sw/entry.ts` built as one classic
// script under a fixed name, carrying `package.json`'s version and the list of
// every file this build wrote, which the worker precaches. It runs after
// Vite's own output, `index.html` included, so the list is the build's, not a
// hand-kept one; a build without `index.html` or MapLibre's chunk, stylesheet
// and worker fails rather than ship a worker that can't open the app offline.

import { resolve } from "node:path";

import { type Plugin, build } from "vite";

import pkg from "./package.json" with { type: "json" };

export const SW_FILE = "sw.js";

/** Files the shell can't open offline without. */
const REQUIRED = [/^index\.html$/, /^assets\/maplibre-[^/]+\.js$/, /^assets\/maplibre-[^/]+\.css$/, /^assets\/maplibre-gl-worker-[^/]+\.mjs$/];

export function serviceWorker(): Plugin {
  let root = "";
  return {
    name: "ciao-sun-service-worker",
    apply: "build",
    configResolved: (config) => void (root = config.root),
    generateBundle: {
      order: "post",
      async handler(_, bundle) {
        const precache = Object.keys(bundle)
          .filter((file) => !file.endsWith(".map") && file !== SW_FILE)
          .sort();
        const missing = REQUIRED.filter((pattern) => !precache.some((file) => pattern.test(file)));
        if (missing.length > 0) this.error(`the shell precache lacks ${missing.join(", ")}`);
        const output = await build({
          configFile: false,
          root,
          logLevel: "warn",
          define: { __CIAO_SUN_SW__: JSON.stringify({ appVersion: pkg.version, precache }) },
          build: {
            write: false,
            copyPublicDir: false,
            lib: { entry: resolve(root, "src/sw/entry.ts"), formats: ["iife"], name: "ciaoSunServiceWorker", fileName: () => SW_FILE },
          },
        });
        const chunks = (Array.isArray(output) ? output : [output]).flatMap((o) => ("output" in o ? o.output : []));
        const sw = chunks.find((chunk) => chunk.fileName === SW_FILE);
        if (!sw || sw.type !== "chunk" || chunks.length !== 1) this.error(`the service worker didn't build as one ${SW_FILE}`);
        this.emitFile({ type: "asset", fileName: SW_FILE, source: sw.code });
      },
    },
  };
}
