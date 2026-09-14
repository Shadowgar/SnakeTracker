(() => {
  "use strict";

  document.querySelectorAll("[data-taxon-combobox]").forEach((root) => {
    const input = root.querySelector('[role="combobox"]');
    const list = root.querySelector("[data-taxon-results]");
    const status = root.querySelector("[data-taxon-status]");
    const taxonId = root.querySelector("[data-taxon-id]");
    const form = root.closest("form");
    const groupField = root.dataset.groupField;
    if (!input || !list || !status || !taxonId || !form || !groupField) return;

    let timer = null;
    let controller = null;
    let activeIndex = -1;

    const groupInput = form.elements.namedItem(groupField);
    const close = () => {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      activeIndex = -1;
    };

    const options = () => Array.from(list.querySelectorAll('[role="option"]'));
    const activate = (index) => {
      const rows = options();
      if (!rows.length) return;
      activeIndex = (index + rows.length) % rows.length;
      rows.forEach((row, rowIndex) => row.setAttribute("aria-selected", String(rowIndex === activeIndex)));
      const active = rows[activeIndex];
      input.setAttribute("aria-activedescendant", active.id);
      active.scrollIntoView({ block: "nearest" });
    };
    const select = (row) => {
      taxonId.value = row.dataset.taxonId || "";
      input.value = row.dataset.commonName || row.dataset.scientificName || "";
      status.textContent = `Selected ${input.value}, ${row.dataset.scientificName}.`;
      close();
    };
    const render = (payload) => {
      list.replaceChildren();
      const records = Array.isArray(payload.records) ? payload.records : [];
      records.forEach((record, index) => {
        const row = document.createElement("li");
        row.id = `${input.id}-option-${index}`;
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", "false");
        row.tabIndex = -1;
        row.dataset.taxonId = record.taxon_id;
        row.dataset.commonName = record.common_name || "";
        row.dataset.scientificName = record.scientific_name;
        const common = document.createElement("strong");
        common.textContent = record.common_name || record.scientific_name;
        const scientific = document.createElement("i");
        scientific.textContent = record.scientific_name;
        const detail = document.createElement("small");
        detail.textContent = [record.family, record.group, record.stale ? "saved result" : ""]
          .filter(Boolean)
          .join(" · ");
        row.append(common, scientific, detail);
        row.addEventListener("pointerdown", (event) => {
          event.preventDefault();
          select(row);
        });
        list.append(row);
      });
      if (records.length) {
        list.hidden = false;
        input.setAttribute("aria-expanded", "true");
        status.textContent = payload.message || `${records.length} species suggestions available.`;
      } else {
        close();
        status.textContent = payload.message || "No matching species. You can keep a manual species entry.";
      }
    };
    const search = async () => {
      const query = input.value.trim();
      const group = groupInput ? groupInput.value : "";
      if (query.length < 2) {
        status.textContent = "Enter at least 2 characters to search.";
        close();
        return;
      }
      controller?.abort();
      controller = new AbortController();
      status.textContent = "Searching species…";
      try {
        const response = await fetch(`/api/directory/search?group=${encodeURIComponent(group)}&q=${encodeURIComponent(query)}`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        const payload = await response.json();
        if (!response.ok && !payload.records) throw new Error("search unavailable");
        render(payload);
      } catch (error) {
        if (error.name === "AbortError") return;
        close();
        status.textContent = "Species search is temporarily unavailable. You can enter the species manually.";
      }
    };

    input.addEventListener("input", () => {
      taxonId.value = "";
      window.clearTimeout(timer);
      timer = window.setTimeout(search, 320);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        activate(activeIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        activate(activeIndex - 1);
      } else if (event.key === "Enter" && activeIndex >= 0) {
        event.preventDefault();
        select(options()[activeIndex]);
      } else if (event.key === "Escape") {
        close();
      }
    });
    input.addEventListener("blur", () => window.setTimeout(close, 120));
    groupInput?.addEventListener("change", () => {
      taxonId.value = "";
      close();
      if (input.value.trim().length >= 2) search();
    });
  });
})();
