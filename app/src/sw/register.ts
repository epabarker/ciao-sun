// The page's side of the service worker (spec #27, "Service worker"; #52).
//
// - Registers `<base>sw.js` with the scope `<base>` (`/ciao-sun/`), so it
//   never controls the site's other pages (story 74).
// - A new worker calls `skipWaiting` and `clients.claim` (`worker.ts`), so it
//   takes over the page in use. The page stays as it is and reloads silently
//   the next time it comes to the foreground, never mid-use (story 56). The
//   first install's takeover doesn't reload: that page is already current.
// - Each foreground asks the browser to look for a new `sw.js`, so an app
//   left open for days still updates.

export interface PageEnv {
  /** `navigator.serviceWorker`; undefined where service workers aren't available. */
  serviceWorker:
    | {
        readonly controller: unknown;
        register(url: string, options: { scope: string }): Promise<{ update(): Promise<unknown> }>;
        addEventListener(type: "controllerchange", listener: () => void): void;
      }
    | undefined;
  document: {
    readonly visibilityState: DocumentVisibilityState;
    addEventListener(type: "visibilitychange", listener: () => void): void;
  };
  reload(): void;
}

/** Register the worker for `base` (the bundle's base path, ending in "/"). */
export async function registerServiceWorker(env: PageEnv, base: string): Promise<void> {
  const container = env.serviceWorker;
  if (!container) return;
  let controlled = container.controller !== null && container.controller !== undefined;
  let updated = false;
  container.addEventListener("controllerchange", () => {
    if (controlled) updated = true;
    controlled = true;
  });
  const registration = await container.register(`${base}sw.js`, { scope: base });
  env.document.addEventListener("visibilitychange", () => {
    if (env.document.visibilityState !== "visible") return;
    if (updated) {
      env.reload();
      return;
    }
    registration.update().catch(() => {}); // offline: try again next time
  });
}
