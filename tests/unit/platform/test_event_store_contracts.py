from __future__ import annotations

from snaketracker.platform.events import store as store_module


def test_canonical_command_hash_is_stable_across_mapping_order() -> None:
    first = {"quantity": 2, "subject": {"id": "abc", "type": "test"}}
    second = {"subject": {"type": "test", "id": "abc"}, "quantity": 2}

    assert store_module.canonical_command_hash(first) == store_module.canonical_command_hash(second)
    assert store_module.canonical_command_hash(first) != store_module.canonical_command_hash(
        {"quantity": 3, "subject": {"id": "abc", "type": "test"}}
    )
