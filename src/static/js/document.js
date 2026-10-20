(function () {
  "use strict";
  var form = document.querySelector("[data-summary-form]");
  if (form) form.addEventListener("submit", function () {
    var button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = button.dataset.pendingLabel;
    form.setAttribute("aria-busy", "true");
  });

  var processing = document.querySelector("[data-document-processing]");
  if (!processing) return;
  var timer;
  var pending = false;
  var stopped = false;
  async function refresh() {
    if (pending || stopped || document.hidden) return;
    window.clearTimeout(timer);
    pending = true;
    try {
      var response = await fetch(processing.dataset.statusUrl, {credentials: "same-origin", cache: "no-store"});
      if (response.status === 404) {
        processing.querySelector("[data-processing-label]").textContent = processing.dataset.missingLabel;
        stopped = true;
        return;
      }
      if (!response.ok || response.redirected) { stopped = response.redirected; return; }
      var data = await response.json();
      processing.querySelector("[data-processing-label]").textContent = data.label;
      var progress = processing.querySelector("[data-processing-progress]");
      progress.value = data.stage;
      progress.setAttribute("aria-valuetext", data.label);
      processing.classList.toggle("has-error", data.state === "error");
      processing.querySelectorAll("[data-processing-step]").forEach(function (step) {
        var index = Number(step.dataset.processingStep);
        step.classList.toggle("is-complete", index < data.stage || data.state === "ready");
        step.classList.toggle("is-current", index === data.stage && data.state !== "ready");
        if (index === data.stage) step.setAttribute("aria-current", "step");
        else step.removeAttribute("aria-current");
      });
      if (data.text_ready && ["uploaded", "processing"].includes(processing.dataset.initialStatus)) {
        processing.querySelector("[data-processing-refresh]").hidden = false;
      }
      stopped = data.finished;
    } catch (error) {
      // Retry temporary failures without interrupting the document preview.
    } finally {
      pending = false;
      if (!stopped) timer = window.setTimeout(refresh, 4000);
    }
  }
  document.addEventListener("visibilitychange", refresh);
  refresh();
})();
