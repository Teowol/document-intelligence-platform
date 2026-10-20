/* DIP frontend helpers: dark/light theme + bootstrap overridable theme attrs. */

(function () {
  "use strict";

  var THEME_KEY = "dip-theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.setAttribute("data-bs-theme", theme);
    document.documentElement.style.colorScheme = theme;
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* storage off */ }
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function toggleTheme() {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  }

  // Attach handlers after DOM is ready.
  function init() {
    applyTheme(currentTheme());

    var btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        toggleTheme();
        refreshThemeBtn(btn);
      });
      refreshThemeBtn(btn); // populate label/icon on first paint
    }
  }

  function refreshThemeBtn(btn) {
    var icon = btn.querySelector("[data-theme-icon]");
    var label = btn.querySelector("[data-theme-label]");
    var dark = currentTheme() === "dark";
    if (icon) icon.textContent = dark ? "☾" : "☀"; // moon for dark, sun for light
    if (label) label.textContent = btn.getAttribute(dark ? "data-label-dark" : "data-label-light") || (dark ? "Dark" : "Light");
    btn.setAttribute("aria-pressed", String(dark));
  }

  // Let base template call this after it swaps in the button too.
  window.DIPTheme = { refresh: refreshThemeBtn };

  // Example question chips on the QA page fill + submit the query.
  var chips = document.querySelectorAll(".example-chips .chip");
  if (chips.length) {
    for (var i = 0; i < chips.length; i++) {
      chips[i].addEventListener("click", function () {
        var q = this.getAttribute("data-ask");
        if (!q) return;
        var input = document.querySelector('form[action*="ask"] input[name=q]');
        if (input) { input.value = q; input.form.submit(); }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
