"use strict";

(() => {
  const form = document.querySelector("[data-inventory-acquisition]");
  if (!(form instanceof HTMLFormElement)) return;
  const existing = form.querySelector("[data-acquisition-existing]");
  const createNew = form.querySelector("[data-acquisition-new]");
  const item = form.querySelector("[data-acquisition-item]");
  const stock = form.querySelector("[data-current-stock]");
  const quantityLabel = form.querySelector("[data-quantity-label]");
  const quantityHelp = form.querySelector("[data-quantity-help]");

  const toggleSection = (section, enabled) => {
    if (!(section instanceof HTMLElement)) return;
    section.hidden = !enabled;
  };
  const synchronize = () => {
    const selection = form.querySelector('input[name="item_selection"]:checked')?.value;
    const useExisting = selection === "existing";
    toggleSection(existing, useExisting);
    toggleSection(createNew, !useExisting);
    if (item instanceof HTMLSelectElement) item.disabled = !useExisting;
    const quantity = form.elements.namedItem("quantity");
    if (quantity instanceof HTMLInputElement) quantity.disabled = !useExisting;
    const option = item instanceof HTMLSelectElement ? item.selectedOptions[0] : undefined;
    if (stock instanceof HTMLElement) {
      stock.textContent = option?.value ? `Current stock: ${option.dataset.stock}` : "Choose an item to see current stock.";
    }
    const mode = form.querySelector('input[name="recording_mode"]:checked')?.value;
    const assigning = useExisting && mode === "existing_cost";
    if (quantityLabel instanceof HTMLElement) {
      quantityLabel.textContent = assigning ? "Quantity whose cost is being added" : "Quantity to add";
    }
    if (quantityHelp instanceof HTMLElement) {
      quantityHelp.textContent = assigning
        ? "This assigns cost only to stock currently on hand. It does not increase the quantity."
        : option?.dataset.unit ? `Enter the amount to add in ${option.dataset.unit}.` : "";
    }
  };
  form.addEventListener("change", synchronize);
  synchronize();
})();
