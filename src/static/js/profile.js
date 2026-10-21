(function () {
  "use strict";
  var form = document.querySelector("[data-profile-form]");
  if (!form) return;
  var file = form.querySelector('input[type="file"]');
  var images = Array.from(document.querySelectorAll("[data-avatar-image]"));
  var initials = document.querySelectorAll("[data-avatar-initials]");
  var original = images[0].getAttribute("src");
  var objectURL;
  var note = form.querySelector("[data-photo-note]");
  var trash = document.querySelector("[data-delete-avatar]");
  var remove = form.querySelector('[name="remove_avatar"]');
  function showPhoto(url) {
    images.forEach(function (image) { image.hidden = !url; if (url) image.src = url; else image.removeAttribute("src"); });
    initials.forEach(function (element) { element.hidden = !!url; });
    trash.hidden = !url;
  }
  function releasePreview() { if (objectURL) { URL.revokeObjectURL(objectURL); objectURL = null; } }
  if (remove.checked) showPhoto(null);
  trash.addEventListener("click", function () {
    releasePreview(); file.value = ""; remove.checked = !!original;
    showPhoto(null); note.hidden = true;
    form.querySelector("[data-unsaved]").hidden = false;
  });
  file.addEventListener("change", function () {
    releasePreview();
    if (file.files[0]) {
      remove.checked = false;
      objectURL = URL.createObjectURL(file.files[0]);
      showPhoto(objectURL); note.hidden = false;
    } else { showPhoto(remove.checked ? null : original); note.hidden = true; }
  });
  var bio = form.querySelector('[name="bio"]');
  function countBio() { form.querySelector("[data-bio-count]").textContent = bio.value.length; }
  bio.addEventListener("input", countBio);
  form.addEventListener("input", function () { form.querySelector("[data-unsaved]").hidden = false; });
  form.addEventListener("change", function () { form.querySelector("[data-unsaved]").hidden = false; });
  form.addEventListener("reset", function () {
    releasePreview(); showPhoto(original); note.hidden = true;
    form.querySelector("[data-unsaved]").hidden = true;
    window.setTimeout(countBio, 0);
  });
  form.addEventListener("submit", function () {
    var button = form.querySelector('button[type="submit"]');
    button.disabled = true; button.textContent = button.dataset.savingLabel;
    form.setAttribute("aria-busy", "true");
  });
  window.addEventListener("pagehide", releasePreview);
})();
