(function () {
  "use strict";
  const form = document.querySelector("[data-live-search]");
  if (!form) return;
  const input = form.elements.q;
  const results = document.getElementById("search-results");
  const feedback = document.querySelector("[data-search-feedback]");
  let timer, controller, revision = 0, composing = false;

  function cancel() {
    clearTimeout(timer);
    if (controller) controller.abort();
    revision += 1;
    results.setAttribute("aria-busy", "false");
  }

  async function search() {
    cancel();
    const current = revision;
    const query = input.value.trim();
    const url = new URL(form.action, window.location.href);
    if (query) url.searchParams.set("q", query);
    history.replaceState(null, "", url);
    if (!query) {
      results.replaceChildren();
      feedback.hidden = true;
      return;
    }
    controller = new AbortController();
    feedback.textContent = form.dataset.loading;
    feedback.hidden = false;
    results.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(url, {
        signal: controller.signal, credentials: "same-origin", cache: "no-store"
      });
      if (!response.ok || response.redirected) throw new Error("Search unavailable");
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      const next = page.getElementById("search-results");
      if (!next) throw new Error("Missing results");
      if (current !== revision) return;
      results.replaceChildren(...next.childNodes);
      feedback.hidden = true;
    } catch (error) {
      if (current !== revision || error.name === "AbortError") return;
      results.replaceChildren();
      feedback.textContent = form.dataset.error;
      feedback.hidden = false;
    } finally {
      if (current === revision) results.setAttribute("aria-busy", "false");
    }
  }

  function schedule() {
    cancel();
    results.replaceChildren();
    feedback.hidden = true;
    if (composing) return;
    if (!input.value.trim()) { search(); return; }
    timer = setTimeout(search, 650);
  }
  input.addEventListener("input", schedule);
  input.addEventListener("compositionstart", function () { composing = true; cancel(); });
  input.addEventListener("compositionend", function () { composing = false; schedule(); });
  form.addEventListener("submit", function (event) { event.preventDefault(); search(); });
})();
