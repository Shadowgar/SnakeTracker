"use strict";

const typeSelect = document.querySelector("[data-inventory-type]");
const unitSelect = document.querySelector("[data-inventory-unit]");
const foodFields = document.querySelector("[data-food-fields]");
const categorySelect = document.querySelector("[data-food-category]");
const preyFields = document.querySelector("[data-prey-fields]");
const foodTypeSelect = document.querySelector("[data-food-type]");
const foodTypeLabel = document.querySelector("[data-food-type-label]");
const sizeSelect = document.querySelector("[data-size-stage]");
const preparationField = document.querySelector("[data-preparation-field]");
const preparationSelect = document.querySelector("[data-preparation-method]");

const setControlState = (container, enabled) => {
  if (!(container instanceof HTMLElement)) return;
  container.hidden = !enabled;
  for (const control of container.querySelectorAll("input, select, textarea")) {
    control.disabled = !enabled;
  }
};

const synchronizeCategory = () => {
  if (!(categorySelect instanceof HTMLSelectElement)) return;
  const category = categorySelect.value;
  const prey = category === "whole_prey" || category === "insect";
  setControlState(preyFields, prey);
  setControlState(preparationField, category === "whole_prey");
  if (foodTypeLabel instanceof HTMLElement) {
    foodTypeLabel.textContent = category === "insect" ? "Feeder type" : "Prey type";
  }
  if (foodTypeSelect instanceof HTMLSelectElement) {
    for (const option of foodTypeSelect.options) {
      const categories = option.dataset.foodCategories;
      const available = !option.value || (categories || "").split(",").includes(category);
      option.hidden = !available;
      option.disabled = !available;
    }
    if (foodTypeSelect.selectedOptions[0]?.disabled) foodTypeSelect.value = "";
    foodTypeSelect.required = prey;
  }
  if (sizeSelect instanceof HTMLSelectElement) sizeSelect.required = category === "whole_prey";
  if (preparationSelect instanceof HTMLSelectElement) {
    preparationSelect.required = category === "whole_prey";
  }
};

const synchronizeType = () => {
  if (!(typeSelect instanceof HTMLSelectElement) || !(unitSelect instanceof HTMLSelectElement)) {
    return;
  }
  const type = typeSelect.value;
  for (const option of unitSelect.options) {
    const types = option.dataset.inventoryTypes;
    const available = !option.value || (types || "").split(",").includes(type);
    option.hidden = !available;
    option.disabled = !available;
  }
  if (unitSelect.selectedOptions[0]?.disabled) unitSelect.value = "";
  const food = type === "food";
  setControlState(foodFields, food);
  if (categorySelect instanceof HTMLSelectElement) categorySelect.required = food;
  if (food) synchronizeCategory();
};

if (typeSelect instanceof HTMLSelectElement && unitSelect instanceof HTMLSelectElement) {
  typeSelect.addEventListener("change", synchronizeType);
  categorySelect?.addEventListener("change", synchronizeCategory);
  synchronizeType();
}
