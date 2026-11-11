// How Answer values are written on screen.

/**
 * The wall-clock "HH:MM" of an Answer time. Every Answer time carries the
 * Europe/London offset already, so it is read off the string: never through
 * `Date`, which would show the device's zone.
 */
export function clockOf(iso: string): string {
  return iso.slice(11, 16);
}

/** "6 min walk"; under half a minute is "Here". */
export function walkLabel(walkMin: number): string {
  return walkMin < 0.5 ? "Here" : `${Math.round(walkMin)} min walk`;
}

/** A date for the sentence, e.g. "Wed 23 Sep". */
export function dateLabel(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y!, m! - 1, d!)).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}
