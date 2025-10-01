from __future__ import annotations

class MovementUsageComponent:
    """Track per-turn movement expenditure for an entity."""

    def __init__(self, distance: int = 0) -> None:
        self.distance = int(distance)

    def reset(self) -> None:
        """Reset accumulated movement distance."""

        self.distance = 0

    def add(self, amount: int) -> None:
        """Increment tracked distance by ``amount``."""

        self.distance += int(amount)


__all__ = ["MovementUsageComponent"]
