"use strict";

const inventorySelector = document.querySelector("[data-feeding-inventory]");
const inventoryQuantity = document.querySelector("[data-feeding-inventory-quantity]");
const amountLabel = document.querySelector("[data-feeding-amount-label]");

if (inventorySelector instanceof HTMLSelectElement && inventoryQuantity instanceof HTMLInputElement) {
  const synchronizeInventoryQuantity = () => {
    const linked = inventorySelector.value !== "";
    inventoryQuantity.disabled = !linked;
    inventoryQuantity.required = linked;
    if (linked && inventoryQuantity.value === "") inventoryQuantity.value = "1";
    const option = inventorySelector.selectedOptions[0];
    const fractional = option?.dataset.fractional === "true";
    inventoryQuantity.step = fractional ? "0.001" : "1";
    inventoryQuantity.min = fractional ? "0.001" : "1";
    if (amountLabel instanceof HTMLElement) {
      amountLabel.textContent = linked ? `Amount (${option?.dataset.unit || "unit"})` : "Amount";
    }
  };
  inventorySelector.addEventListener("change", synchronizeInventoryQuantity);
  synchronizeInventoryQuantity();
}
