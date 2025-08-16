# ecs/actions/defense_actions.py
"""
Defense action system module that handles different defensive options for entities.

This module implements various defensive actions that characters can take in response
to attacks, including dodging ranged attacks, dodging close combat attacks, parrying,
and absorbing damage.

Each defense type is implemented as a separate Action subclass with appropriate traits
and dice rolls for resolution.
"""

from ecs.systems.action_system import Action, ActionType
from core.player_input import choose_defense
from entities.dice import Dice
from random import choice
from typing import Callable, List, Optional, Any, Union


class DodgeRangedAction(Action):
    """
    Represents the action of dodging a ranged attack.

    This defense provides a flat modifier to defense rather than using a dice pool.

    Attributes:
        movement_system: Reference to the movement system for position updates.
        dice_roller (Dice): Dice roller instance for rolling defense dice.

    Example:
        ```python
        # Create a dodge ranged action with the game's movement system
        dodge_ranged = DodgeRangedAction(game_state.movement)

        # Execute the action to get defense successes
        successes = dodge_ranged._execute("player_id", game_state)
        # Will return 2 successes (flat value)
        ```
    """

    def __init__(self, movement_system: Any):
        """
        Initializes a DodgeRangedAction.

        Args:
            movement_system: The movement system used in the game.
        """
        super().__init__(
            name="Dodge (ranged)",
            action_type=ActionType.SECONDARY,
            execute_func=self._execute,
            description="Dodge a ranged attack",
            keywords=["defense", "dodge"],
            incompatible_keywords=["defense"],
            per_turn_limit=1
        )
        self.movement_system = movement_system
        self.dice_roller = Dice()

    def _execute(self, entity_id: str, game_state: Any) -> int:
        """
        Executes the dodge (ranged) action.

        Unlike other defenses, this provides a flat value rather than rolling.

        Args:
            entity_id: The ID of the entity performing the action.
            game_state: The current game state.

        Returns:
            int: 2, to indicate the action works. It does not roll dice and reduce the pool of the attacker by a flat 2.
        """
        return 2


class DodgeCloseCombatAction(Action):
    """
    Represents the action of dodging a close combat attack.

    This defense uses Dexterity + Athletics to determine the number of defense successes.
    On successful dodges, the character may move to an adjacent tile if possible.

    Attributes:
        movement_system: Reference to the movement system for position updates.
        dice_roller (Dice): Dice roller instance for rolling defense dice.

    Example:
        ```python
        # Create a dodge close combat action with the game's movement system
        dodge_melee = DodgeCloseCombatAction(game_state.movement)

        # Execute the action to get defense successes
        successes = dodge_melee._execute("player_id", game_state)
        # Returns number of successes from Dexterity + Athletics roll
        ```
    """

    def __init__(self, movement_system: Any):
        """
        Initializes a DodgeCloseCombatAction.

        Args:
            movement_system: The movement system used in the game.
        """
        super().__init__(
            name="Dodge (close combat)",
            action_type=ActionType.SECONDARY,
            execute_func=self._execute,
            description="Dodge a close combat attack",
            keywords=["defense", "dodge"],
            incompatible_keywords=["defense"],
            per_turn_limit=1
        )
        self.movement_system = movement_system
        self.dice_roller = Dice()

    def _execute(self, entity_id: str, game_state: Any) -> int:
        """
        Executes the dodge (close combat) action.

        Uses Dexterity + Athletics for the defense dice pool.

        Args:
            entity_id: The ID of the entity performing the action.
            game_state: The current game state.

        Returns:
            int: The number of defense successes.
        """
        entity = game_state.get_entity(entity_id)
        char = entity["character_ref"].character
        dex = char.traits.get("Attributes", {}).get("Physical", {}).get("Dexterity", 0)
        ath = char.traits.get("Abilities", {}).get("Talents", {}).get("Athletics", 0)
        defense_pool = dex + ath
        defense_roll = self.dice_roller.roll_pool(defense_pool, hunger_dice=0)
        defense_successes = defense_roll["successes"] + defense_roll["critical_successes"] + defense_roll[
            "hunger_bestial_successes"]
        return defense_successes


