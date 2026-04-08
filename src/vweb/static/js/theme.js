// Apply saved theme before paint to prevent FOUC
(function() {
  var saved = localStorage.getItem("theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
})();

// Sync the theme select dropdown and persist changes
document.addEventListener("DOMContentLoaded", function() {
  var sel = document.getElementById("theme-select");
  if (!sel) return;

  var saved = localStorage.getItem("theme");
  if (saved) sel.value = saved;

  sel.addEventListener("change", function() {
    localStorage.setItem("theme", this.value);
    document.documentElement.setAttribute("data-theme", this.value);
  });
});
