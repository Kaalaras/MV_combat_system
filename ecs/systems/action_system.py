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

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ActionType(Enum):
    """
    Enumeration of action types used to categorize actions and determine their cost.
    """
    PRIMARY = "PRIMARY"            # consumes primary action slot
    SECONDARY = "SECONDARY"        # consumes secondary action slot
    FREE = "FREE"                  # does not consume slots
    LIMITED_FREE = "LIMITED_FREE"  # free but limited per turn (e.g., bonus steps)
    REACTION = "REACTION"          # triggered outside of the entity's turn


@dataclass
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

    name: str
    action_type: ActionType
    execute_func: Callable[..., Any]
    is_available_func: Optional[Callable[..., bool]] = None
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    incompatible_keywords: List[str] = field(default_factory=list)
    per_turn_limit: int = 1
    cooldown: int = 0

    def is_available(self, entity_id: str, game_state, **action_params) -> bool:
        """
        Check if the action is available for the given entity and game state.
        """
        if self.is_available_func:
            try:
                return bool(self.is_available_func(entity_id, game_state, **action_params))
            except Exception as e:
                print(f"[ActionSystem][WARN] availability func error for {self.name}: {e}")
                return False
        return True

    def execute(self, entity_id: str, game_state, **action_params) -> Any:
        """
        Execute the action logic.
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

    def __init__(self, game_state, event_bus=None):
        self.game_state = game_state
        self.event_bus = event_bus

        # Registered actions per entity
        self.available_actions: Dict[str, List[Action]] = {}

        # Action counters per entity (reset every turn)
        self.action_counters: Dict[str, Dict[ActionType, int]] = {}

        # Limited free actions per-turn usage
        self.limited_free_counters: Dict[str, Dict[str, int]] = {}

        # Keywords used by entity this turn
        self.used_keywords: Dict[str, set] = {}

        # Per-turn action counts
        self.per_turn_action_counts: Dict[str, Dict[str, int]] = {}

        # Cooldowns per entity
        self.cooldowns: Dict[str, Dict[str, int]] = {}

        if self.event_bus:
            self.event_bus.subscribe("action_requested", self.handle_action_requested)

    # --- Helpers for robust enum handling -----------------------------------
    def _normalize_action_type(self, at) -> str:
        """Return a stable string for an ActionType-like object (enum or str)."""
        try:
            return at.value
        except AttributeError:
            return str(at)

    def _is_free_like(self, action) -> bool:
        v = self._normalize_action_type(action.action_type)
        try:
            return v in (ActionType.FREE.value, ActionType.LIMITED_FREE.value)
        except Exception:
            return v in ("FREE", "LIMITED_FREE")
    # ------------------------------------------------------------------------

    def register_action(self, entity_id: str, action: Action):
        """
        Register an action for a specific entity.
        """
        self.available_actions.setdefault(entity_id, []).append(action)

    def unregister_action(self, entity_id: str, action_name: str):
        """
        Unregister an action by name for a specific entity.
        """
        if entity_id in self.available_actions:
            self.available_actions[entity_id] = [
                a for a in self.available_actions[entity_id] if a.name != action_name
            ]

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
        """
        action = self.find_action_by_name(entity_id, action_name)
        if not action:
            print(f"[ActionSystem][WARN] Action '{action_name}' not found for entity {entity_id}")
            if self.event_bus:
                self.event_bus.publish("action_failed", entity_id=entity_id, action_name=action_name, reason="not_found")
            return

        if not self.can_perform_action(entity_id, action, **action_params):
            print(f"[ActionSystem][DEBUG] Action '{action_name}' cannot be performed by {entity_id}")
            if self.event_bus:
                self.event_bus.publish("action_failed", entity_id=entity_id, action_name=action_name, reason="unavailable")
            return

        result = self.perform_action(entity_id, action, **action_params)
        if self.event_bus:
            try:
                self.event_bus.publish("action_performed", entity_id=entity_id, action_name=action.name, result=result)
            except Exception as e:
                print(f"[ActionSystem][WARN] Failed to publish action_performed: {e}")
        return result

    def reset_counters(self, entity_id: str):
        """
        Reset action counters and turn-specific tracking for an entity.

        Args:
            entity_id: The identifier of the entity
        """
        self.action_counters[entity_id] = {
            ActionType.PRIMARY: 1,
            ActionType.SECONDARY: 1,
            ActionType.FREE: float('inf'),           # effectively unlimited
            ActionType.LIMITED_FREE: float('inf'),   # limit handled by per_turn_limit + custom logic if needed
            ActionType.REACTION: 1,                  # baseline: one reaction per round
        }
        # Apply condition system action slot modifiers
        cond_sys = getattr(self.game_state, 'condition_system', None)
        if cond_sys:
            self.action_counters[entity_id] = cond_sys.apply_action_slot_modifiers(entity_id, self.action_counters[entity_id])
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

        # Use action_params to pass target, positions, weapons, etc. to availability logic
        if not action.is_available(entity_id, self.game_state, **action_params):
            print(f"[ActionSystem][DEBUG] is_available=False for {action.name}")
            return False

        # Check per-turn limits
        per_turn_map = self.per_turn_action_counts.setdefault(entity_id, {})
        used_count = per_turn_map.get(action.name, 0)
        per_turn_limit = action.per_turn_limit
        if per_turn_limit is not None and used_count >= per_turn_limit:
            print(
                f"[ActionSystem][DEBUG] per-turn limit reached for {action.name} ({used_count}/{per_turn_limit})"
            )
            return False

        # Check cooldowns
        cd_map = self.cooldowns.setdefault(entity_id, {})
        cd_val = cd_map.get(action.name, 0)
        if cd_val and cd_val > 0:
            print(f"[ActionSystem][DEBUG] cooldown active for {action.name}: {cd_val}")
            return False

        # Keyword incompatibilities
        used = self.used_keywords.setdefault(entity_id, set())
        if any(kw in used for kw in action.incompatible_keywords):
            print(f"[ActionSystem][DEBUG] incompatible keyword in use; used={used}, incompatible={action.incompatible_keywords}")
            return False

        # Slot availability (robust to duplicated Enum classes)
        if self._is_free_like(action):
            return True
        else:
            # exact enum key first
            if self.action_counters[entity_id].get(action.action_type, 0) > 0:
                return True
            # value-match fallback (handles duplicated Enum classes across modules)
            needed_val = self._normalize_action_type(action.action_type)
            for k, v in self.action_counters[entity_id].items():
                if self._normalize_action_type(k) == needed_val and v > 0:
                    return True
            print(f"[ActionSystem][DEBUG] no action points for {action.name} type {action.action_type}")
            return False

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
            action: The action to execute
            **action_params: Parameters for the action execution

        Returns:
            Any: The result of the action's execute function
        """
        # Update per-turn count
        per_turn_map = self.per_turn_action_counts.setdefault(entity_id, {})
        per_turn_map[action.name] = per_turn_map.get(action.name, 0) + 1

        # Set cooldown if any
        if action.cooldown > 0:
            self.cooldowns.setdefault(entity_id, {})[action.name] = action.cooldown

        # Consume action points according to type
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
        elif action.action_type == ActionType.REACTION:
            # prefer exact key; else fallback by value
            if self.action_counters[entity_id].get(action.action_type, 0) > 0:
                self.action_counters[entity_id][action.action_type] -= 1
            else:
                needed_val = self._normalize_action_type(action.action_type)
                for k in list(self.action_counters[entity_id].keys()):
                    if self._normalize_action_type(k) == needed_val and self.action_counters[entity_id][k] > 0:
                        self.action_counters[entity_id][k] -= 1
                        break
        elif not self._is_free_like(action):  # PRIMARY / SECONDARY
            if self.action_counters[entity_id].get(action.action_type, 0) > 0:
                self.action_counters[entity_id][action.action_type] -= 1
            else:
                needed_val = self._normalize_action_type(action.action_type)
                for k in list(self.action_counters[entity_id].keys()):
                    if self._normalize_action_type(k) == needed_val and self.action_counters[entity_id][k] > 0:
                        self.action_counters[entity_id][k] -= 1
                        break

        self.used_keywords.setdefault(entity_id, set()).update(action.keywords)

        # Pass entity_id, game_state, and action_params to the action's execute method
        result = action.execute(entity_id, self.game_state, **action_params)

        # Publish here as safety if direct calls bypass handle_action_requested
        if self.event_bus:
            try:
                self.event_bus.publish("action_performed", entity_id=entity_id, action_name=action.name, result=result)
            except Exception as e:
                print(f"[ActionSystem][WARN] Failed to publish action_performed (direct): {e}")
        return result  # Return the actual result from action execution
