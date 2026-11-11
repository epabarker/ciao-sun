// The sentence editor: the query as one editable sentence (spec #27, user
// story 3):
//
//   I wake at [07:00] on [date], the sky looks [clear], and I'll walk up to
//   [15] min from [here].
//
// Each slot is a native control (time, date, select) so a phone shows its own
// picker, and reports on `change`. The words around the slots come from
// WORDING by window: #48 adds the Evening tab's wording there. #49 puts saved
// places in the origin slot. The sky slot is pre-filled from the forecast;
// `sky-slot.ts` has where its value came from and the credit under it (#50).

import { MAX_WALK_CAP_MIN, type Sky, type WindowName } from "../contract";
import type { QueryInputs } from "../query/query";
import { h } from "./dom";
import { type SkySource, skyNote } from "./sky-slot";

export type OriginSlot =
  | { kind: "locating" }
  | { kind: "gps"; lat: number; lon: number }
  | { kind: "typed"; text: string; reason?: string };

export interface SentenceState extends Omit<QueryInputs, "origin"> {
  window: WindowName;
  skySource: SkySource;
  /** The saved default Wake time; differs from `wakeTime` while it is overridden for one query. */
  savedWakeTime: string;
  origin: OriginSlot;
}

export interface SentenceEvents {
  wakeTime(value: string): void;
  saveWakeTime(): void;
  date(value: string): void;
  sky(value: Sky): void;
  maxWalkMin(value: number): void;
  typeOrigin(text: string): void;
  useGps(): void;
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

function originSlot(origin: OriginSlot, events: SentenceEvents): Node {
  if (origin.kind === "typed") {
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
  const button = h(
    "button",
    { type: "button", class: "slot slot-button", "data-action": "type-origin", title: "Type a position instead" },
    origin.kind === "locating" ? "here (locating…)" : "here",
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
      originSlot(state.origin, events),
      words.end,
    ),
    skyNote(state.skySource),
    save,
    state.origin.kind === "typed"
      ? (() => {
          const gps = h("button", { type: "button", class: "link", "data-action": "use-gps" }, "Use my location");
          gps.addEventListener("click", () => events.useGps());
          return gps;
        })()
      : null,
  );
}
