(() => {
  "use strict";

  const selector = document.querySelector("[data-quick-log-selector]");
  if (!(selector instanceof HTMLSelectElement)) return;
  const panels = Array.from(document.querySelectorAll("[data-quick-log-animal]"));
  const update = () => {
    panels.forEach((panel) => {
      panel.hidden = panel.getAttribute("data-quick-log-animal") !== selector.value;
    });
  };
  selector.addEventListener("change", update);
  update();
})();
