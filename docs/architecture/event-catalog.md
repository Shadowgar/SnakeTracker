# Event Contract Catalog

## Envelope contract

Every event record contains:

- Unique `event_id` UUID
- Monotonic `global_position` within one database
- `household_id`
- `stream_type`, `stream_id`, and contiguous `stream_version`
- `event_type` and positive `schema_version` forming the event contract identity
- UTC microsecond `occurred_at` and server-assigned `recorded_at`
- `actor_user_id`
- `correlation_id`, optional `causation_id`, and command idempotency key
- Required typed subject references
- Human-readable title and optional description
- Strongly typed payload
- Size-limited technical metadata only
- Notes, normalized tags, and finalized immutable attachment-version references
- Ordinary canonical-data checksum for corruption detection

Checksums do not provide tamper evidence. HMAC or hash chains require a future ADR and independent key-management design.

## Registry requirements

Each registration keyed by `event_type + schema_version` declares payload schema, owner, deserializer, upcasters, aggregate application handler, projection handlers, authorization policy, subject rules, timeline/export renderers, and these correction capabilities:

- `correctable`
- `voidable`
- `reinstatable`
- `requires_compensation`
- Required role per action
- Correction-age policy
- Permitted correction contract
- Apply, reverse, and reinstate behavior

Unknown contracts stop replay and normal startup safely. Upcasters live beside the owning event contracts and are tested against permanent historical replay fixtures.

## Initial contract families

Names are stable semantic identifiers; initial schemas begin at version 1. A later schema version is
a distinct event contract identity and never rewrites an event stored under an earlier version.

### Household

| Event type | Meaning | Typical correction policy |
|---|---|---|
| `household.created` | Creates household identity and settings | Not voidable after use |
| `household.owner_added` | Establishes an owner | Compensating role transition required |
| `household.member_invited` | Creates a business invitation intent | Revocable |
| `household.member_joined` | Activates membership | Compensating removal/suspension |
| `household.member_role_changed` | Changes capability set | Reversible through new role event |
| `household.member_suspended` | Removes active access | Reinstatable |
| `household.settings_changed` | Changes household settings/timezone | Correctable by later change |

### Animal profile and lifecycle

| Event type | Meaning |
|---|---|
| `animal.registered` v1 | Creates legacy snake identity and initial profile; replay deterministically selects `snake.v1` |
| `animal.registered` v2 | Creates common animal identity and records a registered animal type/capability profile |
| `animal.profile_corrected` | Corrects name, species, morph, genetics, sex, dates, breeder, microchip, temperament, or notes |
| `animal.status_changed` | Changes active, quarantine, deceased, rehomed, or archived status |
| `animal.enclosure_assigned` | Changes animal-owned current enclosure assignment |
| `animal.photo_selected` | Selects finalized attachment version as profile photo |

### Husbandry feature slice

| Event type | Meaning |
|---|---|
| `animal.feeding_recorded` | Records food offered, quantity, outcome, and occurred time |
| `animal.feeding_corrected` | Replaces effective feeding facts |
| `animal.weight_recorded` | Records normalized and entered weight |
| `animal.weight_corrected` | Corrects a measurement |
| `animal.length_recorded` | Records normalized and entered length |
| `animal.length_corrected` | Corrects a measurement |
| `animal.shed_recorded` | Records shed occurrence and quality |
| `animal.shed_corrected` | Replaces effective shed facts for a same-stream target event |
| `animal.handling_recorded` | Records handling session |
| `animal.behavior_recorded` | Records a behavior observation |
| `animal.bath_recorded` | Records a bath |
| `animal.molt_recorded` v1 | Historical Spider-only molt occurrence, result, and keeper observations; never reinterpreted or upcast |
| `animal.molt_recorded` v2 | Records a capability-neutral molt occurrence and result for a molt-capable Animal |
| `animal.molt_corrected` v1 | Historical Spider-only replacement for effective molt facts; never reinterpreted or upcast |
| `animal.molt_corrected` v2 | Replaces capability-neutral effective molt facts for a same-stream target event |
| `animal.premolt_observed` v1 | Historical Spider-only premolt state; never reinterpreted or upcast |
| `animal.premolt_observed` v2 | Records or clears a capability-neutral premolt state with keeper observation |

Length, shed, and bath contracts require the corresponding declared capability; shed remains
snake-specific in v1, while length and bath are also valid for `lizard.v1`. Molt and premolt v2
require a molt-capable profile and are shared by `spider.v1` and `scorpion.v1`. Feeding and weight
remain shared where the active profile permits them.

