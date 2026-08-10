# M4 Real-Browser Evidence

Result: **Pass after one responsive-layout correction**

## Enclosure-history owner-review correction

The browser regression now assigns Nyx first to `55 Gallon Tank` and then to `10 Gallon Tank`.
It verifies that the profile links to `10 Gallon Tank`, the former enclosure has no occupant, and
the current enclosure lists Nyx. The effective timeline renders `Moved to 55 Gallon Tank` followed
by `55 Gallon Tank → 10 Gallon Tank`. Each technical-audit item includes the target enclosure
name and UUID, and neither assignment item renders a Void action. The rebuilt development stack is
healthy at `http://localhost:8081`; its existing household data was preserved.

## Corrected keeper UX requalification

The owner-required UX correction was rerun against the final amd64 Docker image on August 10. A
fresh browser household registered Nyx, used focused feeding/weight/length pages, displayed the
entered `1 small rat`, `42 g`, `512 g`, and `925 mm` facts, kept the technical audit collapsed, and
selected an immutable profile photo that then appeared on the animal listing. Desktop and 390-by-
844 layouts had no overlap, and the browser console contained zero errors and zero warnings.

- [Corrected desktop animal overview](keeper-ux-desktop-overview.png) — SHA-256
  `9400f6763f386da9309489c302b6f0232cd2ad3823edebbafc5345f29f338ac9`
- [Corrected desktop measurements](keeper-ux-desktop-measurements.png) — SHA-256
  `6d03773ed430b2cd57dbcfbd0d9dab3d27fa6e2d3e3de9864ec4ab0f184c8ac8`
- [Corrected mobile animal overview](keeper-ux-mobile-overview.png) — SHA-256
  `545f67f41024e722152093a475fb9e6373c6f7685311371eb90a77dfee364e0f`
- [Mobile animal list with selected photo](keeper-ux-mobile-list-photo.png) — SHA-256
  `1dd7d899dde14dbabd492bd5c91294e83f0abf6c2f970d8868dd2e58b83b3017`

## Original implementation qualification

Playwright exercised fresh Docker/Nginx installations at isolated loopback ports. The journey
created the first household/owner, logged in, registered Nyx, recorded feeding/weight/length/shed/
bath facts, created and assigned an enclosure, recorded cleaning and water change, uploaded a
profile photo, corrected a feeding, inspected effective/audit history, queued a backup, configured
its schedule, and verified protected navigation.

The initial 390-by-844 capture revealed overlapping profile action links. The shared responsive
layout was corrected to a two-column grid with bounded touch targets and the same viewport was
rerun. The final browser console contained zero errors and zero warnings.

- [Desktop animal home](desktop-home.png) — SHA-256
  `36bfbdd3c38f204cdfc5a0b4388ef380ffb7352bb20353fb84703cd63acc1658`
- [Desktop effective timeline](desktop-timeline.png) — SHA-256
  `655d6db83a78f0c106d0783f744bbba4357c1cbd093e01987f54404c54295b2b`
- [Final mobile animal profile](mobile-animal-profile.png) — SHA-256
  `f488bf12213e80cb8913dacf7f2abb92492e3d4af197a7712c923823964cb034`

The user's local preview is intentionally separate from the synthetic evidence database and is
available at `http://localhost:8081`.
