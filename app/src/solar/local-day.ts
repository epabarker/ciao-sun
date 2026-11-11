// Local civil days and times in the query's time zone, from the platform's
// own time zone database (Intl), so the app ships none.

/** The reference's time zone (ciao_sun.reference.windows.TIME_ZONE). */
export const TIME_ZONE = "Europe/London";

export const MS_PER_MINUTE = 60_000;

const formatters = new Map<string, Intl.DateTimeFormat>();

function wallClock(ms: number, timeZone: string): Record<string, number> {
  let formatter = formatters.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
    });
    formatters.set(timeZone, formatter);
  }
  const fields: Record<string, number> = {};
  for (const part of formatter.formatToParts(ms)) {
    if (part.type !== "literal") {
      fields[part.type] = Number(part.value);
    }
  }
  return fields;
}

/** Minutes the zone's wall clock is ahead of UTC at an instant. */
export function utcOffsetMinutes(ms: number, timeZone: string): number {
  const f = wallClock(ms, timeZone);
  const asUtc = Date.UTC(f.year!, f.month! - 1, f.day!, f.hour!, f.minute!, f.second!);
  return Math.round((asUtc - Math.floor(ms / 1000) * 1000) / MS_PER_MINUTE);
}

/** The instant at which the zone's wall clock reads the given date and time. */
function instantOf(date: string, hour: number, minute: number, timeZone: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) {
    throw new RangeError(`${JSON.stringify(date)} is not a date like 2026-12-21`);
  }
  const wall = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), hour, minute);
  const first = wall - utcOffsetMinutes(wall, timeZone) * MS_PER_MINUTE;
  // The offset at the guess may be the one from the other side of a clock change.
  return wall - utcOffsetMinutes(first, timeZone) * MS_PER_MINUTE;
}

/**
 * The local civil day `date` (YYYY-MM-DD): the instant of its 00:00 and the
 * number of whole minutes up to and including its 23:59. That is 1,440, or
 * 1,380 and 1,500 on the days the clocks change.
 */
export function localDay(date: string, timeZone: string): { startMs: number; minutes: number } {
  const startMs = instantOf(date, 0, 0, timeZone);
  const lastMs = instantOf(date, 23, 59, timeZone);
  return { startMs, minutes: (lastMs - startMs) / MS_PER_MINUTE + 1 };
}

const two = (n: number) => String(n).padStart(2, "0");

/**
 * An instant as the reference writes every time: ISO 8601 with the zone's
 * offset, e.g. "2026-09-23T06:58:00+01:00".
 */
export function toLocalIso(ms: number, timeZone: string): string {
  const f = wallClock(ms, timeZone);
  const offset = utcOffsetMinutes(ms, timeZone);
  const sign = offset < 0 ? "-" : "+";
  const hours = Math.floor(Math.abs(offset) / 60);
  return (
    `${String(f.year).padStart(4, "0")}-${two(f.month!)}-${two(f.day!)}` +
    `T${two(f.hour!)}:${two(f.minute!)}:${two(f.second!)}` +
    `${sign}${two(hours)}:${two(Math.abs(offset) % 60)}`
  );
}
