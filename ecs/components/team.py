"""Team affiliation component for ECS entities."""
from __future__ import annotations

from typing import Optional


class TeamComponent:
    """Stores the logical team identifier for an entity."""

    __slots__ = ("team_id",)

    def __init__(self, team_id: Optional[str] = None) -> None:
        self.team_id: Optional[str] = self._normalize_team_id(team_id)

    def set_team(self, team_id: Optional[str]) -> None:
        """Update the stored team identifier."""

        self.team_id = self._normalize_team_id(team_id)

    @staticmethod
    def _normalize_team_id(team_id: Optional[str]) -> Optional[str]:
        if team_id is None:
            return None
        if not isinstance(team_id, str):
            raise TypeError(
                f"team_id must be a string or None, got {type(team_id).__name__}"
            )
        return team_id

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"TeamComponent(team_id={self.team_id!r})"
