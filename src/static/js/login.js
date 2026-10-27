(function () {
  "use strict";
  document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
    var password = document.getElementById(button.getAttribute("aria-controls"));
    if (!password) return;
    button.hidden = false;
    button.addEventListener("click", function () {
      var visible = password.type === "password";
      password.type = visible ? "text" : "password";
      button.setAttribute("aria-pressed", String(visible));
    });
    window.addEventListener("pageshow", function () {
      password.type = "password";
      button.setAttribute("aria-pressed", "false");
    });
  });
})();
