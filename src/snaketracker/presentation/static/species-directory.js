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

    const referenceRoot = form.querySelector("[data-reference-photo]");
    const referenceImage = referenceRoot?.querySelector("[data-reference-photo-image]");
    const referencePlaceholder = referenceRoot?.querySelector("[data-reference-photo-placeholder]");
    const referenceCopy = referenceRoot?.querySelector("[data-reference-photo-copy]");
    const referenceOptions = referenceRoot?.querySelector("[data-reference-photo-options]");
    const referencePlaceholderInitial = referenceRoot?.querySelector("[data-reference-photo-placeholder-initial]");
    const morphSuggestions = form.querySelector("[data-morph-suggestions]");
    const geneticsSuggestions = form.querySelector("[data-genetics-suggestions]");
    const morphSuggestionChips = form.querySelector("[data-morph-suggestion-chips]");
    const geneticsSuggestionChips = form.querySelector("[data-genetics-suggestion-chips]");
    const morphField = form.querySelector("[data-morph-field]");
    const geneticsField = form.querySelector("[data-genetics-field]");
    const morphExample = form.querySelector("[data-morph-example]");
    const nameInput = form.elements.namedItem("name");

    const setIdentityOptions = (target, values) => {
      if (!target) return;
      target.replaceChildren(...values.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        return option;
      }));
    };
    const setIdentityChips = (target, field, values) => {
      if (!target || !field) return;
      target.replaceChildren();
      target.hidden = values.length === 0;
      if (!values.length) return;
      const label = document.createElement("span");
      label.textContent = "Previously used for this species:";
      target.append(label);
      values.forEach((value) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "identity-suggestion-chip";
        button.textContent = value;
        button.addEventListener("click", () => {
          field.value = value;
          field.focus();
        });
        target.append(button);
      });
    };
    const loadIdentitySuggestions = async (selectedTaxonId) => {
      setIdentityOptions(morphSuggestions, []);
      setIdentityOptions(geneticsSuggestions, []);
      setIdentityChips(morphSuggestionChips, morphField, []);
      setIdentityChips(geneticsSuggestionChips, geneticsField, []);
      if (!selectedTaxonId || (!morphSuggestions && !geneticsSuggestions)) return;
      try {
        const response = await fetch(`/api/directory/${encodeURIComponent(selectedTaxonId)}/identity-suggestions`, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const payload = await response.json();
        const morphs = Array.isArray(payload.morphs) ? payload.morphs : [];
        const genetics = Array.isArray(payload.genetics) ? payload.genetics : [];
        setIdentityOptions(morphSuggestions, morphs);
        setIdentityOptions(geneticsSuggestions, genetics);
        setIdentityChips(morphSuggestionChips, morphField, morphs);
        setIdentityChips(geneticsSuggestionChips, geneticsField, genetics);
      } catch (_error) {
        // Suggestions are optional; free text remains available.
      }
    };
    const updateReferencePlaceholder = () => {
      if (!referencePlaceholder) return;
      const group = groupInput?.value || "animal";
      referencePlaceholder.className = `reference-photo-placeholder fallback-${group}`;
      if (referencePlaceholderInitial) {
        const name = nameInput instanceof HTMLInputElement ? nameInput.value.trim() : "";
        referencePlaceholderInitial.textContent = name ? name.charAt(0).toUpperCase() : "A";
      }
    };
    const resetReferencePhoto = (copy = "Reference images are available when a supported Directory species is linked. You can add a photo of your animal after creation.") => {
      if (!referenceRoot) return;
      if (referenceImage) {
        referenceImage.hidden = true;
        referenceImage.removeAttribute("src");
        referenceImage.alt = "";
      }
      if (referencePlaceholder) referencePlaceholder.hidden = false;
      updateReferencePlaceholder();
      if (referenceOptions) referenceOptions.hidden = true;
      if (referenceCopy) referenceCopy.textContent = copy;
      const noPhoto = form.querySelector('input[name="photo_preference"][value="none"]');
      if (noPhoto) noPhoto.checked = true;
    };
    const showUnavailableReferencePhoto = () => resetReferencePhoto(
      "No licensed species reference image is available for this Directory record. You can add a photo of your animal after creation."
    );
    const showReferencePhoto = (row) => {
      if (!referenceRoot || row.dataset.referenceImageAvailable !== "true") {
        showUnavailableReferencePhoto();
        return;
      }
      if (referenceImage) {
        referenceImage.src = row.dataset.referenceImageUrl || "";
        referenceImage.alt = `Species reference image for ${row.dataset.commonName || row.dataset.scientificName}`;
        referenceImage.hidden = false;
      }
      if (referencePlaceholder) referencePlaceholder.hidden = true;
      if (referenceOptions) referenceOptions.hidden = false;
      if (referenceCopy) referenceCopy.textContent = `Species reference image available · ${(row.dataset.imageLicenseCode || "").replaceAll("-", " ").toUpperCase()} · ${row.dataset.imageCreator || "attribution available"}. This is a general photo of the species, not your individual animal.`;
    };
    referenceImage?.addEventListener("error", showUnavailableReferencePhoto);

    const updateMorphExample = () => {
      if (!morphExample) return;
      const examples = {
        snake: "Examples for snakes: Banana, Pastel, Albino, Piebald.",
        lizard: "Examples for lizards: a color/pattern morph or locality.",
        spider: "Example for spiders: a recognized color form or locality, when applicable.",
        scorpion: "Record a recognized form or locality only when it is meaningful.",
      };
      morphExample.textContent = examples[groupInput?.value] || "Record a recognized variant only when applicable.";
    };

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
      showReferencePhoto(row);
      loadIdentitySuggestions(taxonId.value);
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
        row.dataset.referenceImageAvailable = String(record.reference_image_available === true);
        row.dataset.referenceImageUrl = record.reference_image_url || "";
        row.dataset.imageCreator = record.image_creator || "";
        row.dataset.imageLicenseCode = record.image_license_code || "";
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
      resetReferencePhoto();
      loadIdentitySuggestions("");
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
      resetReferencePhoto();
      updateMorphExample();
      close();
      if (input.value.trim().length >= 2) search();
    });
    if (nameInput instanceof HTMLInputElement) {
      nameInput.addEventListener("input", updateReferencePlaceholder);
    }
    updateReferencePlaceholder();
    updateMorphExample();
  });
})();
