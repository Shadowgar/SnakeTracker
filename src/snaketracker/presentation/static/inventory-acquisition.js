"use strict";

(() => {
  const form = document.querySelector("[data-inventory-acquisition]");
  if (!(form instanceof HTMLFormElement)) return;

  const existing = form.querySelector("[data-acquisition-existing]");
  const createNew = form.querySelector("[data-acquisition-new]");
  const item = form.querySelector("[data-acquisition-item]");
  const itemSummary = form.querySelector("[data-selected-item-summary]");
  const actionField = form.querySelector("[data-acquisition-action]");
  const existingFields = form.querySelector("[data-existing-fields]");
  const payment = form.querySelector("[data-acquisition-payment]");
  const actions = form.querySelector("[data-acquisition-actions]");
  const quantityLabel = form.querySelector("[data-quantity-label]");
  const quantityHelp = form.querySelector("[data-quantity-help]");
  const assignmentNote = form.querySelector("[data-cost-assignment-note]");
  const amountLabel = form.querySelector("[data-amount-label]");
  const amountHelp = form.querySelector("[data-amount-help]");
  const submitLabel = form.querySelector("[data-submit-label]");

  const setSection = (section, visible) => {
    if (!(section instanceof HTMLElement)) return;
    section.hidden = !visible;
    for (const control of section.querySelectorAll("input, select, textarea, button")) {
      if (!(control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement || control instanceof HTMLButtonElement)) continue;
      if (!visible && !control.disabled) {
        control.disabled = true;
        control.dataset.acquisitionDisabled = "true";
      } else if (visible && control.dataset.acquisitionDisabled === "true") {
        control.disabled = false;
        delete control.dataset.acquisitionDisabled;
      }
    }
  };

  const synchronize = () => {
    const selection = form.querySelector('input[name="item_selection"]:checked')?.value;
    const useExisting = selection === "existing";
    const useNew = selection === "new";
    setSection(existing, useExisting);
    setSection(createNew, useNew);
    if (item instanceof HTMLSelectElement) item.disabled = !useExisting;

    const option = item instanceof HTMLSelectElement ? item.selectedOptions[0] : undefined;
    const hasItem = useExisting && Boolean(option?.value);
    setSection(itemSummary, hasItem);
    setSection(actionField, hasItem);
    if (hasItem) {
      const name = form.querySelector("[data-selected-item-name]");
      const stock = form.querySelector("[data-current-stock]");
      const cost = form.querySelector("[data-current-cost]");
      if (name instanceof HTMLElement) name.textContent = option?.dataset.name || "Selected item";
      if (stock instanceof HTMLElement) stock.textContent = option?.dataset.stock || "";
      if (cost instanceof HTMLElement) cost.textContent = option?.dataset.cost || "";
    }

    const mode = form.querySelector('input[name="recording_mode"]:checked')?.value;
    const addStock = hasItem && mode === "add_stock";
    const assignCost = hasItem && mode === "existing_cost";
    const hasExistingAction = addStock || assignCost;
    setSection(existingFields, hasExistingAction);
    const quantity = form.elements.namedItem("quantity");
    if (quantity instanceof HTMLInputElement) quantity.disabled = !hasExistingAction;
    setSection(payment, useNew || hasExistingAction);
    setSection(actions, useNew || hasExistingAction);

    if (quantityLabel instanceof HTMLElement) {
      quantityLabel.textContent = assignCost ? "Quantity to assign" : "Quantity";
    }
    if (quantityHelp instanceof HTMLElement) {
      quantityHelp.textContent = option?.dataset.unit
        ? assignCost
          ? `Enter the stock amount in ${option.dataset.unit} whose original cost you are adding.`
          : `Enter the amount received in ${option.dataset.unit}.`
        : "";
    }
    if (assignmentNote instanceof HTMLElement) assignmentNote.hidden = !assignCost;
    if (amountLabel instanceof HTMLElement) {
      amountLabel.textContent = assignCost ? "Amount originally paid" : "Amount paid";
    }
    if (amountHelp instanceof HTMLElement) {
      amountHelp.textContent = assignCost
        ? "Enter the total originally paid for this quantity."
        : "Use $0.00 when you only want to track quantity.";
    }
    if (submitLabel instanceof HTMLElement) {
      submitLabel.textContent = assignCost ? "Save cost information" : "Add inventory";
    }
  };

  form.addEventListener("change", synchronize);
  synchronize();
})();
