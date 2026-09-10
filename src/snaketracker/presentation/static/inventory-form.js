"use strict";

const typeSelect = document.querySelector("[data-inventory-type]");
const guidedUnitSection = document.querySelector("[data-unit-section]");

const setControlState = (container, enabled, clear = false) => {
  if (!(container instanceof HTMLElement)) return;
  container.hidden = !enabled;
  for (const control of container.querySelectorAll("input, select, textarea")) {
    control.disabled = !enabled;
    if (!enabled && clear && control instanceof HTMLSelectElement) control.value = "";
    if (!enabled && clear && control instanceof HTMLInputElement && control.type !== "hidden") {
      control.value = "";
    }
  }
};

const selectedOption = (select) =>
  select instanceof HTMLSelectElement ? select.selectedOptions[0] : undefined;

const filterByParent = (select, parent) => {
  if (!(select instanceof HTMLSelectElement)) return;
  for (const option of select.options) {
    const parents = (option.dataset.parent || "").split(",");
    const available = !option.value || parents.includes(parent);
    option.hidden = !available;
    option.disabled = !available;
  }
  if (selectedOption(select)?.disabled) select.value = "";
};

const synchronizeFood = () => {
  const categorySelect = document.querySelector("[data-food-category]");
  if (!(categorySelect instanceof HTMLSelectElement) || categorySelect.disabled) return;
  const category = categorySelect.value;
  const prey = category === "whole_prey" || category === "insect";
  const preyFields = document.querySelector("[data-prey-fields]");
  setControlState(preyFields, prey, !prey);
  const foodType = document.querySelector("[data-food-type]");
  filterByParent(foodType, category);
  if (foodType instanceof HTMLSelectElement) foodType.required = prey;
  const foodTypeLabel = document.querySelector("[data-food-type-label]");
  if (foodTypeLabel instanceof HTMLElement) {
    foodTypeLabel.textContent = category === "insect" ? "Feeder" : "Prey";
  }
  const size = document.querySelector("[data-size-stage]");
  if (size instanceof HTMLSelectElement) size.required = category === "whole_prey";
  const preparationField = document.querySelector("[data-preparation-field]");
  setControlState(preparationField, category === "whole_prey", category !== "whole_prey");
  const preparation = document.querySelector("[data-preparation-method]");
  if (preparation instanceof HTMLSelectElement) {
    preparation.required = category === "whole_prey";
  }
  const stockField = document.querySelector("[data-food-stock-field]");
  const bulk = Boolean(category) && !prey;
  setControlState(stockField, bulk, !bulk);
  const stockBasis = document.querySelector("[data-food-stock-basis]");
  filterByParent(stockBasis, category);
  if (stockBasis instanceof HTMLSelectElement) stockBasis.required = bulk;
};

const synchronizeDetail = (fieldset) => {
  if (!(fieldset instanceof HTMLElement) || fieldset.hidden) return;
  const category = fieldset.querySelector("[data-context-category]");
  const detailField = fieldset.querySelector("[data-context-detail-field]");
  const detail = fieldset.querySelector("[data-context-detail]");
  if (!(category instanceof HTMLSelectElement)) return;
  filterByParent(detail, category.value);
  setControlState(detailField, Boolean(category.value), !category.value);
};

const synchronizeCleaning = () => {
  const form = document.querySelector("[data-cleaning-form]");
  const basisField = document.querySelector("[data-cleaning-basis-field]");
  if (!(form instanceof HTMLSelectElement) || form.disabled) return;
  setControlState(basisField, form.value === "liquid", form.value !== "liquid");
};

const activeUnitPolicy = () => {
  const candidates = document.querySelectorAll("[data-unit-driver], [data-food-category]");
  for (const candidate of Array.from(candidates).reverse()) {
    if (!(candidate instanceof HTMLSelectElement) || candidate.disabled) continue;
    const option = selectedOption(candidate);
    const codes = (option?.dataset.unitCodes || "").split(",").filter(Boolean);
    if (codes.length) return { codes, defaultCode: option?.dataset.defaultUnit || codes[0] };
  }
  return undefined;
};

