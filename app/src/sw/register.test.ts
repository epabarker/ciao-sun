// The page's side of the service worker: it registers `/ciao-sun/sw.js` for
// `/ciao-sun/` only, and a new version applies silently on the next
// foreground, never mid-use (spec #27, stories 56 and 74; #52).

import { describe, expect, it } from "vitest";

import { type PageEnv, registerServiceWorker } from "./register";

function page(options: { controlled: boolean; supported?: boolean }) {
  const registered: { url: string; scope: string | undefined }[] = [];
  let updates = 0;
  let reloads = 0;
  const swListeners: (() => void)[] = [];
  const docListeners: (() => void)[] = [];
  const document = { visibilityState: "visible" as DocumentVisibilityState, addEventListener: (_: "visibilitychange", fn: () => void) => void docListeners.push(fn) };
  const container = {
    controller: options.controlled ? {} : null,
    register: async (url: string, opts?: { scope?: string }) => {
      registered.push({ url, scope: opts?.scope });
      return { update: async () => void updates++ };
    },
    addEventListener: (_: "controllerchange", fn: () => void) => void swListeners.push(fn),
  };
  const env: PageEnv = {
    serviceWorker: options.supported === false ? undefined : container,
    document,
    reload: () => void reloads++,
  };
  return {
    env,
    registered,
    reloads: () => reloads,
    updates: () => updates,
    /** A new worker takes control (after its `clients.claim`). */
    newWorker: () => {
      container.controller = {};
      for (const fn of swListeners) fn();
    },
    hide: () => {
      document.visibilityState = "hidden";
      for (const fn of docListeners) fn();
    },
    show: () => {
      document.visibilityState = "visible";
      for (const fn of docListeners) fn();
    },
  };
}

describe("registering the service worker", () => {
  it("registers /ciao-sun/sw.js with the scope /ciao-sun/ and nothing wider", async () => {
    const p = page({ controlled: false });
    await registerServiceWorker(p.env, "/ciao-sun/");
    expect(p.registered).toEqual([{ url: "/ciao-sun/sw.js", scope: "/ciao-sun/" }]);
  });

  it("does nothing in a browser without service workers", async () => {
    const p = page({ controlled: false, supported: false });
    await expect(registerServiceWorker(p.env, "/ciao-sun/")).resolves.toBeUndefined();
  });
});

describe("a new version", () => {
  it("doesn't reload the page in use when it takes over, only when the app next comes to the foreground", async () => {
    const p = page({ controlled: true });
    await registerServiceWorker(p.env, "/ciao-sun/");
    p.newWorker();
    expect(p.reloads()).toBe(0);
    p.hide();
    expect(p.reloads()).toBe(0);
    p.show();
    expect(p.reloads()).toBe(1);
  });

  it("taking over while the app is in the background applies when it comes back", async () => {
    const p = page({ controlled: true });
    await registerServiceWorker(p.env, "/ciao-sun/");
    p.hide();
    p.newWorker();
    expect(p.reloads()).toBe(0);
    p.show();
    expect(p.reloads()).toBe(1);
  });

  it("the first install's takeover doesn't reload: the page is already the current version", async () => {
    const p = page({ controlled: false });
    await registerServiceWorker(p.env, "/ciao-sun/");
    p.newWorker();
    p.hide();
    p.show();
    expect(p.reloads()).toBe(0);
  });

  it("is looked for each time the app comes to the foreground", async () => {
    const p = page({ controlled: true });
    await registerServiceWorker(p.env, "/ciao-sun/");
    p.hide();
    p.show();
    p.hide();
    p.show();
    expect(p.updates()).toBe(2);
    expect(p.reloads()).toBe(0);
  });
});
