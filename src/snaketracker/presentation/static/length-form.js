"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const value = document.querySelector("[data-length-value]");
  const unit = document.querySelector("[data-length-unit]");
  const confirmation = document.querySelector("[data-length-original]");
  if (!value || !unit) return;
  const update = () => {
    value.step = unit.value === "mm" ? "0.1" : "0.01";
    if (confirmation) confirmation.textContent = `Replace ${confirmation.dataset.lengthOriginal} with ${value.value || "…"} ${unit.value}.`;
  };
  value.addEventListener("input", update);
  unit.addEventListener("change", update);
  update();
});
