// The About the data sheet and the footer link that opens it.
//
//   <section class="about" data-sheet="about" role="dialog">
//     credits      one [data-credit] per manifest attribution entry, in order
//     survey years [data-field=survey-years]
//     licence      [data-field=licence], the bundle's
//     caveats      one [data-caveat=<key>] per CAVEATS entry
//     privacy      [data-field=privacy], what the data host sees
//
// Whether it is open is app state, so a re-render keeps it open.

import { type About, CAVEATS, type CaveatKey, type Credit, PRIVACY, PROTOCOLS_FACTOR, listYears } from "../about/about";
import { h } from "./dom";

export const ABOUT_TITLE = "About the data";

/** The footer link; it opens the sheet through `onOpen`. */
export function aboutLink(onOpen: () => void): HTMLElement {
  const button = h("button", { type: "button", class: "link", "data-action": "about" }, ABOUT_TITLE);
  button.addEventListener("click", onOpen);
  return button;
}

/** The sheet. `about` is undefined until a manifest has loaded. */
export function renderAbout(about: About | undefined, onClose: () => void): HTMLElement {
  const close = h("button", { type: "button", class: "link", "data-action": "close-about" }, "Close");
  close.addEventListener("click", onClose);
  return h(
    "section",
    { class: "about", "data-sheet": "about", role: "dialog", "aria-labelledby": "about-title" },
    h("h2", { id: "about-title" }, ABOUT_TITLE),
    ...(about ? manifestPart(about) : [h("p", { class: "mute", "data-field": "credits-pending" }, "Credits and the licence load with the data.")]),
    h("h3", {}, "What to keep in mind"),
    h(
      "ul",
      { class: "caveats" },
      ...(Object.keys(CAVEATS) as CaveatKey[]).map((key) =>
        h(
          "li",
          { "data-caveat": key },
          CAVEATS[key],
          key === "ranking" ? h("strong", { "data-field": "ranking-reason" }, ` ${PROTOCOLS_FACTOR}.`) : null,
        ),
      ),
    ),
    h("p", { class: "mute", "data-field": "privacy" }, PRIVACY),
    close,
  );
}

function manifestPart(about: About): Node[] {
  const parts: (Node | null)[] = [
    h("h3", {}, "Credits"),
    h("ul", { class: "credits" }, ...about.credits.map(credit)),
    about.surveyYears.length > 0
      ? h(
          "p",
          { "data-field": "survey-years" },
          `The LIDAR in this build was flown in ${listYears(about.surveyYears)}.`,
        )
      : null,
    about.licence
      ? h(
          "p",
          { "data-field": "licence" },
          about.build ? `The data bundle (build ${about.build}) is licensed under the ` : "The data bundle is licensed under the ",
          link(about.licence.name, about.licence.url),
          ".",
        )
      : null,
  ];
  return parts.filter((node): node is Node => node !== null);
}

function credit(line: Credit): HTMLElement {
  return h(
    "li",
    { "data-credit": line.source },
    h("strong", {}, line.source),
    `: ${line.text}`,
    line.licence ? " " : null,
    line.licence ? link(line.licence, line.licenceUrl) : null,
  );
}

function link(label: string, url: string | undefined): Node {
  return url ? h("a", { href: url, rel: "noopener", target: "_blank" }, label) : document.createTextNode(label);
}
