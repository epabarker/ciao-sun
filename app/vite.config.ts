import { createReadStream, statSync } from "node:fs";
import { resolve, sep } from "node:path";

import type { Connect, Plugin } from "vite";
import { defineConfig } from "vitest/config";

const BASE = "/ciao-sun/";

/**
 * Serves the committed synthetic build at /ciao-sun/synthetic-data/ in
 * `npm run dev` and `vite preview`, as a data host would: the pin in
 * release.json names it until the first Bristol build is published (#55).
 * The bundle itself carries no data.
 */
function syntheticData(): Plugin {
  const root = resolve(import.meta.dirname, "../fixtures/synthetic");
  const prefix = `${BASE}synthetic-data/`;
  const serve: Connect.NextHandleFunction = (req, res, next) => {
    const path = decodeURIComponent((req.url ?? "").split("?")[0]!);
    if (!path.startsWith(prefix)) return next();
    const file = resolve(root, path.slice(prefix.length));
    if (!file.startsWith(root + sep) || !statSync(file, { throwIfNoEntry: false })?.isFile()) {
      res.statusCode = 404;
      res.end();
      return;
    }
    res.setHeader("Content-Type", file.endsWith(".json") ? "application/json" : "application/octet-stream");
    createReadStream(file).pipe(res);
  };
  return {
    name: "ciao-sun-synthetic-data",
    configureServer: (server) => void server.middlewares.use(serve),
    configurePreviewServer: (server) => void server.middlewares.use(serve),
  };
}

export default defineConfig({
  // The bundle is served under /ciao-sun/ (spec #27, "Client app").
  base: BASE,
  plugins: [syntheticData()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // MapLibre (with the basemap style) is one lazily loaded chunk of about 1.1 MB.
    chunkSizeWarningLimit: 1200,
  },
  test: {
    // Node by default; a rendering test opts into happy-dom with
    // `// @vitest-environment happy-dom` on its first line.
    environment: "node",
    include: ["src/**/*.test.ts", "test/**/*.test.ts"],
  },
});
