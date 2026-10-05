(() => {
  "use strict";

  document.querySelectorAll(".animal-section-nav").forEach((nav) => {
    const reveal = (link) => {
      const section = nav.getBoundingClientRect();
      const tab = link.getBoundingClientRect();
      if (tab.left < section.left) nav.scrollLeft += tab.left - section.left;
      else if (tab.right > section.right) nav.scrollLeft += tab.right - section.right;
    };
    nav.addEventListener("focusin", (event) => {
      if (event.target instanceof HTMLAnchorElement) reveal(event.target);
    });
    const active = nav.querySelector('a[aria-current="page"]');
    if (active) reveal(active);
  });
})();
