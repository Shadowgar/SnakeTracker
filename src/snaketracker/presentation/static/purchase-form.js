(() => {
  const form = document.querySelector("[data-purchase-form]");
  if (!form) return;
  const list = form.querySelector("[data-purchase-lines]");
  const add = form.querySelector("[data-add-purchase-line]");
  const count = form.querySelector("[data-purchase-line-count]");
  const totalCheck = form.querySelector("[data-purchase-total-check]");

  const money = (name) => Number.parseFloat(form.elements.namedItem(name)?.value || "0") || 0;
  const update = () => {
    const rows = [...list.querySelectorAll("[data-purchase-line]")];
    rows.forEach((row) => {
      const select = row.querySelector("[data-purchase-item]");
      row.querySelector("[data-purchase-unit]").textContent = select.selectedOptions[0]?.dataset.unit || "";
      row.querySelector("[data-remove-purchase-line]").disabled = rows.length === 1;
    });
    count.textContent = `${rows.length} of 25 receipt items`;
    add.disabled = rows.length >= 25;
    const subtotals = [...form.querySelectorAll('input[name="subtotal"]')]
      .reduce((sum, input) => sum + (Number.parseFloat(input.value) || 0), 0);
    const calculated = subtotals + money("tax") + money("fee") - money("discount");
    const entered = money("total_paid");
    totalCheck.textContent = entered > 0 && Math.abs(calculated - entered) < 0.005
      ? `Totals reconcile at ${calculated.toFixed(2)}.`
      : `Calculated total is ${calculated.toFixed(2)}. Enter the matching amount paid.`;
  };
  add.addEventListener("click", () => {
    const rows = list.querySelectorAll("[data-purchase-line]");
    if (!rows.length || rows.length >= 25) return;
    const row = rows[0].cloneNode(true);
    row.querySelectorAll("input").forEach((input) => { input.value = ""; });
    row.querySelector("select").selectedIndex = 0;
    list.append(row);
    update();
    row.querySelector("select").focus();
  });
  list.addEventListener("click", (event) => {
    const remove = event.target.closest("[data-remove-purchase-line]");
    if (!remove || list.querySelectorAll("[data-purchase-line]").length === 1) return;
    remove.closest("[data-purchase-line]").remove();
    update();
  });
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  update();
})();
