# CARE KEEPER — X4 AMPHIBIAN EXPANSION

## OWNER DIRECTIVE

X3 has been merged and verified.

Repository: `Shadowgar/SnakeTracker`

Starting main commit:

`4d7d769b804cd2aebafa6d4fc901f5ca4e247c84`

**Proceed with X4 — Amphibian Expansion, beginning with Frogs.**

Follow the approved Care Keeper roadmap, controlling October 1 plan, ADR-0039, ADR-0045, and relevant X4 acceptance requirements.

You are the coding AI. Implement the functionality, test it, prepare a pull request, and provide screenshots for owner design review.

Do not replace this assignment with another architecture investigation.

## 1. What the user should experience

Care Keeper currently supports Snakes, Spiders, Lizards, and Scorpions.

Add **Amphibians**, initially focused on Frogs.

A user should be able to:

- Select Amphibian when adding an animal.
- Enter its name and species.
- Add a photograph.
- Assign and change its enclosure.
- Record what it ate and whether it ate successfully.
- Record weight and length.
- Add notes and observations.
- Review its care history.
- Configure appropriate reminders.
- Record expenses and use shared Inventory.
- View relevant feeding and measurement trends.
- Find its linked species in the directory.

The experience must feel like a natural part of Care Keeper, not a separate application.

Use the owner-approved second design concept and current dark, photo-first visual style.

Provide a distinct, attractive Amphibian fallback illustration. Do not reuse the Snake, Lizard, Spider, or Scorpion artwork.

Correct the previously deferred unknown-profile visual fallback mismatch as part of enabling the new animal group.

## 2. Implement the exact amphibian.v1 profile

The frozen X4 capability matrix is:

**Capabilities:**

`feeding`, `weight`, `length`, `enclosure_assignment`, `photos`, `notes`, `inventory`, `expenses`, `reminders`, `timeline`

**Care actions:**

`feeding`, `weight`, `length`

**Reminder kinds:**

`feeding`, `weight`, `length`, `cleaning`, `water_change`

**Analytics:**

`feeding`, `weight`, `length`

Do not silently add additional capabilities.

Explicitly exclude Snake shedding, Spider molting/premolt, bath/soak, and misting from amphibian.v1.

Existing care workflows must continue respecting the animal's registered profile.

Feeding and measurement records describe what the keeper actually observed. Do not infer diets, feeding schedules, growth targets, or husbandry requirements.

Cleaning and water-change reminders relate to the appropriate enclosure records, not automatic assumptions about aquatic life stages.

## 3. Preserve biological identity

Use the taxonomy foundation from X2.

Biological species and Care Keeper capability profiles are separate concepts.

Qualified Amphibia taxonomy mapping should use provider identities and ancestry, not a hard-coded list of Frog names or guesses based on common names.

The new profile must not automatically enable specialized Salamander, Newt, Caecilian, or aquatic-stage workflows that haven't been qualified.

Support an appropriate manual-entry path without requiring a successful live provider lookup.

Do not require the full production taxonomy archive to be imported for the isolated development tests.

## 4. Event history and backward compatibility

This is a mandatory data-preservation requirement.

Implement:

- `animal.registered` schema v3 with explicit `capability_profile` identity.
- `animal.taxon_linked` schema v2 with the qualified expanded group validation.
- `amphibian.v1` trusted profile registration, eligibility, and default selection.

Maintain all historical registration v1/v2 and taxon-link v1 decoding.

Never rewrite existing registration events.

Existing Snakes, Spiders, Lizards, and Scorpions must retain their exact historical profiles and behavior.

Preserve completed registration retries and idempotency behavior.

Qualify the actual previously released application binary rejecting new v3 registrations before normal mutable startup. Do not merely mock that check.

Once newer incompatible events exist, do not attempt an unsafe binary downgrade or delete events to make the older binary start.

Keep database migrations minimal and additive if needed.

## 5. Preserve shared workflows

Amphibians should reuse the existing working systems whenever appropriate:

- Animal profiles and household permissions.
- Photos and immutable attachments.
- Feeding and Inventory consumption.
- Weight and length history.
- Enclosure assignment and care.
- Expense tracking.
- Reminders and Calendar.
- Today and Quick Log.
- Search, timeline, reports, and analytics.
- Correction/void behavior.
- Backup and restoration.

Test mixed households containing all five supported groups.

Do not break existing animals merely to make Amphibians work.

## 6. Boundaries

Initial Frog tracking does not include:

- Tadpole development.
- Metamorphosis tracking.
- Automated water chemistry monitoring.
- Species-specific husbandry schedules.
- New captive-care guides.
- Automatic feeding or environmental recommendations.
- Dogs, Cats, Fish, Birds, or colony workflows.

Those belong to later independently qualified modules.

X5 will introduce researched Amphibian Care Guides.

Keep the general animal capability architecture extensible without turning X4 into a universal-animal rewrite.

## 7. Visual acceptance

Provide actual browser screenshots showing:

1. Add Animal with Amphibian available.
2. A newly registered Frog's profile.
3. A Frog's feeding and measurement history.
4. Its care/reminder experience.
5. Its linked species-reference page.
6. Mixed animal groups in the Animals list.

Capture mobile at 390px and 320px and desktop at 1440px.

Confirm that photographs, labels, cards, navigation and care actions match Care Keeper's established UX.

No horizontal overflow, broken images, inaccessible controls, irrelevant actions, or misleading care advice.

## 8. Qualification

Complete `AT-AMPH-01`, applicable `AT-PRODCOMP-01`, historical compatibility, and X1 capability-registry regressions.

Verify actual old-binary rejection of registration v3, immutable event preservation, registry enforcement, household separation, reference-only taxonomy handling, and backup/restore on disposable databases.

Run focused tests first, then the unchanged project quality gate and hosted checks.

Do not relax assertions, lower coverage, or create unnecessary infrastructure gates.

Preserve all owner-approved architecture documents and follow existing content-bound approval requirements if a protected-document amendment genuinely becomes necessary.

## 9. Deliverable

Create a focused X4 branch and pull request against current main.

After qualifying the implementation:

- Commit and push normally.
- Verify hosted Quality, Container, and security results.
- Address substantive Codex review findings.
- Provide the exact PR head and qualification results.
- Include real mobile and desktop screenshots.
- Summarize what the new feature does in ordinary language.
- Prepare a draft What's New entry, marked as development-only until a confirmed production deployment.

## ABSOLUTE BOUNDARIES

Care Keeper is used by real people.

No production database wipe, reset, replacement, reseeding, or data loss.

No production migration, container restart, deployment, or taxonomy import.

No reopening the abandoned kernel-supervisor security project.

Do not start X5.

Do not merge X4 without explicit owner approval.

**Build usable Frog tracking, demonstrate that the X1 foundation works, and return for owner design review.**