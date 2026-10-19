// Applies the saved light/dark preference before first paint (kept external so CSP can forbid inline scripts).
try {
  if (localStorage.getItem("af-theme") === "light") document.documentElement.dataset.theme = "light";
} catch (e) {
  /* storage unavailable: default dark theme */
}
