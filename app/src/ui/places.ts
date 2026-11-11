// Saved places (#49): save the origin in use under a name, rename, delete.
// They are kept only in the settings store on the phone (user story 11);
// picking one as the origin is the sentence's origin slot (`sentence.ts`).
//
//   [Saved places (2)]                  the toggle, under the sentence
//   <section class="places">            open:
//     <li data-place="<id>">            [name] [Delete]   (rename on change)
//     [name for here] [Save]            when the origin in use can be saved
//     <p data-field="places-note">      when storage won't outlive the page

import type { SavedPlace } from "../settings/store";
import { h } from "./dom";

export interface PlacesState {
  places: readonly SavedPlace[];
  open: boolean;
  /** Whether the origin in use is a position that can be saved (GPS or typed). */
  canSave: boolean;
  /** The name typed for the next place, kept across re-renders. */
  draft: string;
  /** Whether saved places will outlive this page. */
  persistent: boolean;
}

export interface PlacesEvents {
  togglePlaces(): void;
  draftPlace(name: string): void;
  savePlace(): void;
  renamePlace(id: string, name: string): void;
  deletePlace(id: string): void;
}

function button(action: string, label: string, onClick: () => void, cls = "link"): HTMLButtonElement {
  const el = h("button", { type: "button", class: cls, "data-action": action }, label);
  el.addEventListener("click", onClick);
  return el;
}

function placeRow(place: SavedPlace, events: PlacesEvents): HTMLElement {
  const name = h("input", { name: "place-name", type: "text", class: "place-name", value: place.name, "aria-label": "name" });
  name.value = place.name;
  name.addEventListener("change", () => {
    if (name.value.trim()) events.renamePlace(place.id, name.value);
    else name.value = place.name;
  });
  return h(
    "li",
    { class: "place", "data-place": place.id },
    name,
    button("delete-place", "Delete", () => events.deletePlace(place.id)),
  );
}

function saveForm(state: PlacesState, events: PlacesEvents): HTMLElement {
  const name = h("input", {
    name: "new-place-name",
    type: "text",
    class: "place-name",
    placeholder: "Name this origin",
    "aria-label": "name for the origin in use",
  });
  name.value = state.draft;
  const keep = () => events.draftPlace(name.value);
  name.addEventListener("input", keep);
  name.addEventListener("change", keep);
  return h(
    "p",
    { class: "place-save" },
    name,
    button("save-place", "Save", () => {
      keep();
      events.savePlace();
    }),
  );
}

export function renderPlaces(state: PlacesState, events: PlacesEvents): HTMLElement {
  const toggle = button(
    "toggle-places",
    state.places.length ? `Saved places (${state.places.length})` : "Saved places",
    () => events.togglePlaces(),
  );
  toggle.setAttribute("aria-expanded", String(state.open));
  if (!state.open) return h("div", { class: "places-wrap" }, toggle);
  return h(
    "div",
    { class: "places-wrap" },
    toggle,
    h(
      "section",
      { class: "places", "aria-label": "Saved places" },
      state.places.length
        ? h("ul", { class: "place-list" }, ...state.places.map((place) => placeRow(place, events)))
        : h("p", { class: "mute" }, "No saved places yet."),
      state.canSave ? saveForm(state, events) : null,
      h("p", { class: "mute place-note" }, "Kept only on this phone."),
      state.persistent
        ? null
        : h(
            "p",
            { class: "slot-note", "data-field": "places-note" },
            "This browser isn't keeping data, so places are kept only until you reload.",
          ),
    ),
  );
}
