"""Application-owned product projection status models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProjectionFreshness:
    group_name: str
    checkpoint_global_position: int
    latest_global_position: int
    checkpoint_updated_at: datetime
    lag_events: int
    is_stale: bool


@dataclass(frozen=True, slots=True)
class ProjectionAdvanceResult:
    processed_outbox_items: int
    final_global_position: int
