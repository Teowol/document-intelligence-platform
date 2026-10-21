(function () {
  "use strict";
  function bindSummaryForm() {
    var form = document.querySelector("[data-summary-form]");
    if (!form || form.dataset.bound) return;
    form.dataset.bound = "true";
    form.addEventListener("submit", function () {
    var button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = button.dataset.pendingLabel;
    form.setAttribute("aria-busy", "true");
    });
  }
  bindSummaryForm();

  var processing = document.querySelector("[data-document-processing]");
  if (!processing) return;
  var timer;
  var pending = false;
  var stopped = false;
  async function updateDocument(status) {
    var response = await fetch(window.location.href, {credentials: "same-origin", cache: "no-store"});
    if (!response.ok || response.redirected) throw new Error("Document refresh failed");
    var page = new DOMParser().parseFromString(await response.text(), "text/html");
    var ids = ["summary-section", "chunks-section", "file-info-section"];
    if (!ids.every(function (id) { return page.getElementById(id); })) throw new Error("Incomplete document response");
    ids.forEach(function (id) {
      var current = document.getElementById(id);
      var next = page.getElementById(id);
      if (current.tagName === "DETAILS") next.open = current.open;
      if (id === "file-info-section") next.querySelector("[data-document-processing]").replaceWith(processing);
      current.replaceWith(next);
    });
    if (status === "ready" || status === "error") {
      var notice = document.querySelector("[data-processing-notice]");
      if (notice) notice.remove();
    }
    processing.dataset.initialStatus = status;
    bindSummaryForm();
  }
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
      if (data.document_status !== processing.dataset.initialStatus) {
        await updateDocument(data.document_status);
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
