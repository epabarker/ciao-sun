// The sentence editor: the query as one editable sentence (spec #27, user
// story 3):
//
//   I wake at [07:00] on [date], the sky looks [clear], and I'll walk up to
//   [15] min from [here].
//
// Each slot is a native control (time, date, select) so a phone shows its own
// picker, and reports on `change`. The words around the slots come from
// WORDING by window: #48 adds the Evening tab's wording there. The sky slot is
// pre-filled from the forecast; `sky-slot.ts` has where its value came from
// and the credit under it (#50).
//
// The origin slot says which origin is in use: "here" (GPS), a saved place's
// name, or a typed position. Once places are saved it is a select of all
// three, so a denied GPS offers the saved places (#49).

import { MAX_WALK_CAP_MIN, type Sky, type WindowName } from "../contract";
import type { QueryInputs } from "../query/query";
import type { SavedPlace } from "../settings/store";
import { h } from "./dom";
import { type SkySource, skyNote } from "./sky-slot";

export type OriginSlot =
  | { kind: "locating" }
  | { kind: "gps"; lat: number; lon: number }
  | { kind: "typed"; text: string; reason?: string }
  /** A saved place, as it was when picked (the app keeps it in step with renames). */
  | { kind: "place"; place: SavedPlace };

export interface SentenceState extends Omit<QueryInputs, "origin"> {
  window: WindowName;
  skySource: SkySource;
  /** The saved default Wake time; differs from `wakeTime` while it is overridden for one query. */
  savedWakeTime: string;
  origin: OriginSlot;
  /** The saved places the origin slot offers. */
  places: readonly SavedPlace[];
}

export interface SentenceEvents {
  wakeTime(value: string): void;
  saveWakeTime(): void;
  date(value: string): void;
  sky(value: Sky): void;
  maxWalkMin(value: number): void;
  typeOrigin(text: string): void;
  useGps(): void;
  usePlace(id: string): void;
}

export const SKY_LABELS: Record<Sky, string> = { clear: "clear", partly: "partly cloudy", overcast: "overcast" };

const MAX_WALK_CHOICES = [5, 10, 15, MAX_WALK_CAP_MIN];

interface Wording {
  wake: string;
  on: string;
  sky: string;
  walk: string;
  from: string;
  end: string;
}

export const WORDING: Partial<Record<WindowName, Wording>> = {
  morning: {
    wake: "I wake at",
    on: "on",
    sky: ", the sky looks",
    walk: ", and I'll walk up to",
    from: "min from",
    end: ".",
  },
};

function select<T extends string | number>(
  name: string,
  value: T,
  choices: readonly T[],
  label: (choice: T) => string,
  onChange: (value: string) => void,
): HTMLSelectElement {
  const options = choices.includes(value) ? choices : [...choices, value];
  const el = h(
    "select",
    { name, class: "slot", "aria-label": name },
    ...options.map((choice) => h("option", { value: String(choice), selected: choice === value }, label(choice))),
  );
  el.value = String(value);
  el.addEventListener("change", () => onChange(el.value));
  return el;
}

function input(name: string, type: string, value: string, onChange: (value: string) => void): HTMLInputElement {
  const el = h("input", { name, type, class: "slot", value, required: true, "aria-label": name });
  el.value = value;
  el.addEventListener("change", () => {
    if (el.value) onChange(el.value);
  });
  return el;
}

const HERE = "here";
const TYPED = "typed";
const PLACE = "place:";

/** The origin slot once places are saved: here, each place, or a typed position. */
function originChoice(origin: OriginSlot, places: readonly SavedPlace[], events: SentenceEvents): Node {
  const value = origin.kind === "place" ? PLACE + origin.place.id : origin.kind === "typed" ? TYPED : HERE;
  const labels = new Map<string, string>([
    [HERE, origin.kind === "locating" ? "here (locating…)" : "here"],
    ...places.map((place): [string, string] => [PLACE + place.id, place.name]),
    [TYPED, "a position…"],
  ]);
  const choice = select("origin-choice", value, [...labels.keys()], (v) => labels.get(v) ?? v, (picked) => {
    if (picked === HERE) events.useGps();
    else if (picked === TYPED) events.typeOrigin("");
    else events.usePlace(picked.slice(PLACE.length));
  });
  choice.setAttribute("aria-label", "from");
  return origin.kind === "typed" ? h("span", { class: "origin-choice" }, choice, " ", typedOrigin(origin, events)) : choice;
}

function typedOrigin(origin: Extract<OriginSlot, { kind: "typed" }>, events: SentenceEvents): HTMLElement {
  const field = input("origin", "text", origin.text, events.typeOrigin);
  field.placeholder = "51.4589, -2.6052";
  field.inputMode = "decimal";
  field.classList.add("slot-origin");
  return h(
    "span",
    { class: "origin-typed" },
    field,
    origin.reason ? h("span", { class: "slot-note", "data-field": "origin-note" }, origin.reason) : null,
  );
}

function originSlot(origin: OriginSlot, places: readonly SavedPlace[], events: SentenceEvents): Node {
  if (places.length > 0) return originChoice(origin, places, events);
  if (origin.kind === "typed") return typedOrigin(origin, events);
  const button = h(
    "button",
    { type: "button", class: "slot slot-button", "data-action": "type-origin", title: "Type a position instead" },
    origin.kind === "locating" ? "here (locating…)" : origin.kind === "place" ? origin.place.name : "here",
  );
  button.addEventListener("click", () => events.typeOrigin(""));
  return button;
}

function skySlot(state: SentenceState, events: SentenceEvents): HTMLSelectElement {
  const slot = select("sky", state.sky, Object.keys(SKY_LABELS) as Sky[], (sky) => SKY_LABELS[sky], (v) =>
    events.sky(v as Sky),
  );
  slot.setAttribute("data-sky-source", state.skySource.kind);
  return slot;
}

export function renderSentence(state: SentenceState, events: SentenceEvents): HTMLElement {
  const words = WORDING[state.window] ?? WORDING.morning!;
  const overridden = state.wakeTime !== state.savedWakeTime;
  const save = overridden
    ? h(
        "button",
        { type: "button", class: "link", "data-action": "save-wake" },
        `Make ${state.wakeTime} my usual Wake time`,
      )
    : null;
  save?.addEventListener("click", () => events.saveWakeTime());

  return h(
    "div",
    { class: "sentence-wrap" },
    h(
      "p",
      { class: "sentence", "data-field": "sentence" },
      `${words.wake} `,
      input("wakeTime", "time", state.wakeTime, events.wakeTime),
      ` ${words.on} `,
      input("date", "date", state.date, events.date),
      `${words.sky} `,
      skySlot(state, events),
      `${words.walk} `,
      select("maxWalkMin", state.maxWalkMin, MAX_WALK_CHOICES, String, (v) => events.maxWalkMin(Number(v))),
      ` ${words.from} `,
      originSlot(state.origin, state.places, events),
      words.end,
    ),
    skyNote(state.skySource),
    save,
    state.origin.kind === "typed" && state.places.length === 0
      ? (() => {
          const gps = h("button", { type: "button", class: "link", "data-action": "use-gps" }, "Use my location");
          gps.addEventListener("click", () => events.useGps());
          return gps;
        })()
      : null,
  );
}
