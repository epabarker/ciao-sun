// The app's entry point: the browser's dependencies, handed to `startApp`.

import { startApp } from "./app";
import { RELEASE } from "./config/release";
import "./ui/style.css";

/** The GPS position. It never leaves the phone (spec #27, user story 12). */
function locate(): Promise<{ lat: number; lon: number }> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("no geolocation"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lon: position.coords.longitude }),
      reject,
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    );
  });
}

const root = document.querySelector<HTMLDivElement>("#app");
if (root) {
  startApp(root, {
    config: RELEASE,
    fetch: (url, init) => fetch(url, init),
    baseUrl: document.baseURI,
    storage: () => window.localStorage,
    now: () => Date.now(),
    locate,
  });
}
