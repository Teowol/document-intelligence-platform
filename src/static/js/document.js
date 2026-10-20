(function () {
  "use strict";
  var form = document.querySelector("[data-summary-form]");
  if (!form) return;
  form.addEventListener("submit", function () {
    var button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = button.dataset.pendingLabel;
    form.setAttribute("aria-busy", "true");
  });
})();
