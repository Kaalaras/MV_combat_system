"""Condition tracking component for ECS entities."""
from typing import Dict, Set, Any


class ConditionTrackerComponent:
    """Stores active conditions and runtime metadata for an entity."""

    def __init__(self) -> None:
        # Mapping of condition name -> Condition instance (defined in condition_system)
        self.conditions: Dict[str, Any] = {}
        # Dynamic-only states (e.g., thresholds) managed outside the timed tracker.
        self.dynamic_states: Set[str] = set()

    def active_states(self) -> Set[str]:
        """Return the union of timed and dynamic states tracked for the entity."""
        return set(self.conditions.keys()) | set(self.dynamic_states)


__all__ = ["ConditionTrackerComponent"]
