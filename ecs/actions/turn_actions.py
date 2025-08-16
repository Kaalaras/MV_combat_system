# ecs/actions/turn_actions.py
"""
Turn management actions module for entity turn control in the game system.

This module provides actions that entities can use to control their turns within the
game's initiative system. It includes actions for ending a turn normally and for
delaying an entity's turn to a later position in the initiative order.

These actions integrate with the action system and turn order system to provide
a complete framework for entity turn management.
"""

from typing import Any
from ecs.systems.action_system import Action, ActionType


class EndTurnAction(Action):
    """
    Represents the action of an entity ending their turn.

    This is a free action that signals the entity has completed their actions
    for the current turn. Since it's a free action, it can be performed at any time
    during the entity's turn without consuming action points or other resources.

    Example:
        ```python
        # Create an end turn action
        end_turn = EndTurnAction()

        # Register with action system
        action_system.register_action(end_turn)

        # Execute through action system
        action_system.execute_action("player1", "End Turn")
        # At this point, the game system would typically advance to the next entity's turn
        ```
    """

    def __init__(self):
        """
        Initialize an end turn action.

        The action is configured as a FREE action type, meaning it doesn't consume
        any of the entity's action allocations for the turn.
        """
        super().__init__(
            name="End Turn",
            action_type=ActionType.FREE,
            execute_func=self._execute,
            description="Ends the current entity's turn, allowing the game to proceed to the next entity.",
            # This action is fundamental and typically doesn't have complex availability logic,
            # keywords, limits (beyond being the 'last' action conceptually), or cooldowns.
        )

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Executes the end turn action.

        This method signals that the entity has finished their turn. The actual turn
        advancement is handled by the game system after this action is processed.

        Args:
            entity_id: The ID of the entity ending their turn.
            game_state: The current state of the game.
            **action_params: Additional parameters for the action (not used by EndTurnAction).

        Returns:
            bool: True, indicating the action was successfully performed.

        Note:
            The GameSystem or equivalent turn management logic is responsible for
            actually advancing to the next turn after this action succeeds.

        Example:
            ```python
            # Execute directly through the action
            success = end_turn._execute("player1", game_state)
            if success:
                game_system.advance_to_next_turn()
            ```
        """
        # This action's primary role is to signal that the entity's turn is complete.
        # The actual advancement of the turn order is handled by the GameSystem
        # after this action is successfully processed by the ActionSystem.
        # Returning True ensures the ActionSystem registers it as performed.
        return True


class DelayAction(Action):
    """
    Represents the action of delaying an entity's turn in the initiative order.

    This action allows an entity to voluntarily move down in the initiative order,
    ending their current turn and taking a later turn in the round. This can be used
    for tactical advantages or to coordinate actions with other entities.

    Attributes:
        turn_order_system: The system responsible for managing initiative and turn order.

    Example:
        ```python
        # Create a delay action with the game's turn order system
        delay_action = DelayAction(game_state.turn_order)

        # Register with action system
        action_system.register_action(delay_action)

        # Execute through action system
        action_system.execute_action("player1", "Delay Action")
        # Player1's initiative is now reduced by 1, and their turn ends
        ```
    """

    def __init__(self, turn_order_system: Any):
        """
        Initialize a delay action.

        Args:
            turn_order_system: The system that manages initiative and turn order.
                               Must implement a delay_current_entity method.
        """
        super().__init__(
            name="Delay Action",
            action_type=ActionType.FREE,
            execute_func=self._execute,
            description="Move your initiative rank down by 1 and end your turn."
        )
        self.turn_order_system = turn_order_system

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Executes the delay action for the current entity.

        This method reduces the entity's initiative position and ends their turn.
        The entity will get another turn later in the initiative order.

        Args:
            entity_id: The ID of the entity delaying their turn.
            game_state: The current state of the game.
            **action_params: Additional parameters for the action (not used by DelayAction).

        Returns:
            bool: True if the action was successfully performed, False otherwise.

        Side effects:
            - Changes the entity's position in the initiative order
            - Ends the entity's current turn

        Example:
            ```python
            # Execute directly through the action
            success = delay_action._execute("player1", game_state)
            if success:
                print("Player 1 has delayed their turn and will act later")
            ```
        """
        self.turn_order_system.delay_current_entity()
        return True