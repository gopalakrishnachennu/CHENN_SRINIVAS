document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("click", (ev) => {
      const msg = el.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(msg)) {
        ev.preventDefault();
      }
    });
  });
});
