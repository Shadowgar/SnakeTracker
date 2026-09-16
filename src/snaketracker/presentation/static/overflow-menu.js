(() => {
  "use strict";

  const triggers = Array.from(document.querySelectorAll(".overflow-trigger[popovertarget]"));
  const triggerFor = (menu) => triggers.find(
    (trigger) => trigger.getAttribute("popovertarget") === menu.id
  );

  const place = (menu) => {
    const trigger = triggerFor(menu);
    if (!(trigger instanceof HTMLElement)) return;
    const margin = 8;
    const gap = 4;
    const triggerBox = trigger.getBoundingClientRect();
    const menuBox = menu.getBoundingClientRect();
    let left = triggerBox.right - menuBox.width;
    let top = triggerBox.bottom + gap;
    if (top + menuBox.height > window.innerHeight - margin) {
      top = triggerBox.top - menuBox.height - gap;
    }
    left = Math.max(margin, Math.min(left, window.innerWidth - menuBox.width - margin));
    top = Math.max(margin, Math.min(top, window.innerHeight - menuBox.height - margin));
    menu.style.left = `${Math.round(left)}px`;
    menu.style.top = `${Math.round(top)}px`;
  };

  triggers.forEach((trigger) => trigger.addEventListener("click", (event) => {
    event.stopPropagation();
  }));

  document.addEventListener("toggle", (event) => {
    const menu = event.target;
    if (!(menu instanceof HTMLElement) || !menu.matches(".overflow-menu > nav[popover]")) return;
    const trigger = triggerFor(menu);
    const open = menu.matches(":popover-open");
    if (trigger instanceof HTMLElement) trigger.setAttribute("aria-expanded", String(open));
    if (!open) return;
    requestAnimationFrame(() => {
      place(menu);
      const firstAction = menu.querySelector("a, button");
      if (firstAction instanceof HTMLElement) firstAction.focus({ preventScroll: true });
    });
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const menu = document.querySelector(".overflow-menu > nav[popover]:popover-open");
    if (!(menu instanceof HTMLElement)) return;
    const trigger = triggerFor(menu);
    requestAnimationFrame(() => {
      if (trigger instanceof HTMLElement) trigger.focus({ preventScroll: true });
    });
  });

  const reposition = () => {
    const menu = document.querySelector(".overflow-menu > nav[popover]:popover-open");
    if (menu instanceof HTMLElement) place(menu);
  };
  window.addEventListener("resize", reposition);
  document.addEventListener("scroll", reposition, true);
})();
