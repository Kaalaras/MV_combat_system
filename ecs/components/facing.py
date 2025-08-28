"""
Facing Component - Tracks the direction an entity is facing.

This component stores the facing direction of entities, which is updated based on
their actions (movement, attacks, etc.) and used for visual representation.
"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class FacingComponent:
    """
    Component that tracks which direction an entity is facing.

    Attributes:
        direction: Current facing direction as normalized vector (dx, dy)
        last_target_position: Last position the entity targeted with an action
        default_direction: Default facing direction when no actions have been taken
        mode: Behaviour mode. "Auto" (default) automatically updates facing after actions.
              "Fixed" prevents automatic updates (manual control only).
    """
    direction: Tuple[float, float] = (0.0, 1.0)  # Default facing up (North)
    last_target_position: Optional[Tuple[int, int]] = None
    default_direction: Tuple[float, float] = (0.0, 1.0)  # North by default
    mode: str = "Auto"  # or "Fixed"

    def is_fixed(self) -> bool:
        """Return True if automatic facing updates should be skipped."""
        return self.mode.lower() == "fixed"

    def set_facing_direction(self, dx: float, dy: float) -> None:
        """
        Set the facing direction as a normalized vector.

        Args:
            dx: X component of direction vector
            dy: Y component of direction vector
        """
        # Normalize the direction vector
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            self.direction = (dx / length, dy / length)
        else:
            self.direction = self.default_direction

    def face_towards_position(self, entity_pos: Tuple[int, int], target_pos: Tuple[int, int]) -> None:
        """
        Update facing direction to face towards a target position.

        Args:
            entity_pos: Current position of the entity (x, y)
            target_pos: Target position to face towards (x, y)
        """
        self.last_target_position = target_pos

        # Calculate direction vector
        dx = target_pos[0] - entity_pos[0]
        dy = target_pos[1] - entity_pos[1]

        # If same position, don't change facing
        if dx == 0 and dy == 0:
            return

        self.set_facing_direction(float(dx), float(dy))

    def get_cardinal_direction(self) -> str:
        """
        Get the facing direction as a cardinal direction string.

        Returns:
            One of: 'north', 'south', 'east', 'west', 'northeast', 'northwest', 'southeast', 'southwest'
        """
        dx, dy = self.direction

        # Determine primary directions
        if abs(dx) > abs(dy):
            # More horizontal than vertical
            if dx > 0:
                return 'east' if abs(dy) < 0.5 else ('northeast' if dy > 0 else 'southeast')
            else:
                return 'west' if abs(dy) < 0.5 else ('northwest' if dy > 0 else 'southwest')
        else:
            # More vertical than horizontal
            if dy > 0:
                return 'north' if abs(dx) < 0.5 else ('northeast' if dx > 0 else 'northwest')
            else:
                return 'south' if abs(dx) < 0.5 else ('southeast' if dx > 0 else 'southwest')

    def get_character_orientation(self) -> str:
        """
        Get the facing direction compatible with the character orientation system.

        Returns:
            One of: 'up', 'down', 'left', 'right'
        """
        dx, dy = self.direction

        # Determine primary direction based on largest component
        if abs(dx) > abs(dy):
            return 'right' if dx > 0 else 'left'
        else:
            return 'up' if dy > 0 else 'down'
