// `sw.js`: the service worker in the browser. The build (`vite-sw.ts`) bundles
// this into one classic script and defines `__CIAO_SUN_SW__` as this
// release's version and precache list; the pin comes from `release.json`.

import { RELEASE } from "../config/release";
import { type WorkerScope, serveCiaoSun } from "./worker";

declare const __CIAO_SUN_SW__: { appVersion: string; precache: string[] };
declare const self: WorkerScope;

serveCiaoSun(self, { ...__CIAO_SUN_SW__, pin: RELEASE });
