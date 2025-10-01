"""Team affiliation component for ECS entities."""
from __future__ import annotations

from typing import Optional


class TeamComponent:
    """Stores the logical team identifier for an entity."""

    __slots__ = ("team_id",)

    def __init__(self, team_id: Optional[str] = None) -> None:
        self.team_id: Optional[str] = None if team_id is None else str(team_id)

    def set_team(self, team_id: Optional[str]) -> None:
        """Update the stored team identifier."""

        self.team_id = None if team_id is None else str(team_id)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"TeamComponent(team_id={self.team_id!r})"
