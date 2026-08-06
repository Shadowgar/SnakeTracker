"""Registry-driven append-only correction policy."""

from __future__ import annotations

from enum import StrEnum

from snaketracker.platform.events.control_contracts import EventReinstatedV1, EventVoidedV1
from snaketracker.platform.events.envelope import DomainEvent
from snaketracker.platform.events.registry import CorrectionCapabilities


class CorrectionAction(StrEnum):
    CORRECT = "correct"
    VOID = "void"
    REINSTATE = "reinstate"


class CorrectionPolicyError(ValueError):
    """A requested historical control is forbidden or structurally invalid."""


def validate_correction(
    action: CorrectionAction,
    target: DomainEvent,
    control: DomainEvent,
    capabilities: CorrectionCapabilities,
    actor_role: str,
    prior_controls: tuple[DomainEvent, ...],
    *,
    compensations: tuple[DomainEvent, ...] = (),
) -> None:
    """Validate control policy without mutating stored history."""
    if actor_role != capabilities.required_role:
        raise CorrectionPolicyError("Actor role does not permit this correction action.")
    allowed = {
        CorrectionAction.CORRECT: capabilities.correctable,
        CorrectionAction.VOID: capabilities.voidable,
        CorrectionAction.REINSTATE: capabilities.reinstatable,
    }
    if not allowed[action]:
        raise CorrectionPolicyError("Target event contract does not permit this action.")
    if target.household_id != control.household_id or (
        target.stream_type,
        target.stream_id,
    ) != (control.stream_type, control.stream_id):
        raise CorrectionPolicyError(
            "Correction target must belong to the same stream and household."
        )
    if (
        capabilities.maximum_age_days is not None
        and (control.recorded_at - target.recorded_at).days > capabilities.maximum_age_days
    ):
        raise CorrectionPolicyError("Correction exceeds the target contract age policy.")
    payload_target = getattr(control.payload, "target_event_id", None)
    if payload_target != target.event_id:
        raise CorrectionPolicyError("Correction payload does not identify its target event.")
    if control.correlation_id != target.correlation_id:
        raise CorrectionPolicyError("Correction must retain the original correlation lineage.")

    active_void = _active_void(target.event_id, prior_controls)
    if action is CorrectionAction.CORRECT:
        if control.event_type not in capabilities.correction_event_types:
            raise CorrectionPolicyError("Correction contract is not permitted for the target.")
        if control.causation_id != target.event_id:
            raise CorrectionPolicyError("Correction causation must identify the target event.")
    elif action is CorrectionAction.VOID:
        if not isinstance(control.payload, EventVoidedV1):
            raise CorrectionPolicyError("Void action requires the event.voided contract.")
        if active_void is not None:
            raise CorrectionPolicyError("Target event is already voided.")
        if control.causation_id != target.event_id:
            raise CorrectionPolicyError("Void causation must identify the target event.")
    else:
        if not isinstance(control.payload, EventReinstatedV1):
            raise CorrectionPolicyError("Reinstatement requires the event.reinstated contract.")
        if active_void is None:
            raise CorrectionPolicyError("Target event has no active void to reinstate.")
        if control.causation_id != active_void.event_id:
            raise CorrectionPolicyError("Reinstatement causation must identify the active void.")

    if action in (CorrectionAction.CORRECT, CorrectionAction.VOID) and (
        capabilities.requires_compensation
    ):
        if not compensations:
            raise CorrectionPolicyError("Target contract requires an explicit compensation event.")
        for compensation in compensations:
            if compensation.household_id != target.household_id:
                raise CorrectionPolicyError("Compensation must remain in the target household.")
            if compensation.correlation_id != target.correlation_id:
                raise CorrectionPolicyError("Compensation must retain correlation lineage.")
            if compensation.causation_id != control.event_id:
                raise CorrectionPolicyError(
                    "Compensation causation must identify the control event."
                )


def evaluate_effective_events(events: tuple[DomainEvent, ...]) -> tuple[DomainEvent, ...]:
    """Small deterministic reducer used to prove correction-chain semantics."""
    base: list[DomainEvent] = []
    replacements: dict[object, DomainEvent] = {}
    voided: set[object] = set()
    for event in events:
        payload = event.payload
        target_id = getattr(payload, "target_event_id", None)
        if isinstance(payload, EventVoidedV1):
            voided.add(payload.target_event_id)
        elif isinstance(payload, EventReinstatedV1):
            voided.discard(payload.target_event_id)
        elif target_id is not None:
            replacements[target_id] = event
        else:
            base.append(event)
    return tuple(
        replacements.get(event.event_id, event) for event in base if event.event_id not in voided
    )


def _active_void(target_event_id: object, controls: tuple[DomainEvent, ...]) -> DomainEvent | None:
    active: DomainEvent | None = None
    for event in controls:
        if (
            isinstance(event.payload, EventVoidedV1)
            and event.payload.target_event_id == target_event_id
        ):
            active = event
        elif (
            isinstance(event.payload, EventReinstatedV1)
            and event.payload.target_event_id == target_event_id
        ):
            active = None
    return active