### Health feature slice

| Event type | Meaning |
|---|---|
| `animal.health_observation_recorded` | Records structured observation and notes |
| `animal.medication_started` | Starts medication plan |
| `animal.medication_administered` | Records one administration |
| `animal.medication_stopped` | Ends plan |
| `animal.vet_visit_recorded` | Records visit, findings, and follow-up |
| `animal.health_event_corrected` | Contract-specific correction |

### Enclosures

| Event type | Meaning |
|---|---|
| `enclosure.registered` | Creates enclosure |
| `enclosure.profile_changed` | Changes name/type/capacity policy |
| `enclosure.cleaning_recorded` | Records cleaning |
| `enclosure.water_change_recorded` | Records water change |
| `enclosure.misting_recorded` | Records configured watering/misting care with an optional typed animal subject |
| `enclosure.status_changed` | Activates, retires, or quarantines enclosure |

### Inventory

| Event type | Meaning |
|---|---|
| `inventory.item_registered` | Creates item and unit definition |
| `inventory.item_updated` | Changes the item name, unit, or reorder threshold without rewriting stock history |
| `inventory.item_archived` | Removes an item from active use while preserving its stream and references |
| `inventory.item_restored` | Returns an archived item to active use |
| `inventory.stock_received` | Adds stock |
| `inventory.stock_reserved` | Reserves stock |
| `inventory.stock_consumed` | Consumes stock |
| `inventory.consumption_reversed` | Compensates a prior consumption |
| `inventory.stock_adjusted` | Authorized reconciliation |
| `inventory.stock_expired` | Removes expired stock |
| `inventory.reorder_policy_changed` | Changes threshold policy |

#### Proposed M6.5 contracts (not registered)

The following contract versions/types are proposed by ADR-0042. Version-1 Inventory history remains
registered unchanged.

| Event contract | Meaning |
|---|---|
| `inventory.item_registered` v2 | Adds owner category while retaining one canonical item unit |
| `inventory.item_updated` v2 | Changes name/category and permits unit change only before movement |
| `inventory.stock_received` v2 | Adds scaled quantity with an optional typed Purchase-line source |
| `inventory.receipt_corrected` v1 | Replaces effective quantity of a targeted v2 receipt without relinking its source |
| `inventory.stock_consumed` v2 | Removes scaled quantity for typed generic or linked inventory use |
| `inventory.stock_adjusted` v2 | Applies a scaled nonzero manual delta with structured reason/context |
| `inventory.stock_counted` v1 | Records expected, actual, variance, actor/time, and count-workflow context |
| `inventory.reorder_policy_changed` v2 | Sets minimum, target, maximum, and owner lead time |
| `inventory.verification_policy_changed` v1 | Sets or clears the owner recount interval |

`event.voided`, `event.reinstated`, and `inventory.consumption_reversed` are reused where their
target registration permits them. A physical count applies its own variance and does not generate a
duplicate adjustment event.

### Expenses, reminders, and documents

| Event type | Meaning |
|---|---|
| `expense.recorded` | Creates expense |
| `expense.corrected` | Replaces effective financial facts |
| `expense.voided` | Voids expense |
| `purchase.recorded` v1 *(Proposed M6.5)* | Records one specialized cash-spend receipt with bounded inventory lines |
| `purchase.corrected` v1 *(Proposed M6.5)* | Replaces effective Purchase facts and coordinates receipt corrections |
| `reminder.rule_created` | Creates rule |
| `reminder.rule_changed` | Changes schedule or channels |
| `reminder.rule_disabled` | Disables rule |
| `document.registered` | Associates finalized attachment version |
| `document.replaced` | Associates a new immutable version |
| `document.archived` | Archives logical document |

### Generic historical-control contracts

`event.voided` and `event.reinstated` may be used only when the target registration permits them. Domain-specific compensating events are additionally required when another stream or material business effect must be reversed.

## Correction rules

Corrections and voids append to the target stream and reference `target_event_id`. Projections expose effective state while retaining the entire chain. An event cannot be voided twice. Reinstatement is explicit. Cross-stream effects use the original correlation ID lineage and a new causation relationship. Privacy erasure uses a separately authorized redaction procedure and retains a non-sensitive structural tombstone.

## Stream-growth gates

Architecture review is mandatory when a stream exceeds 10,000 events, replay p95 exceeds 100 ms despite snapshots, snapshot state exceeds 1 MiB, a command regularly touches over five streams, unexpected SQLite busy failures exceed 0.1%, or one family dominates database growth. Sensor telemetry always requires a separate ingestion ADR.
