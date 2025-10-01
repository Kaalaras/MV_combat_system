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
