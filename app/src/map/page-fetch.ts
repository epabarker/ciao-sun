// Basemap tiles fetched by the page (#52). MapLibre would fetch them from its
// own dedicated worker. The Service Worker spec has that worker controlled
// (it is matched by its script URL, which is inside /ciao-sun/), but whether
// Safari does so is unverified, and offline maps on a phone hang on it. So the
// basemap source's tile URLs carry a scheme of their own: MapLibre's worker
// doesn't know it and passes each request to the page (`makeRequest` in
// maplibre-gl's `src/util/ajax.ts`), where `addProtocol` has registered
// `pageTileLoader`, and the page's fetch always goes through the service worker.

export const PAGE_SCHEME = "ciao-sun-page";
const PREFIX = `${PAGE_SCHEME}://`;

/** `url` (an http(s) tile template or URL) as one the page fetches. */
export function throughPage(url: string): string {
  return PREFIX + url;
}

/** MapLibre's `addProtocol` loader for `throughPage` URLs. */
export function pageTileLoader(fetch: (url: string, init?: RequestInit) => Promise<Response>) {
  return async (request: { url: string; type?: string }, abort: AbortController): Promise<{ data: ArrayBuffer }> => {
    const url = request.url.startsWith(PREFIX) ? request.url.slice(PREFIX.length) : request.url;
    const response = await fetch(url, { signal: abort.signal });
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    return { data: await response.arrayBuffer() };
  };
}
