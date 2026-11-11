// The Query -> Answer contract (spec #27, "The Query -> Answer contract"), as
// the JSON that golden fixtures hold. `ciao_sun.reference.contract` is the
// Python side; docs/fixtures.md describes the fixture around it.
//
// Every time is an ISO 8601 string with the Europe/London offset, on a whole
// minute. A field that is unset is absent, never null.

export type WindowName = "morning" | "evening";
export type Sky = "clear" | "partly" | "overcast";
export type Status = "ranked" | "fallback" | "lamp-only" | "no-evening-window" | "not-covered";

/** The most a Query may ask to walk, in minutes. */
export const MAX_WALK_CAP_MIN = 20;

export interface Query {
  window: WindowName;
  /** Local date, YYYY-MM-DD, Europe/London. */
  date: string;
  /** Local "HH:MM". */
  wakeTime: string;
  origin: { lat: number; lon: number };
  /** At most MAX_WALK_CAP_MIN. */
  maxWalkMin: number;
  sky: Sky;
  /** ISO instant; clips the window start when it falls on `date`. */
  now?: string;
}

/** A run of minutes: `start` is its first minute, `end` the minute after its last. */
export interface Interval {
  start: string;
  end: string;
}

/** The Morning window or Evening window, and the timeline axis to draw it on. */
export interface AnswerWindow {
  start: string;
  end: string;
  axisStart: string;
  axisEnd: string;
}

export interface Spot {
  /** "<tile grid ref>/<Candidate index in that tile>". */
  candidateId: string;
  /** Spot name. */
  name: string;
  lat: number;
  lon: number;
  /** Whole metres; the ranking's tie-break. */
  walkMetres: number;
  walkMin: number;
  leaveBy: string;
  /** Sun in view, within the window. */
  sunIntervals: Interval[];
  /** The part of those at 0-30 degrees. */
  lowSunIntervals: Interval[];
  sunMinutes: number;
  /** To 0.01 min; taper-weighted in the morning. */
  lowSunMinutes: number;
  /** To 0.001. */
  skyOpenness: number;
  targetMet: boolean;
  /** Evening. */
  lastSun?: string;
  /** Fallback "stay N min". */
  stayMin?: number;
}

export interface Answer {
  status: Status;
  window?: AnswerWindow;
  nominalSunrise?: string;
  nominalSunset?: string;
  solarNoon?: string;
  durationTargetMin?: number;
  /** Morning: Nominal sunrise > Wake time + 1 h. */
  lamp?: boolean;
  /** Lamp-only. */
  nextOutdoorLight?: string;
  /** In display order. */
  spots: Spot[];
  /** Fallback when the sky isn't overcast. */
  nearestSunBeyondLimit?: Spot;
}
