(function () {
  "use strict";
  var tabs = Array.from(document.querySelectorAll("[data-demo-tab]"));
  function select(tab) {
    tabs.forEach(function (item) {
      var active = item === tab;
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
      document.getElementById(item.dataset.demoTab).hidden = !active;
    });
  }
  tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function () { select(tab); });
    tab.addEventListener("keydown", function (event) {
      var target;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") target = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      if (target === undefined) return;
      event.preventDefault();
      select(tabs[target]);
      tabs[target].focus();
    });
  });
})();
