// The typed origin: "lat, lon" in decimal degrees. Saved places (#49) are the
// other non-GPS origin; their coordinates come from the settings store.

export function parseOrigin(text: string): { lat: number; lon: number } | undefined {
  const match = /^\s*(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(text);
  if (!match) return undefined;
  const lat = Number(match[1]);
  const lon = Number(match[2]);
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return undefined;
  return { lat, lon };
}
