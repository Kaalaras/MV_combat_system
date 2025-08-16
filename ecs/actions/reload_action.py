# ecs/actions/reload_action.py
"""
Reload action system module for weapon reloading functionality.

This module implements the ReloadAction class which integrates with the action system
to allow entities to reload their weapons during gameplay. The action handles validation,
execution, and proper reporting of reload operations.
"""

from ecs.systems.action_system import Action, ActionType
from typing import Any, Optional, Dict, Union


class ReloadAction(Action):
    """
    Represents a reload action for a weapon.

    This action allows an entity to reload a weapon if it is reloadable and not already
    at maximum ammunition. The action type (primary or secondary) is determined by the
    weapon's `reload_action_type` attribute.

    Attributes:
        weapon (Any): The weapon instance to be reloaded.

    Example:
        ```python
        # Create a reload action for a pistol
        pistol = Weapon(name="Pistol", ammunition=2, max_ammunition=6, reloadable=True)
        reload_action = ReloadAction(pistol)

        # Register with action system
        action_system.register_action(reload_action)

        # Execute through action system
        success = action_system.execute_action("player1", "Reload Pistol")

        # Direct execution
        success = reload_action._execute("player1", game_state)
        # Pistol now has 6 ammunition
        ```
    """

    def __init__(self, weapon: Any):
        """
        Initialize a reload action for the specified weapon.

        Args:
            weapon: The weapon instance to be reloaded. Must have ammunition,
                   max_ammunition and reloadable attributes.
        """
        self.weapon = weapon
        action_type_enum = ActionType.PRIMARY if getattr(weapon, 'reload_action_type',
                                                         'secondary') == 'primary' else ActionType.SECONDARY
        super().__init__(
            name=f"Reload {weapon.name}",
            action_type=action_type_enum,
            execute_func=self._execute,
            is_available_func=self._is_available,
            description=f"Reload the {weapon.name}.",
            keywords=["reload"],
            incompatible_keywords=["reload"],  # Or other keywords like "attack" if reload prevents attack
            per_turn_limit=1
        )

    def _is_available(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Checks if the reload action is available.

        An action is available if:
        1. The weapon has the 'reloadable' attribute set to True
        2. The weapon's current ammunition is less than its maximum capacity

        Args:
            entity_id: The ID of the entity attempting to reload.
            game_state: The current game state.
            **action_params: Additional parameters (not used by this action).

        Returns:
            bool: True if the weapon is reloadable and not fully loaded, False otherwise.

        Example:
            ```python
            # Check if reload action is available
            if reload_action._is_available("player1", game_state):
                print("Player can reload their weapon")
            else:
                print("Weapon cannot be reloaded (already full or not reloadable)")
            ```
        """
        # game_state might be used here if availability depends on external factors
        return getattr(self.weapon, 'reloadable', False) and self.weapon.ammunition < self.weapon.max_ammunition

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Executes the reload action.

        This method resets the weapon's ammunition to its maximum value
        and logs the result of the action.

        Args:
            entity_id: The ID of the entity performing the reload.
            game_state: The current game state (may be used for event publishing).
            **action_params: Additional parameters (not used by this action).

        Returns:
            bool: True if the reload was successful, False otherwise.

        Side effects:
            - Updates weapon's ammunition count
            - Outputs informational messages about the reload operation
            - Could publish an event when uncommented (game_state.event_bus.publish)

        Example:
            ```python
            # Execute the reload action
            if reload_action._execute("player1", game_state):
                print("Weapon reloaded successfully")
            else:
                print("Reload failed")
            ```
        """
        if not getattr(self.weapon, 'reloadable', False):
            print(f"[Reload] {self.weapon.name} cannot be reloaded by {entity_id}!")
            return False
        if self.weapon.ammunition >= self.weapon.max_ammunition:
            print(f"[Reload] {self.weapon.name} is already fully loaded for {entity_id}.")
            return False  # Or True if "attempting to reload full weapon" is not an error

        self.weapon.reload()
        print(f"[Reload] {entity_id} reloaded {self.weapon.name} to {self.weapon.ammunition}.")
        # Potentially publish an event:
        # game_state.event_bus.publish("weapon_reloaded", entity_id=entity_id, weapon_name=self.weapon.name, ammo=self.weapon.ammunition)
        return True