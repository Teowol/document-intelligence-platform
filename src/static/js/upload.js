(function () {
  "use strict";
  var form = document.querySelector("[data-upload-form]");
  if (!form || !window.XMLHttpRequest || !window.FormData) return;
  var button = form.querySelector("button[type=submit]");
  var originalLabel = button.textContent;
  var feedback = form.querySelector("[data-upload-feedback]");
  var progress = form.querySelector("[data-upload-progress]");
  var label = form.querySelector("[data-upload-label]");
  var percent = form.querySelector("[data-upload-percent]");
  var errors = form.querySelector("[data-upload-errors]");

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (button.disabled) return;
    var body = new FormData(form);
    button.disabled = true;
    button.textContent = form.dataset.uploading;
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll('[aria-invalid="true"]').forEach(function (field) {
      field.removeAttribute("aria-invalid");
    });
    feedback.hidden = false;
    feedback.classList.remove("has-error");
    progress.value = 0;
    percent.textContent = "0%";
    label.textContent = form.dataset.uploading;
    errors.hidden = true;
    errors.replaceChildren();

    function fail(messages) {
      button.disabled = false;
      button.textContent = originalLabel;
      form.removeAttribute("aria-busy");
      feedback.classList.add("has-error");
      label.textContent = form.dataset.failure;
      var list = document.createElement("ul");
      messages.forEach(function (message) {
        var item = document.createElement("li");
        item.textContent = message;
        list.appendChild(item);
      });
      errors.replaceChildren(list);
      errors.hidden = false;
      errors.setAttribute("tabindex", "-1");
      errors.focus();
    }

    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action || window.location.href);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.timeout = 120000;
    xhr.upload.addEventListener("progress", function (event) {
      if (!event.lengthComputable) {
        progress.removeAttribute("value");
        percent.textContent = "";
        return;
      }
      var value = Math.min(100, Math.floor(event.loaded / event.total * 100));
      progress.value = value;
      percent.textContent = value + "%";
    });
    xhr.upload.addEventListener("load", function () {
      progress.value = 100;
      percent.textContent = "100%";
      label.textContent = form.dataset.validating;
    });
    xhr.addEventListener("load", function () {
      if (xhr.responseURL && new URL(xhr.responseURL).pathname.startsWith("/accounts/login/")) {
        window.location.assign(xhr.responseURL);
        return;
      }
      var data;
      try { data = JSON.parse(xhr.responseText); }
      catch (error) { fail([form.dataset.failure]); return; }
      if (xhr.status === 201 && data.url) {
        window.location.assign(data.url);
        return;
      }
      var messages = [];
      (data.errors || []).forEach(function (error) {
        var field = form.elements.namedItem(error.field);
        if (field && field.setAttribute) field.setAttribute("aria-invalid", "true");
        error.messages.forEach(function (message) { messages.push(error.label + ": " + message); });
      });
      fail(messages.length ? messages : [form.dataset.failure]);
    });
    ["error", "timeout", "abort"].forEach(function (event) {
      xhr.addEventListener(event, function () { fail([form.dataset.failure]); });
    });
    xhr.send(body);
  });
})();
