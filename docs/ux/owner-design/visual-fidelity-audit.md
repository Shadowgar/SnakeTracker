# Owner design-board visual fidelity audit

Audit date: September 14, 2026. Baseline head:
`5c76800ce781117bdf65ec4957712c792fe43a0b`.

This comparison used the preserved [owner design board](care-keeper-owner-design-board.png) and
the actual 390×844/1440×900 browser captures from the accepted M6 passes and current M6.6-A
qualification. It is a photographic audit, not a source-only review.

| Surface | Approved design | Current product | Gap | Correction |
| --- | --- | --- | --- | --- |
| Today | Compact status summary, three care groups, animal thumbnails, floating quick action | Dark three-group layout and dense cards already align; most animals show generic marks | Animal identity is inconsistent and desktop cards are visually flatter | Route every subject through the unified Animal visual resolver; tighten thumbnail/card treatment and retain real due facts only |
| Animals | Photo-first two-column mobile and multi-column desktop collection | Responsive 2/4-column grid exists, but most linked animals show green-dot/initial placeholders | Image prominence exists structurally but not in content | Use personal photo → licensed reference → species illustration → group fallback on every card |
| Animal Profile | Large image-led mobile header and wide desktop hero | Strong facts/navigation exist; visual is a small square beside text | Hero lacks the board's visual weight | Introduce a responsive wide hero while retaining next-care, care tabs, provenance, and owner-photo actions |
| Calendar | Compact date context and thumbnail-led agenda rows | Agenda/month structure is dense and readable | Generic identity marks weaken scanning; desktop composition is mostly list-like | Reuse resolved thumbnails and refine compact event-card grouping without inventing dates or statuses |
| Quick Log | Focused animal picker, action tile grid, recent actions | Animal-grouped cards expose real supported actions | Cards are tall, text-heavy, and frequently lack imagery | Add resolved thumbnails and a denser action-tile composition; do not invent unsupported actions or a new recent-actions model |
| Enclosures | Prominent habitat/occupant imagery with compact facts | Responsive grid, occupants, type, status, and maintenance facts exist | Cards read as database rows and mostly show generic marks | Use lead-occupant resolved imagery, enlarge visual region, retain only real occupancy/plant/type/maintenance facts |
| Inventory | Compact stock cards and dashboard-like summary | Current mobile/desktop cards already use strong hierarchy and real stock facts | Less image-led than animal surfaces, appropriately | Preserve M6.5 accepted semantics; only normalize shared headings/status/card polish |
| Reports | Visual summaries with strong metrics and compact navigation | Current report entry cards and detailed charts are already visually structured | Entry page has more unused space than board examples | Preserve charts and real totals; align shared density without inventing insights |
| More | Compact grouped utility navigation | Grouped dark action rows and account card already align | Minor spacing/typography variance | Retain structure; normalize reusable action-tile and section-heading styling |
| Onboarding/setup | Six short, progressive steps with one clear action | Real setup checklist and recommended next step exist | One long workspace page is less guided than the board's staged examples | Preserve non-linear real setup semantics while tightening cards and focused desktop width; do not invent completed steps |

## Intentional differences

- The board's temperature, humidity, health, handling, and other example facts are omitted unless
  Care Keeper already stores them.
- Quick Log continues to expose capability-driven animal actions rather than the board's fixed
  example action set.
- Onboarding remains resumable and non-linear because existing requirements permit setup in any
  order.
- Reference visuals are marked accessibly as species references and never represented as a
  keeper-owned photograph.

## Acceptance lens

Final comparison must use new application captures beside the same board and judge image
prominence, density, hierarchy, desktop space use, mobile card behavior, navigation character, and
overall polish. Axe and geometry results are supporting evidence only.
