"use strict";

const inventorySelector = document.querySelector("[data-feeding-inventory]");
const inventoryQuantity = document.querySelector("[data-feeding-inventory-quantity]");

if (inventorySelector instanceof HTMLSelectElement && inventoryQuantity instanceof HTMLInputElement) {
  const synchronizeInventoryQuantity = () => {
    const linked = inventorySelector.value !== "";
    inventoryQuantity.disabled = !linked;
    inventoryQuantity.required = linked;
    if (linked && inventoryQuantity.value === "") inventoryQuantity.value = "1";
  };
  inventorySelector.addEventListener("change", synchronizeInventoryQuantity);
  synchronizeInventoryQuantity();
}
