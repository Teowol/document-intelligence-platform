(function () {
  "use strict";
  var panel = document.querySelector("[data-qa-history]");
  if (!panel) return;
  var details = panel.querySelector("details");
  if (window.matchMedia("(max-width: 1000px)").matches) details.open = false;
  var pending = false;
  var list = panel.querySelector("[data-history-list]");
  var historySignature = JSON.stringify(Array.from(list.querySelectorAll("a")).map(function (link) {
    return [link.getAttribute("href"), link.title];
  }));

  async function refreshHistory() {
    if (document.hidden || pending) return;
    pending = true;
    try {
      var response = await fetch(panel.dataset.historyUrl, {
        credentials: "same-origin", cache: "no-store"
      });
      if (!response.ok || response.redirected) return;
      var data = await response.json();
      if (!data.selected_exists) {
        window.location.replace(panel.dataset.newUrl);
        return;
      }
      var signature = JSON.stringify(data.entries.map(function (entry) {
        return [entry.url, entry.question];
      }));
      if (signature === historySignature) return;
      var fragment = document.createDocumentFragment();
      data.entries.forEach(function (entry) {
        var link = document.createElement("a");
        link.className = "qa-history-entry";
        link.href = entry.url;
        link.title = entry.question;
        link.textContent = entry.question;
        if (String(entry.id) === panel.dataset.selectedChat) {
          link.classList.add("active");
          link.setAttribute("aria-current", "page");
        }
        fragment.appendChild(link);
      });
      list.replaceChildren(fragment);
      historySignature = signature;
      panel.querySelector("[data-history-empty]").hidden = data.entries.length > 0;
    } catch (error) {
      // Keep the rendered history usable during temporary network failures.
    } finally {
      pending = false;
    }
  }

  window.setInterval(refreshHistory, 15000);
  window.addEventListener("focus", refreshHistory);
  document.addEventListener("visibilitychange", refreshHistory);
  refreshHistory();

  panel.querySelector("[data-question-form]").addEventListener("submit", function () {
    var button = this.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = button.dataset.submitLabel;
    this.setAttribute("aria-busy", "true");
  });
})();
