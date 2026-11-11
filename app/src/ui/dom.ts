// A small element builder, so views read as markup without a framework.

type Attrs = Record<string, string | number | boolean | undefined>;
export type Child = Node | string | null | undefined | false;

/**
 * `h("li", { class: "spot", "data-spot": id }, ...children)`. An attribute
 * that is `false` or `undefined` is left off; `true` sets it empty.
 */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === false) continue;
    el.setAttribute(name, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child);
  }
  return el;
}
