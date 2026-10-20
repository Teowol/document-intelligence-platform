(function () {
  "use strict";
  document.querySelectorAll("[data-notification]").forEach(function (notification) {
    var timer;
    function dismiss() {
      window.clearTimeout(timer);
      notification.remove();
    }
    notification.querySelector("[data-notification-close]").addEventListener("click", dismiss);
    notification.classList.add("is-active");
    timer = window.setTimeout(dismiss, 5000);
  });
})();
