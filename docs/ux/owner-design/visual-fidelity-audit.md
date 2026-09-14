# Owner design-board visual fidelity audit

Final comparison date: September 14, 2026. Correction base:
`f3298aa19b0acccbf3c840f5db232b2570418fa8`. Qualified ARM64 image:
`sha256:2c7f66d0baaac69c6a29cd3eff9b24332e0a4d6742677aec584efd84c4c0070c`.

This is a human visual comparison of the preserved [owner design
board](care-keeper-owner-design-board.png) with the final real application captures. It evaluates
image prominence, density, hierarchy, desktop space use, mobile card behavior, navigation
character, and polish. Automated geometry and axe results are supporting evidence only.

## Required owner-review surfaces

| Surface | What changed | What now matches the board | Intentional difference and why | Remaining visual gap |
| --- | --- | --- | --- | --- |
| [Today mobile](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/mobile-390x844-today.png) | Added four compact workload metrics, richer thumbnail-led care cards, tighter typography, and a floating Add Care action | Strong branded header, immediate date context, Overdue/Due today/Upcoming grouping, dense scannable rows, purple status/action language, and fixed bottom navigation | Buttons name the real supported action rather than using the board's overflow menus | Real care-action labels make some cards slightly wider/taller than the concept; no major fidelity blocker remains |
| [Today desktop](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/desktop-1440x900-today.png) | Rebalanced the wide canvas into three parallel care columns and a four-part summary | Fixed sidebar, useful horizontal composition, dashboard metrics, compact photo rows, and visible status hierarchy | The board's speculative Insights strip is omitted because those cross-animal facts are not an accepted current capability | The real workload can extend below one viewport; no stretched-mobile presentation remains |
| [Animals mobile](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/mobile-390x844-animals.png) | Replaced tall placeholder cards with a compact two-column photo grid and compact filter/add controls | Photo-first identity, comparable image-to-copy balance, subtle type/status metadata, dark cards, and mobile density | Scientific names are retained because they are useful Directory identity; filters scroll instead of using a single mock dropdown | Long names truncate in the dense grid and open fully on profile; no ordinary common-species placeholder gap remains |
| [Animals desktop](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/desktop-1440x900-animals.png) | Built a true four-column collection grid with large upper-card imagery and compact lower metadata | Wide desktop canvas, card rhythm, image prominence, category filters, sidebar navigation, and restrained purple accents | Real next-care state replaces the board's illustrative sex/health icons when more actionable | The 21-item qualification collection continues below the viewport, as expected for real collection size |
| [Animal Profile mobile](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/mobile-390x844-animal-profile-reference.png) | Promoted the visual to an edge-to-edge hero, moved identity/status/next care directly beneath it, and tightened tabs/actions | Substantial photography, name/species hierarchy, compact next-care panel, Overview/History/Trends/Care navigation, and quick care actions | Reference photos carry a tiny attribution and owner-photo action because they must not be presented as the keeper's individual animal | The deliberately long qualification name wraps more than the short board example; normal names retain the intended balance |
| [Animal Profile desktop](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/desktop-1440x900-animal-profile-reference.png) | Rebuilt the hero as identity/photo/next-care columns spanning the content width | Wide photographic hero, left identity, right next-care focus, horizontal tabs, action tiles, and two-column detail content | No health classification, telemetry, or handling facts are invented; exact reference attribution stays below the photo | The long test name occupies more vertical space than “Bob”; no structural desktop gap remains |
| [Calendar mobile](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/mobile-390x844-calendar.png) | Added the compact current-week strip, tightened agenda grouping, propagated animal thumbnails, and added the floating care action | Date-first agenda, thumbnail-led rows, due-state grouping, one-handed action, and bottom navigation closely match the board | Existing Agenda/Month modes and actual reminder dates replace the board's illustrative August data | Month mode is intentionally outside this capture; Agenda has no major remaining visual gap |
| [Quick Log mobile](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/mobile-390x844-quick-log.png) | Added a selected-animal visual, compact two-column capability grid, and real recent-action list | Focused one-handed flow, clear animal selection, action tiles, recent activity, premium dark panel, and bottom navigation | Available actions are derived from the animal type; recent items use real stored care records rather than the board's fixed examples | Some animals expose five rather than eight actions because unsupported actions are not fabricated |
| [Enclosures mobile](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/mobile-390x844-enclosures.png) | Converted plain rows into compact image-led habitat cards using the lead occupant visual | Prominent visual identity, occupant count, type, real next-care fact, dense rows, and fixed navigation | Temperature/humidity and enclosure photography are omitted because neither is stored; occupant imagery is the approved practical fallback | Repeated lead-occupant group imagery can occur for unlinked animals, but it is meaningful and polished rather than an empty mark |
| [Enclosures desktop](../../evidence/m6.6-species-aware-husbandry/a-universal-directory/screenshots/desktop-1440x900-enclosures.png) | Rebuilt the list as a three-column visual grid with broad image regions and compact facts | True desktop grid, habitat-card rhythm, large visuals, occupancy/type/status hierarchy, and strong wide-canvas use | Occupant imagery substitutes for future enclosure photos; no telemetry is fabricated | A dedicated keeper-uploaded enclosure-photo capability remains future scope, not a fidelity blocker for this tranche |

## Other audited surfaces

| Surface | Board comparison and disposition |
| --- | --- |
| Inventory | The accepted M6.5 card/summary hierarchy already matches the shared dark product language. It remains stock-fact-first rather than artificially photo-led. |
| Reports | Existing chart-led reports and real totals already provide stronger factual visualization than the board's small examples. Shared width, headings, cards, and navigation remain consistent. |
| More | Compact grouped utility rows and account treatment already align with the board's navigation character; no unrelated redesign was introduced. |
| Onboarding/setup | Existing setup is resumable and non-linear by requirement. Focused cards and one clear next action preserve the board's progressive character without fabricating completed steps or forcing a rigid wizard. |

## Cross-product imagery and fidelity result

One Animal visual resolver now supplies Animals, Today, Calendar, profiles, Quick Log, Enclosures,
and search using keeper photo → licensed reference photo → reviewed species illustration → polished
group fallback. The final 20-animal fixture uses deterministic 640×480 WebP derivatives derived
from the checked-in group visuals, replacing the previous lime/initial placeholders while retaining
twenty distinct attachment hashes. Common linked species resolve through iNaturalist, Wikimedia
Commons, or GBIF; the requested Boa photo is retained as a CC BY-NC species reference with a tiny
attribution line.

The final captures and the board are immediately recognizable as the same product design. The
remaining differences are deliberate consequences of real Care Keeper data and capabilities, not
major visual omissions. No temperature, humidity, health, handling, enclosure-photo, or other
unsupported fact was fabricated to imitate concept content.
