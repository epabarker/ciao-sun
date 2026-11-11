// The app's entry point. The answer screen arrives with the UI tickets
// (#46 onwards); until then the bundle is only a shell that builds.
const root = document.querySelector<HTMLDivElement>("#app");
if (root) {
  root.textContent = "Ciao Sun";
}
