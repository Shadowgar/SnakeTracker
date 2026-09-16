(() => {
  "use strict";

  const menus = () => Array.from(document.querySelectorAll("details.overflow-menu[open]"));
  const close = (menu) => {
    menu.removeAttribute("open");
    const trigger = menu.querySelector("summary");
    if (trigger instanceof HTMLElement) trigger.setAttribute("aria-expanded", "false");
  };

  document.addEventListener("toggle", (event) => {
    const menu = event.target;
    if (!(menu instanceof HTMLDetailsElement) || !menu.classList.contains("overflow-menu")) return;
    const trigger = menu.querySelector("summary");
    if (trigger instanceof HTMLElement) trigger.setAttribute("aria-expanded", String(menu.open));
    if (menu.open) menus().filter((item) => item !== menu).forEach(close);
  }, true);

  document.addEventListener("pointerdown", (event) => {
    menus().filter((menu) => !menu.contains(event.target)).forEach(close);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = menus();
    if (!open.length) return;
    event.preventDefault();
    const menu = open.at(-1);
    const trigger = menu.querySelector("summary");
    close(menu);
    if (trigger instanceof HTMLElement) trigger.focus();
  });
})();
