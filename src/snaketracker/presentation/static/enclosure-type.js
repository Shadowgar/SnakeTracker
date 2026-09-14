(() => {
  "use strict";

  document.querySelectorAll("[data-enclosure-type-form]").forEach((form) => {
    const select = form.querySelector("[data-enclosure-type-choice]");
    const custom = form.querySelector("[data-custom-enclosure-type]");
    if (!select || !custom) return;
    const input = custom.querySelector("input");
    const update = () => {
      const shown = select.value === "Custom / other";
      custom.hidden = !shown;
      if (input) input.required = shown;
    };
    select.addEventListener("change", update);
    update();
  });
})();
