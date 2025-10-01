"""Initiative component definitions."""
from typing import Optional


class InitiativeComponent:
    """Stores initiative tuning data for an entity.

    Attributes:
        bonus: Flat modifier applied on top of the character's base initiative.
        override: When provided, forces initiative to a fixed value (still allowing
            character-based modifiers to apply).
        enabled: When ``False`` the component participates in queries but is
            effectively ignored by the initiative calculation. This allows
            temporarily removing an entity from the turn order without deleting
            the component outright.
    """

    def __init__(self, bonus: int = 0, override: Optional[int] = None, enabled: bool = True):
        self.bonus = bonus
        self.override = override
        self.enabled = enabled

    def resolve(self, base: int, character_modifier: int = 0) -> int:
        """Return the final initiative value derived from stored settings."""

        if not self.enabled:
            return base + character_modifier
        if self.override is not None:
            return self.override + character_modifier
        return base + character_modifier + self.bonus


__all__ = ["InitiativeComponent"]
