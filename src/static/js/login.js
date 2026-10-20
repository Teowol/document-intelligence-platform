(function () {
  "use strict";
  var control = document.querySelector("[data-password-visibility]");
  var password = document.querySelector('input[name="password"]');
  if (!control || !password) return;
  var checkbox = control.querySelector('input[type="checkbox"]');
  if (password.id) checkbox.setAttribute("aria-controls", password.id);
  var field = password.closest("p");
  if (field) field.insertAdjacentElement("afterend", control);
  control.hidden = false;
  checkbox.addEventListener("change", function () {
    password.type = checkbox.checked ? "text" : "password";
  });
  window.addEventListener("pageshow", function () {
    checkbox.checked = false;
    password.type = "password";
  });
})();
