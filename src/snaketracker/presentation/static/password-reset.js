(() => {
  const form = document.querySelector("[data-password-reset-form]");
  const missing = document.querySelector("[data-missing-reset-token]");
  const tokenInput = document.querySelector("[data-reset-token]");
  if (!(form instanceof HTMLFormElement) || !(tokenInput instanceof HTMLInputElement)) return;

  const token = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
  if (token) {
    tokenInput.value = token;
    form.hidden = false;
    if (missing instanceof HTMLElement) missing.hidden = true;
    window.history.replaceState(null, "", window.location.pathname);
    const password = document.querySelector("[data-new-password]");
    if (password instanceof HTMLInputElement) password.focus();
  }
})();