class ParryAction(Action):
    """
    Represents the action of parrying a close combat attack.

    This defense uses Dexterity + Melee to determine the number of defense successes.
    Parrying requires the character to be armed with a melee weapon to be effective.

    Attributes:
        dice_roller (Dice): Dice roller instance for rolling defense dice.

    Example:
        ```python
        # Create a parry action
        parry = ParryAction()

        # Execute the action to get defense successes
        successes = parry._execute("player_id", game_state)
        # Returns number of successes from Dexterity + Melee roll
        ```
    """

    def __init__(self):
        """
        Initializes a ParryAction.
        """
        super().__init__(
            name="Parry",
            action_type=ActionType.SECONDARY,
            execute_func=self._execute,
            description="Parry a close combat attack",
            keywords=["defense", "parry"],
            incompatible_keywords=["defense"],
            per_turn_limit=1
        )
        self.dice_roller = Dice()

    def _execute(self, entity_id: str, game_state: Any) -> int:
        """
        Executes the parry action.

        Uses Dexterity + Melee for the defense dice pool.

        Args:
            entity_id: The ID of the entity performing the action.
            game_state: The current game state.

        Returns:
            int: The number of defense successes.
        """
        entity = game_state.get_entity(entity_id)
        char = entity["character_ref"].character
        dex = char.traits.get("Attributes", {}).get("Physical", {}).get("Dexterity", 0)
        melee = char.traits.get("Abilities", {}).get("Skills", {}).get("Melee", 0)
        defense_pool = dex + melee
        defense_roll = self.dice_roller.roll_pool(defense_pool, hunger_dice=0)
        defense_successes = defense_roll["successes"] + defense_roll["critical_successes"] + defense_roll[
            "hunger_bestial_successes"]
        return defense_successes


class AbsorbAction(Action):
    """
    Represents the action of absorbing damage using stamina and brawl.

    This defense uses Stamina + Brawl to determine the number of defense successes.
    Instead of avoiding the hit, it reduces the amount of damage taken.

    Attributes:
        dice_roller (Dice): Dice roller instance for rolling defense dice.

    Example:
        ```python
        # Create an absorb action
        absorb = AbsorbAction()

        # Execute the action to get defense successes
        successes = absorb._execute("player_id", game_state)
        # Returns number of successes from Stamina + Brawl roll
        # Each success reduces damage by 1
        ```
    """

    def __init__(self):
        """
        Initializes an AbsorbAction.
        """
        super().__init__(
            name="Absorb",
            action_type=ActionType.SECONDARY,
            execute_func=self._execute,
            description="Absorb damage with stamina and brawl",
            keywords=["defense", "absorb"],
            incompatible_keywords=["defense"],
            per_turn_limit=1
        )
        self.dice_roller = Dice()

    def _execute(self, entity_id: str, game_state: Any) -> int:
        """
        Executes the absorb action.

        Uses Stamina + Brawl for the defense dice pool.

        Args:
            entity_id: The ID of the entity performing the action.
            game_state: The current game state.

        Returns:
            int: The number of defense successes.
        """
        entity = game_state.get_entity(entity_id)
        char = entity["character_ref"].character
        sta = char.traits.get("Attributes", {}).get("Physical", {}).get("Stamina", 0)
        brawl = char.traits.get("Abilities", {}).get("Talents", {}).get("Brawl", 0)
        defense_pool = sta + brawl
        defense_roll = self.dice_roller.roll_pool(defense_pool, hunger_dice=0)
        defense_successes = defense_roll["successes"] + defense_roll["critical_successes"] + defense_roll[
            "hunger_bestial_successes"]
        return defense_successes


def choose_defensive_action(available_defenses: List[str], is_ai: bool = False,
                            ai_strategy: Optional[Callable[[List[str]], str]] = None) -> str:
    """
    Chooses a defensive action for the player or AI.

    If is_ai is True, either uses the provided ai_strategy or selects randomly.
    Otherwise, it prompts the player to choose from available defenses.

    Args:
        available_defenses: List of available defense action names.
        is_ai: If True, use AI logic; else, use player input.
        ai_strategy: Custom AI strategy function.

    Returns:
        str: The chosen defense action name.

    Example:
        ```python
        # Get player choice
        defense = choose_defensive_action(
            ["Dodge (ranged)", "Absorb"]
        )

        # Get AI choice
        def prefer_dodge(options):
            return next((o for o in options if "Dodge" in o), options[0])

        ai_defense = choose_defensive_action(
            ["Dodge (close combat)", "Parry", "Absorb"],
            is_ai=True,
            ai_strategy=prefer_dodge
        )
        ```
    """
    if is_ai:
        if ai_strategy:
            return ai_strategy(available_defenses)
        # Default AI: pick randomly
        return choice(available_defenses)
    else:
        return choose_defense(available_defenses)