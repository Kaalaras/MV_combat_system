# ecs/systems/action_system.py
"""
Action System Module
===================

This module implements a flexible action system for turn-based games using an Entity Component System (ECS)
architecture. It provides classes for defining, registering, and executing game actions with various
constraints like action types, cooldowns, and usage limits.

Example:
    # Create a game state and event bus
    game_state = GameState()
    event_bus = EventBus()

    # Initialize the action system
    action_system = ActionSystem(game_state, event_bus)

    # Define an attack action
    def can_attack(entity_id, game_state, **params):
        # Check if entity has a weapon, target is in range, etc.
        return True

    def execute_attack(entity_id, game_state, target_id, **params):
        # Perform attack logic
        damage = 10
        return {"damage": damage, "target": target_id}

    attack = Action(
        name="attack",
        action_type=ActionType.PRIMARY,
        execute_func=execute_attack,
        is_available_func=can_attack,
        description="Attack an enemy",
        keywords=["offensive"],
        per_turn_limit=1
    )

    # Register the action for a character
    action_system.register_action("player1", attack)

    # Reset action counters at the start of turn
    action_system.reset_counters("player1")

    # Trigger the action via the event bus
    event_bus.publish("action_requested", entity_id="player1", action_name="attack", target_id="enemy1")
"""
from enum import Enum
from typing import Dict, List, Optional, Callable, Any


class ActionType(Enum):
    """
    Enum defining the different types of actions and their associated costs.

    Attributes:
        PRIMARY: Main actions that typically cost a primary action point
        SECONDARY: Less impactful actions that cost a secondary action point
        FREE: Actions that can be performed without consuming action points
        LIMITED_FREE: Actions that are free but have per-turn usage limitations
    """
    PRIMARY = "primary"
    SECONDARY = "secondary"
    FREE = "free"
    LIMITED_FREE = "limited_free"


class Action:
    """
    Represents a game action that can be performed by an entity.

    Attributes:
        name (str): Unique identifier for the action
        action_type (ActionType): The type of action which determines its cost
        execute_func (Callable): Function that implements the action's behavior
        is_available_func (Optional[Callable]): Function that determines if the action can be used
        description (str): Human-readable description of the action
        keywords (list): Tags that categorize the action and may affect interactions
        incompatible_keywords (list): Keywords that make this action unavailable if used
        per_turn_limit (int): Maximum number of times this action can be used per turn
        cooldown (int): Number of turns to wait before the action can be used again
    """

    def __init__(self,
                 name: str,
                 action_type: ActionType,
                 execute_func: Callable,
                 is_available_func: Optional[Callable] = None,
                 description: str = "",
                 keywords: Optional[list] = None,
                 incompatible_keywords: Optional[list] = None,
                 per_turn_limit: int = None,
                 cooldown: int = 0):
        """
        Initialize a new Action.

        Args:
            name: Unique identifier for the action
            action_type: The type of action which determines its cost
            execute_func: Function that implements the action's behavior
            is_available_func: Function that determines if the action can be used
            description: Human-readable description of the action
            keywords: Tags that categorize the action and may affect interactions
            incompatible_keywords: Keywords that make this action unavailable if used
            per_turn_limit: Maximum number of times this action can be used per turn
            cooldown: Number of turns to wait before the action can be used again
        """
        self.name = name
        self.action_type = action_type
        self.execute_func = execute_func
        self.is_available_func = is_available_func
        self.description = description
        self.keywords = keywords or []
        self.incompatible_keywords = incompatible_keywords or []
        self.per_turn_limit = per_turn_limit
        self.cooldown = cooldown

    def is_available(self, entity_id, game_state, **action_params) -> bool:
        """
        Checks if the action is available for the given entity in the current game state,
        considering specific action parameters if provided.

        Args:
            entity_id: The identifier of the entity attempting the action
            game_state: The current state of the game
            **action_params: Additional parameters specific to this action instance

        Returns:
            bool: True if the action is available, False otherwise
        """
        if self.is_available_func:
            # Pass entity_id, game_state, and any action_params to the specific availability check
            return self.is_available_func(entity_id, game_state, **action_params)
        return True

    def execute(self, entity_id: str, game_state: Any, **action_params) -> Any:
        """
        Executes the action using the provided arguments.

        The execute_func is expected to have a signature like:
        func(entity_id, game_state, **action_params)

        Args:
            entity_id: The identifier of the entity performing the action
            game_state: The current state of the game
            **action_params: Additional parameters specific to this action instance

        Returns:
            Any: The result of executing the action, dependent on the specific action implementation
        """
        return self.execute_func(entity_id, game_state, **action_params)


