"""
Facing System - Updates entity facing direction based on their actions.

This system listens to action events and updates the facing component
of entities based on the targets of their actions.

Rules:
  * If an entity has a FacingComponent with mode=="Fixed" (case-insensitive),
    automatic facing updates are skipped entirely.
  * Otherwise (default "Auto"), the entity turns to face the last target
    position / entity referenced by its most recent action (requested or performed).
"""

from typing import Optional, Tuple
from ..components.facing import FacingComponent  # changed to relative import
from ..components.position import PositionComponent  # changed to relative import
from interface.event_constants import CoreEvents


class FacingSystem:
    """
    System that manages entity facing directions based on their actions.

    This system listens to action events and updates facing components
    to ensure entities face towards their action targets, unless the
    component is set to Fixed mode.
    """

    def __init__(self, game_state, event_bus):
        """
        Initialize the facing system.

        Args:
            game_state: The game state instance
            event_bus: The event bus for listening to action events
        """
        self.game_state = game_state
        self.event_bus = event_bus

        # Subscribe to action events
        if event_bus:
            event_bus.subscribe(CoreEvents.ACTION_REQUESTED, self._on_action_requested)
            event_bus.subscribe(CoreEvents.ACTION_PERFORMED, self._on_action_performed)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    def _on_action_requested(self, entity_id: str, action_name: str, **params):
        """Handle action requested events to update facing direction."""
        self._update_facing_for_action(entity_id, action_name, **params)

    def _on_action_performed(self, entity_id: str, action_name: str, **params):
        """Handle action performed events to update facing direction."""
        self._update_facing_for_action(entity_id, action_name, **params)

    # ------------------------------------------------------------------
    # Core Logic
    # ------------------------------------------------------------------
    def _update_facing_for_action(self, entity_id: str, action_name: str, **params):
        """
        Update entity facing based on action parameters.

        Args:
            entity_id: ID of the entity performing the action
            action_name: Name of the action being performed
            **params: Action parameters that may contain target information
        """
        entity = self.game_state.get_entity(entity_id)
        if not entity:
            return

        facing_comp: Optional[FacingComponent] = entity.get("facing")  # type: ignore
        position_comp: Optional[PositionComponent] = entity.get("position")  # type: ignore

        # Skip if we cannot operate, or facing is explicitly fixed
        if not facing_comp or not position_comp or facing_comp.is_fixed():
            return

        entity_pos = (position_comp.x, position_comp.y)
        target_pos = None

        # Extract target position from different action types
        if "target_tile" in params:
            # Movement actions
            target_pos = params["target_tile"]
        elif "target_id" in params:
            # Attack actions with entity targets
            target_entity = self.game_state.get_entity(params["target_id"]) if params.get("target_id") else None
            if target_entity and "position" in target_entity:
                target_pos_comp = target_entity["position"]
                target_pos = (target_pos_comp.x, target_pos_comp.y)
        elif "target_position" in params:
            # Direct position targets
            target_pos = params["target_position"]

        # Update facing direction if we have a target cell different from current
        if target_pos and target_pos != entity_pos:
            facing_comp.face_towards_position(entity_pos, target_pos)

            # Mirror into character orientation for legacy consumers
            char_ref = entity.get("character_ref")
            if char_ref and hasattr(char_ref, "character"):
                orientation = facing_comp.get_character_orientation()
                # Guard against characters lacking setter
                if hasattr(char_ref.character, "set_orientation"):
                    char_ref.character.set_orientation(orientation)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_entity_facing_direction(self, entity_id: str) -> Tuple[float, float]:
        """
        Get the facing direction for an entity.

        Args:
            entity_id: ID of the entity

        Returns:
            Tuple of (dx, dy) representing the facing direction vector
        """
        entity = self.game_state.get_entity(entity_id)
        if not entity:
            return (0.0, 1.0)

        facing_comp: Optional[FacingComponent] = entity.get("facing")  # type: ignore
        if facing_comp:
            return facing_comp.direction

        # Fallback to character orientation if facing component doesn't exist
        char_ref = entity.get("character_ref")
        if char_ref and hasattr(char_ref, "character"):
            orientation = getattr(char_ref.character, 'orientation', 'up')
            orientation_map = {
                'up': (0.0, 1.0),
                'down': (0.0, -1.0),
                'left': (-1.0, 0.0),
                'right': (1.0, 0.0)
            }
            return orientation_map.get(orientation, (0.0, 1.0))

        return (0.0, 1.0)  # Default facing up

    def set_entity_facing_direction(self, entity_id: str, direction: Tuple[float, float]):
        """
        Manually set the facing direction for an entity (even if Fixed mode is active).

        Args:
            entity_id: ID of the entity
            direction: Tuple of (dx, dy) representing the facing direction vector
        """
        entity = self.game_state.get_entity(entity_id)
        if not entity:
            return

        facing_comp: Optional[FacingComponent] = entity.get("facing")  # type: ignore
        if facing_comp:
            facing_comp.set_facing_direction(direction[0], direction[1])

            # Mirror into character orientation for legacy consumers
            char_ref = entity.get("character_ref")
            if char_ref and hasattr(char_ref, "character"):
                orientation = facing_comp.get_character_orientation()
                if hasattr(char_ref.character, "set_orientation"):
                    char_ref.character.set_orientation(orientation)
