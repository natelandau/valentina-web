// Theme toggle: localStorage persistence, OS preference detection, FOUC prevention.
// Must run synchronously in <head> (before DOMContentLoaded) to set data-theme before paint.
(function () {
  var LIGHT = "valentina-light";
  var DARK = "dim";
  var saved = localStorage.getItem("theme");

  if (saved) {
    document.documentElement.setAttribute("data-theme", saved);
  } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.setAttribute("data-theme", DARK);
  }

  // After DOM is ready: sync the toggle checkbox and wire up persistence + OS listener.
  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("theme-toggle");
    if (!toggle) return;

    var activeTheme = document.documentElement.getAttribute("data-theme");
    toggle.checked = activeTheme === DARK;

    toggle.addEventListener("change", function () {
      var theme = this.checked ? DARK : LIGHT;
      localStorage.setItem("theme", theme);
    });

    // Follow OS preference changes when the user hasn't made an explicit choice
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {
      if (localStorage.getItem("theme") !== null) return;
      var theme = e.matches ? DARK : LIGHT;
      document.documentElement.setAttribute("data-theme", theme);
      toggle.checked = e.matches;
    });
  });
})();