class ActionSystem:
    """
    Manages the registration, availability, and execution of actions for game entities.

    This system keeps track of action slots, cooldowns, and restrictions for each entity,
    and handles the execution of actions triggered via events.

    Attributes:
        game_state: The current state of the game
        event_bus: Event system for communication between game components
        available_actions: Dictionary mapping entity IDs to their available actions
        action_counters: Dictionary tracking remaining action points for each entity
        limited_free_counters: Dictionary tracking usage of limited free actions
        used_keywords: Dictionary tracking keywords used by each entity during their turn
        per_turn_action_counts: Dictionary tracking how many times each action was used per turn
        cooldowns: Dictionary tracking cooldowns for each entity's actions
    """

    def __init__(self, game_state: Any, event_bus: Any):
        """
        Initialize the ActionSystem.

        Args:
            game_state: The current state of the game
            event_bus: Event system for communication between game components
        """
        self.game_state = game_state
        self.event_bus = event_bus
        self.available_actions: Dict[str, List[Action]] = {}
        self.action_counters: Dict[str, Dict[ActionType, float]] = {}
        self.limited_free_counters: Dict[str, Dict[str, int]] = {}
        self.used_keywords: Dict[str, set] = {}
        self.per_turn_action_counts: Dict[str, Dict[str, int]] = {}
        self.cooldowns: Dict[str, Dict[str, int]] = {}

        if self.event_bus:
            self.event_bus.subscribe("action_requested", self.handle_action_requested)

    def find_action_by_name(self, entity_id: str, action_name: str) -> Optional[Action]:
        """
        Find an action available to an entity by its name.

        Args:
            entity_id: The identifier of the entity
            action_name: The name of the action to find

        Returns:
            Optional[Action]: The action if found, None otherwise
        """
        for action in self.available_actions.get(entity_id, []):
            if action.name == action_name:
                return action
        return None

    def handle_action_requested(self, entity_id: str, action_name: str, **action_params):
        """
        Handles an 'action_requested' event by finding, validating, and executing the requested action.

        This method is typically triggered by the event bus when an entity attempts to perform an action.
        It checks if the action exists and can be performed, then executes it and publishes the result.

        Args:
            entity_id: The identifier of the entity attempting the action
            action_name: The name of the action to perform
            **action_params: Additional parameters for the action execution
        """
        # If 'params' is present in action_params, unpack it and merge with other action_params
        params_dict = action_params.pop('params', None)
        if params_dict and isinstance(params_dict, dict):
            action_params.update(params_dict)

        # print(f"[ActionSystem] Received action_requested: {entity_id}, {action_name}, {action_params}")
        action_to_perform = self.find_action_by_name(entity_id, action_name)

        if not action_to_perform:
            print(f"[ActionSystem] Action '{action_name}' not found for entity {entity_id}.")
            if self.event_bus:
                self.event_bus.publish("action_failed", entity_id=entity_id, action_name=action_name,
                                       reason="Action not found", params=action_params)
            return

        # Pass action_params to can_perform_action for specific availability checks
        if self.can_perform_action(entity_id, action_to_perform, **action_params):
            result = self.perform_action(entity_id, action_to_perform, **action_params)
            # perform_action now returns the direct result of action.execute()
            # The event payload should reflect this.
            if self.event_bus:
                # Assuming 'result' indicates success if not False or None,
                # specific actions might return damage, status, etc.
                # For simplicity, let's assume any non-False/None result means performed.
                # A more robust system might have execute() return a status object.
                if result is not False and result is not None:  # Crude check for success
                    self.event_bus.publish("action_performed", entity_id=entity_id, action_name=action_name,
                                           result=result, params=action_params)
                else:  # Explicit False or None indicates failure from execute
                    self.event_bus.publish("action_failed", entity_id=entity_id, action_name=action_name,
                                           reason="Execution failed", result=result, params=action_params)
        else:
            print(f"[ActionSystem] Cannot perform action '{action_name}' for entity {entity_id}.")
            if self.event_bus:
                self.event_bus.publish("action_failed", entity_id=entity_id, action_name=action_name,
                                       reason="Cannot perform action (rules/state)", params=action_params)

    def register_action(self, entity_id: str, action: Action):
        """
        Register an action as available to an entity.

        Args:
            entity_id: The identifier of the entity
            action: The action to register
        """
        if entity_id not in self.available_actions:
            self.available_actions[entity_id] = []
        self.available_actions[entity_id].append(action)

    def reset_counters(self, entity_id: str):
        """
        Reset all action counters for an entity at the start of their turn.

        This method reestablishes the standard action economy for the entity:
        - 1 primary action
        - 1 secondary action
        - Unlimited free actions
        - Resets per-turn action counts
        - Clears used keywords

        Args:
            entity_id: The identifier of the entity
        """
        self.action_counters[entity_id] = {
            ActionType.PRIMARY: 1,
            ActionType.SECONDARY: 1,
            ActionType.FREE: float('inf'),  # Effectively unlimited
            ActionType.LIMITED_FREE: float('inf')  # Base availability, specific limits handled by per_turn_limit
        }
        self.limited_free_counters[entity_id] = {}
        self.used_keywords[entity_id] = set()
        self.per_turn_action_counts[entity_id] = {}
        if entity_id not in self.cooldowns:
            self.cooldowns[entity_id] = {}

    def decrement_cooldowns(self):
        """
        Decrease all action cooldowns by 1 at the end of a round.

        Removes cooldown entries that have reached zero.
        """
        for entity_id, cooldowns in self.cooldowns.items():
            for action_name in list(cooldowns.keys()):  # Iterate over a copy of keys
                cooldowns[action_name] = max(0, cooldowns[action_name] - 1)
                if cooldowns[action_name] == 0:
                    del cooldowns[action_name]

    def can_perform_action(self, entity_id: str, action: Action, **action_params) -> bool:
        """
        Determine if an entity can perform a specific action.

        Checks various constraints:
        - Action-specific availability logic
        - Per-turn usage limits
        - Cooldowns
        - Keyword incompatibilities
        - Action point availability

        Args:
            entity_id: The identifier of the entity attempting the action
            action: The action to check
            **action_params: Additional parameters specific to this action instance

        Returns:
            bool: True if the action can be performed, False otherwise
        """
        if entity_id not in self.action_counters:
            self.reset_counters(entity_id)

        # Use action_params for the action-specific availability check
        if not action.is_available(entity_id, self.game_state, **action_params):
            return False

        count = self.per_turn_action_counts.get(entity_id, {}).get(action.name, 0)
        if action.per_turn_limit is not None and count >= action.per_turn_limit:
            return False

        if self.cooldowns.get(entity_id, {}).get(action.name, 0) > 0:
            return False

        used = self.used_keywords.get(entity_id, set())
        if any(kw in used for kw in action.incompatible_keywords):
            return False

        if action.action_type == ActionType.LIMITED_FREE:
            # For limited free, per_turn_limit is the primary constraint.
            # If it costs a secondary action after first use, that's handled during perform_action.
            # Here, we just check if it's generally allowed by limits.
            return True  # Specific per_turn_limit already checked
        elif action.action_type == ActionType.FREE:
            return True
        else:  # PRIMARY or SECONDARY
            return self.action_counters[entity_id].get(action.action_type, 0) > 0

    def perform_action(self, entity_id: str, action: Action, **action_params) -> Any:
        """
        Execute an action and update relevant counters.

        This method assumes can_perform_action() has already verified the action can be performed.
        It handles:
        - Updating per-turn usage counts
        - Setting cooldowns
        - Consuming action points
        - Tracking used keywords
        - Executing the actual action logic

        Args:
            entity_id: The identifier of the entity performing the action
            action: The action to perform
            **action_params: Additional parameters specific to this action instance

        Returns:
            Any: The result returned by the action's execute method
        """
        # Note: can_perform_action should have been called with action_params before this.
        # This method now focuses on execution and counter updates.

        # Per-turn count update
        self.per_turn_action_counts.setdefault(entity_id, {})
        self.per_turn_action_counts[entity_id][action.name] = \
            self.per_turn_action_counts[entity_id].get(action.name, 0) + 1

        if action.cooldown > 0:
            self.cooldowns.setdefault(entity_id, {})[
                action.name] = action.cooldown + 1  # Cooldown is for N future rounds

        if action.action_type == ActionType.LIMITED_FREE:
            # Logic for limited free actions that might consume a secondary action slot
            # This depends on specific game rules (e.g., first is free, subsequent cost secondary)
            # For now, assume per_turn_limit handles it. If it needs to cost secondary:
            # current_uses = self.limited_free_counters.get(entity_id, {}).get(action.name, 0)
            # if current_uses > 0: # If not the first use (assuming first use is free part)
            #     if self.action_counters[entity_id][ActionType.SECONDARY] > 0:
            #         self.action_counters[entity_id][ActionType.SECONDARY] -= 1
            #     else:
            #         # This case should ideally be caught by can_perform_action if it's more complex
            #         print(f"Warning: {action.name} (limited free) attempted without secondary action slot.")
            # self.limited_free_counters.setdefault(entity_id, {})[action.name] = current_uses + 1
            pass  # Simplified: per_turn_limit is the main check via can_perform_action

        elif action.action_type != ActionType.FREE:  # PRIMARY or SECONDARY
            self.action_counters[entity_id][action.action_type] -= 1

        self.used_keywords.setdefault(entity_id, set()).update(action.keywords)

        # Pass entity_id, game_state, and action_params to the action's execute method
        result = action.execute(entity_id, self.game_state, **action_params)

        # Removed event publishing from here, will be done in handle_action_requested
        return result  # Return the actual result from action execution