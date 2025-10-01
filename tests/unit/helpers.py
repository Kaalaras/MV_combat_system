"""Shared testing helpers for condition-related assertions."""
from typing import Optional

from ecs.components.condition_tracker import ConditionTrackerComponent


def find_condition_by_prefix_and_delta(
    tracker: Optional[ConditionTrackerComponent],
    prefix: str,
    delta: int,
) -> Optional[str]:
    """Locate a condition matching the given prefix and delta.

    Args:
        tracker: The condition tracker component to search.
        prefix: The expected condition name prefix (e.g., "DamageOutMod").
        delta: The numeric delta stored in the condition's data.

    Returns:
        The condition name if found, otherwise ``None``.
    """
    if tracker is None:
        return None
    for name, condition in tracker.conditions.items():
        if name.startswith(prefix) and condition.data.get('delta') == delta:
            return name
    return None


def assert_tracker_has_condition(
    testcase,
    condition_system,
    entity_id: str,
    prefix: str,
    delta: int,
    tracker_message: Optional[str] = None,
    missing_message: Optional[str] = None,
) -> str:
    """Assert that an entity tracker exists and contains a matching condition.

    Args:
        testcase: The calling ``unittest.TestCase`` instance.
        condition_system: The ``ConditionSystem`` under test.
        entity_id: The entity identifier whose tracker should be inspected.
        prefix: The condition name prefix to match.
        delta: The expected numeric delta stored with the condition.
        tracker_message: Optional custom message when the tracker is missing.
        missing_message: Optional custom message when the condition is absent.

    Returns:
        The fully qualified condition name.
    """

    tracker = condition_system.get_tracker(entity_id)
    testcase.assertIsNotNone(
        tracker,
        tracker_message
        or f"Condition tracker missing for entity '{entity_id}'",
    )
    condition_name = find_condition_by_prefix_and_delta(tracker, prefix, delta)
    testcase.assertIsNotNone(
        condition_name,
        missing_message
        or f"No {prefix} condition with delta {delta} found for entity '{entity_id}'",
    )
    return condition_name
