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

Names are stable semantic identifiers; initial schemas begin at version 1.

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
| `animal.registered` | Creates animal identity and initial profile |
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
| `animal.handling_recorded` | Records handling session |
| `animal.behavior_recorded` | Records a behavior observation |
| `animal.bath_recorded` | Records a bath |

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
| `enclosure.status_changed` | Activates, retires, or quarantines enclosure |

### Inventory

| Event type | Meaning |
|---|---|
| `inventory.item_registered` | Creates item and unit definition |
| `inventory.stock_received` | Adds stock |
| `inventory.stock_reserved` | Reserves stock |
| `inventory.stock_consumed` | Consumes stock |
| `inventory.consumption_reversed` | Compensates a prior consumption |
| `inventory.stock_adjusted` | Authorized reconciliation |
| `inventory.stock_expired` | Removes expired stock |
| `inventory.reorder_policy_changed` | Changes threshold policy |

### Expenses, reminders, and documents

| Event type | Meaning |
|---|---|
| `expense.recorded` | Creates expense |
| `expense.corrected` | Replaces effective financial facts |
| `expense.voided` | Voids expense |
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
