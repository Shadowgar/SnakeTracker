document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-copy-id]");
  if (!button) return;
  const value = button.dataset.copyId;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    const original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(() => { button.textContent = original; }, 1600);
  } catch {
    button.textContent = "Copy unavailable";
  }
});
