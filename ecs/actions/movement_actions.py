# ecs/actions/movement_actions.py
"""
Movement action system module that handles different movement options for entities.

This module implements various movement actions that characters can take during gameplay,
including standard movement and sprinting. Each movement type is implemented as a separate
Action subclass with appropriate parameters and execution logic.

Movement actions interact with the game's movement system to validate and execute
positional changes on the game grid.
"""

from ecs.systems.action_system import Action, ActionType
from core.player_input import choose_direction  # choose_tile removed as target_tile comes from params
from typing import Tuple, Optional, Any, Dict, List, Union


class StandardMoveAction(Action):
    """
    Represents a standard movement action for an entity.

    This action allows the entity to move up to 7 spaces and choose a facing direction.
    It is a limited free action and can only be performed once per turn.

    Attributes:
        movement_system: The movement system responsible for handling entity movement.

    Example:
        ```python
        # Create a standard move action with the game's movement system
        move_action = StandardMoveAction(game_state.movement)

        # Register with action system
        action_system.register_action(move_action)

        # Execute through action system
        success = action_system.execute_action(
            "player1",
            "Standard Move",
            target_tile=(5, 3),
            new_direction="right"
        )
        ```
    """

    def __init__(self, movement_system: Any):
        """
        Initialize a standard move action.

        Args:
            movement_system: The movement system used to handle entity movement.
        """
        super().__init__(
            name="Standard Move",
            action_type=ActionType.LIMITED_FREE,
            execute_func=self._execute,
            is_available_func=self._is_available,  # Added for consistency
            description="Move up to 7 spaces and choose facing direction",
            keywords=["move"],
            incompatible_keywords=["move"],
            per_turn_limit=1
        )
        self.movement_system = movement_system

    def _is_available(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Check if the standard move action is available for the given entity.

        Args:
            entity_id: The ID of the entity attempting to move.
            game_state: The current game state.
            **action_params: Additional parameters including target_tile.

        Returns:
            bool: True if the move action can be performed, False otherwise.

        Note:
            Currently only checks if target_tile is provided. A more robust
            implementation would check if the tile is reachable based on
            entity position and movement range.
        """
        # Availability can be checked here, e.g., if entity can move.
        # For now, assume ActionSystem's general checks are sufficient or it's always available if not otherwise restricted.
        # A more robust check might verify if a target_tile is provided in action_params.
        if not action_params.get("target_tile"):
            # print(f"StandardMoveAction: target_tile not provided for {entity_id}")
            return False  # Or handle differently if interactive fallback is desired
        return True

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Execute the standard move action for the given entity.

        Moves the entity to the target_tile specified in action_params.
        Allows the user/AI to choose a new facing direction if not specified in action_params.

        Args:
            entity_id: The ID of the entity performing the move.
            game_state: The current game state.
            **action_params: Must contain 'target_tile'. Can optionally contain 'new_direction'.

        Returns:
            bool: True if the move was successful, False otherwise.

        Example:
            ```python
            # Execute directly through the action
            move_action._execute(
                "player1",
                game_state,
                target_tile=(5, 3),
                new_direction="up"
            )
            ```
        """
        target_tile = action_params.get("target_tile")
        new_direction = action_params.get("new_direction")
        if target_tile is None:
            print(f"[Move] No target_tile provided for Standard Move for {entity_id}.")
            return False
        entity = game_state.get_entity(entity_id)
        used = game_state.get_movement_used(entity_id) if hasattr(game_state, 'get_movement_used') else 0
        allowance = max(0, 7 - used)
        # Apply condition-based movement constraints
        cond_sys = getattr(game_state, 'condition_system', None)
        if cond_sys:
            allowance = cond_sys.apply_movement_constraints(entity_id, allowance, movement_type='standard')
        if allowance <= 0:
            print(f"[Move] Movement allowance reduced to 0 for {entity_id}.")
            return False
        moved = self.movement_system.move(entity_id, target_tile, max_steps=allowance)
        if moved and new_direction:
            entity["character_ref"].character.set_orientation(new_direction)
        return moved


class SprintAction(Action):
    """
    Represents a sprint action for an entity.

    This action allows the entity to run quickly and maintain its facing direction.
    Unlike StandardMoveAction, Sprint is a primary action and uses the character's
    full action for the turn, but potentially allows for greater movement distance
    depending on the movement system implementation.

    Attributes:
        movement_system: The movement system responsible for handling entity movement.

    Example:
        ```python
        # Create a sprint action with the game's movement system
        sprint_action = SprintAction(game_state.movement)

        # Register with action system
        action_system.register_action(sprint_action)

        # Execute through action system
        success = action_system.execute_action(
            "player1",
            "Sprint",
            target_tile=(8, 7)
        )
        ```
    """

    def __init__(self, movement_system: Any):
        """
        Initialize a sprint action.

        Args:
            movement_system: The movement system used to handle entity movement.
        """
        super().__init__(
            name="Sprint",
            action_type=ActionType.PRIMARY,
            execute_func=self._execute,
            is_available_func=self._is_available,  # Added for consistency
            description="Run quickly and maintain facing direction",
            keywords=["move"],
            incompatible_keywords=["move"]
        )
        self.movement_system = movement_system

    def _is_available(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Check if the sprint action is available for the given entity.

        Args:
            entity_id: The ID of the entity attempting to sprint.
            game_state: The current game state.
            **action_params: Additional parameters including target_tile.

        Returns:
            bool: True if the sprint action can be performed, False otherwise.

        Note:
            Currently only checks if target_tile is provided. A more robust
            implementation would check if the tile is reachable based on
            entity position, stamina, and other relevant factors.
        """
        if not action_params.get("target_tile"):
            # print(f"SprintAction: target_tile not provided for {entity_id}")
            return False
        return True

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Execute the sprint action for the given entity.

        Moves the entity to the target_tile specified in action_params.
        The entity maintains its current facing direction.

        Args:
            entity_id: The ID of the entity performing the sprint.
            game_state: The current game state.
            **action_params: Must contain 'target_tile'. Can optionally contain 'entity_id_moving'.

        Returns:
            bool: True if the sprint was successful, False otherwise.

        Example:
            ```python
            # Execute directly through the action
            sprint_action._execute(
                "player1",
                game_state,
                target_tile=(8, 7),
                entity_id_moving="companion1"  # Optional, to move another entity
            )
            ```
        """
        target_tile = action_params.get("target_tile")
        entity_id_moving = action_params.get("entity_id_moving", entity_id)
        if target_tile is None:
            print(f"[Sprint] No target_tile provided for Sprint for {entity_id}.")
            return False
        try:
            tx, ty = target_tile
        except (ValueError, TypeError):
            print(f"[Sprint] Invalid target_tile format: {target_tile}")
            return False
        ent = game_state.get_entity(entity_id_moving)
        if not ent or 'character_ref' not in ent:
            return False
        char = ent['character_ref'].character
        sprint_max = char.calculate_sprint_distance() if hasattr(char, 'calculate_sprint_distance') else 15
        used = game_state.get_movement_used(entity_id_moving) if hasattr(game_state, 'get_movement_used') else 0
        remaining = max(0, sprint_max - used)
        cond_sys = getattr(game_state, 'condition_system', None)
        if cond_sys:
            remaining = cond_sys.apply_movement_constraints(entity_id_moving, remaining, movement_type='sprint')
        if remaining <= 0:
            print(f"[Sprint] Movement allowance reduced to 0 for {entity_id_moving}.")
            return False
        return self.movement_system.move(entity_id_moving, (tx, ty), max_steps=remaining)