const synchronizeGuidedUnit = () => {
  const fixedField = document.querySelector("[data-fixed-unit-field]");
  const fixedInput = document.querySelector("[data-fixed-unit-input]");
  const fixedLabel = document.querySelector("[data-fixed-unit-label]");
  const filteredField = document.querySelector("[data-filtered-unit-field]");
  const filteredSelect = document.querySelector("[data-inventory-unit]");
  const startingField = document.querySelector("[data-starting-quantity-field]");
  const reorderField = document.querySelector("[data-reorder-field]");
  const policy = activeUnitPolicy();
  setControlState(guidedUnitSection, Boolean(policy));
  setControlState(startingField, Boolean(policy));
  setControlState(reorderField, Boolean(policy));
  if (!policy) {
    setControlState(fixedField, false);
    setControlState(filteredField, false);
    return;
  }
  const fixed = policy.codes.length === 1;
  setControlState(fixedField, fixed);
  setControlState(filteredField, !fixed);
  if (fixedInput instanceof HTMLInputElement) {
    fixedInput.disabled = !fixed;
    fixedInput.value = fixed ? policy.codes[0] : "";
  }
  if (filteredSelect instanceof HTMLSelectElement) {
    for (const option of filteredSelect.options) {
      const available = policy.codes.includes(option.value);
      option.hidden = !available;
      option.disabled = !available;
    }
    if (fixed || !policy.codes.includes(filteredSelect.value)) {
      filteredSelect.value = policy.defaultCode;
    }
    filteredSelect.disabled = fixed;
  }
  const activeUnit = fixed ? policy.codes[0] : filteredSelect?.value || policy.defaultCode;
  const unitOption = filteredSelect instanceof HTMLSelectElement
    ? Array.from(filteredSelect.options).find((option) => option.value === activeUnit)
    : undefined;
  if (fixedLabel instanceof HTMLElement) fixedLabel.textContent = unitOption?.dataset.label || activeUnit;
  const fractional = unitOption?.dataset.fractional === "true";
  for (const field of [startingField, reorderField]) {
    const input = field?.querySelector("input[type=number]");
    if (input instanceof HTMLInputElement) {
      input.step = fractional ? "0.001" : "1";
      input.inputMode = fractional ? "decimal" : "numeric";
    }
  }
  const help = document.querySelector("[data-starting-quantity-help]");
  if (help instanceof HTMLElement) {
    help.textContent = `Enter the amount already on hand in ${unitOption?.dataset.label || activeUnit}.`;
  }
};

const synchronizeGuided = () => {
  if (!(typeSelect instanceof HTMLSelectElement)) return;
  const type = typeSelect.value;
  for (const fieldset of document.querySelectorAll("[data-context-fields]")) {
    setControlState(fieldset, fieldset.getAttribute("data-context-fields") === type, true);
  }
  synchronizeFood();
  for (const fieldset of document.querySelectorAll("[data-context-fields]")) {
    synchronizeDetail(fieldset);
  }
  synchronizeCleaning();
  synchronizeGuidedUnit();
};

const synchronizeLegacyEdit = () => {
  const unitSelect = document.querySelector("[data-inventory-unit]");
  const foodFields = document.querySelector("[data-food-fields]");
  const categorySelect = document.querySelector("[data-food-category]");
  if (!(typeSelect instanceof HTMLSelectElement) || !(unitSelect instanceof HTMLSelectElement)) {
    return;
  }
  const type = typeSelect.value;
  for (const option of unitSelect.options) {
    const available = !option.value || (option.dataset.inventoryTypes || "").split(",").includes(type);
    option.hidden = !available;
    option.disabled = !available;
  }
  if (selectedOption(unitSelect)?.disabled) unitSelect.value = "";
  const food = type === "food";
  setControlState(foodFields, food, !food);
  if (categorySelect instanceof HTMLSelectElement) categorySelect.required = food;
  synchronizeFood();
};

if (typeSelect instanceof HTMLSelectElement) {
  if (guidedUnitSection instanceof HTMLElement) {
    typeSelect.addEventListener("change", synchronizeGuided);
    for (const control of document.querySelectorAll("select")) {
      if (control !== typeSelect) control.addEventListener("change", synchronizeGuided);
    }
    synchronizeGuided();
  } else {
    typeSelect.addEventListener("change", synchronizeLegacyEdit);
    document.querySelector("[data-food-category]")?.addEventListener("change", synchronizeLegacyEdit);
    synchronizeLegacyEdit();
  }
}
