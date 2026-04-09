// Must run synchronously in <head> (before DOMContentLoaded) to set data-theme before paint.
(function () {
  var LIGHT = "valentina-light";
  var DARK = "dim";
  var saved = localStorage.getItem("theme");
  var darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  if (saved) {
    document.documentElement.setAttribute("data-theme", saved);
  } else if (darkQuery.matches) {
    document.documentElement.setAttribute("data-theme", DARK);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("theme-toggle");
    if (!toggle) return;

    toggle.checked = document.documentElement.getAttribute("data-theme") === DARK;

    toggle.addEventListener("change", function () {
      var theme = this.checked ? DARK : LIGHT;
      localStorage.setItem("theme", theme);
    });

    // Follow OS preference changes when the user hasn't made an explicit choice
    darkQuery.addEventListener("change", function (e) {
      if (localStorage.getItem("theme") !== null) return;
      var theme = e.matches ? DARK : LIGHT;
      document.documentElement.setAttribute("data-theme", theme);
      toggle.checked = e.matches;
    });
  });
})();
