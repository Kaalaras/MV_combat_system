# ecs/actions/attack_actions.py
from ecs.systems.action_system import Action, ActionType  # Ensure Action, ActionType are imported
from entities.weapon import Weapon  # Ensure Weapon is imported
from entities.character import Character  # Ensure Character is imported
from entities.dice import Dice
from typing import Any, Tuple, Optional, List, Dict
from random import choice
from math import floor
from ecs.actions.defensive_actions import (
    DodgeRangedAction,
    DodgeCloseCombatAction,
    ParryAction,
    AbsorbAction,
    choose_defensive_action,
)
from ecs.systems.ai.utils import calculate_distance_between_entities, calculate_distance_from_point_to_bbox


class AttackAction:
    """
    Represents an attack action between two entities in the game.

    This class handles the full attack resolution process including:
    - Attacker's dice pool calculation
    - Target's defensive options and resolution
    - Damage calculation and application including armor reduction
    - Movement effects from successful dodges

    Attributes:
        attacker_id (str): The ID of the attacking entity.
        target_id (str): The ID of the target entity.
        weapon (Weapon): The weapon used for the attack.
        game_state (Any): The current game state.
        dice_roller (Dice): Dice roller utility for resolving actions.

    Example:
        ```python
        # Create and execute an attack
        attack = AttackAction(
            attacker_id="player1",
            target_id="enemy2",
            weapon=player_sword,
            game_state=game_state
        )
        damage_dealt = attack.execute()
        ```
    """

    def __init__(self, attacker_id: str, target_id: str, weapon: Weapon, game_state: Any):
        """
        Initialize a new attack action.

        Args:
            attacker_id: ID of the entity performing the attack
            target_id: ID of the entity being attacked
            weapon: Weapon object used for the attack
            game_state: Current game state containing entity data and systems
        """
        self.attacker_id = attacker_id
        self.target_id = target_id
        self.weapon = weapon
        self.game_state = game_state
        self.dice_roller = Dice()

    def _get_distance_point_to_entity(self, point: Tuple[int, int], entity_id: str) -> int:
        """Calculates Manhattan distance from a point to the closest point on an entity's bounding box."""
        target_entity = self.game_state.get_entity(entity_id)
        if not target_entity or "position" not in target_entity:
            return float('inf')  # Or some other large number indicating an error/impossibility

        target_pos = target_entity["position"]
        target_box = {'x1': target_pos.x1, 'y1': target_pos.y1, 'x2': target_pos.x2, 'y2': target_pos.y2}

        return calculate_distance_from_point_to_bbox(point, target_box)

    def _get_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        """Calculate Manhattan distance between two points."""
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

    def _move_defender_randomly(self, target: Character) -> None:
        """
        Move the defending character to a random adjacent tile when successfully dodging.

        Args:
            target: Character instance of the defender

        Returns:
            None

        Note:
            Relies on movement_system being properly set on game_state
        """
        entity_data = self.game_state.get_entity(self.target_id)  # target_id is defender
        position = entity_data.get("position")
        movement_system = getattr(self.game_state, "movement", None)  # Critical dependency

        if not position or not movement_system:
            print(
                f"[Defense] {target.name} ({self.target_id}) would move but system components missing (position or movement_system on game_state)."
            )
            return

        # Get reachable tiles at distance 1, including current position
        # Pass target_id (defender's ID) to get_reachable_tiles
        reachable = movement_system.get_reachable_tiles(self.target_id, 1)
        valid_moves = [(x, y) for x, y, dist in reachable if
                       dist <= 1 and (x, y) != (position.x, position.y)]  # Exclude current tile

        if valid_moves:
            nx, ny = choice(valid_moves)
            # Use movement_system.move for the target_id (defender)
            moved = movement_system.move(self.target_id, (nx, ny))
            if moved:
                print(f"[Defense] {target.name} ({self.target_id}) dodges to ({nx}, {ny})!")
            else:
                print(
                    f"[Defense] {target.name} ({self.target_id}) failed to dodge using movement system to ({nx},{ny}).")
        else:
            print(f"[Defense] {target.name} ({self.target_id}) cannot dodge: no free adjacent cell.")

    def get_attack_traits(self, attacker: Character) -> int:
        """
        Calculate the total attack dice pool from attacker's traits and weapon.

        Args:
            attacker: Character performing the attack

        Returns:
            int: Total dice pool size for attack roll (attribute + skill)

        Example:
            ```python
            # If weapon.attack_traits = ["Physical.Strength", "Skills.Melee"]
            # And character has Strength=3, Melee=2
            # Returns 5
            pool = attack.get_attack_traits(character)
            ```
        """
        attr_path, skill_path = self.weapon.attack_traits
        attr = self._get_nested_trait(attacker.traits, attr_path)
        skill = self._get_nested_trait(attacker.traits, skill_path)
        return attr + skill

    def _get_nested_trait(self, traits: dict, path: str) -> int:
        """
        Traverse a dot-notation path through a nested dictionary to retrieve a trait value.

        Args:
            traits: Dictionary containing character traits
            path: Dot-notation string path (e.g. "Physical.Strength")

        Returns:
            int: Value of the trait at the given path, or 0 if not found
        """
        keys = path.split('.')
        value = traits
        for key in keys:
            if not isinstance(value, dict):
                return 0
            value = value.get(key, 0)
        if isinstance(value, int):
            return value
        return 0

    def get_available_defenses(self, defender: Character, is_close_combat: bool, is_superficial: bool) -> list:
        """
        Determine which defensive options are available to the defender based on context.

        Args:
            defender: Character being attacked
            is_close_combat: Whether this is a close combat attack
            is_superficial: Whether this attack deals superficial damage

        Returns:
            list: List of defense option names available to the defender

        Example:
            ```python
            # For a close combat attack with a knife (superficial damage) against
            # a character with armor, available defenses might be:
            # ["Dodge (close combat)", "Parry", "Absorb"]
            defenses = attack.get_available_defenses(
                defender=target,
                is_close_combat=True,
                is_superficial=True
            )
            ```
        """
        available = []  # Start with empty, add "Dodge" based on context

        # All attacks can be Dodged in some way
        if is_close_combat:
            available.append("Dodge (close combat)")
        else:
            available.append("Dodge (ranged)")  # Assuming Dodge (ranged) is the name

        if is_close_combat:  # Parry is only for close combat
            available.append("Parry")

        has_armor = False
        equipment = self.game_state.get_entity(self.target_id).get("equipment")
        if equipment and equipment.armor and equipment.armor.armor_value > 0:
            has_armor = True

        fortitude = defender.traits.get("Disciplines", {}).get("Fortitude", 0)

        # Absorb conditions:
        # - Close combat AND (superficial damage OR has armor OR Fortitude >= 1)
        # - Ranged attacks cannot be Absorbed this way (unless specific Fortitude power)
        if is_close_combat and (is_superficial or has_armor or fortitude >= 1):
            available.append("Absorb")

        # Ensure no duplicates if logic paths overlap, though current structure avoids it.
        return available

    def execute(self) -> int:
        """
        Execute the attack action, performing all rolls and damage calculations.

        This method handles the complete attack flow:
        1. Get attacker and target data and positions.
        2. Calculate distance and apply range penalties to the dice pool.
        3. Resolve the primary attack against the main target.
        4. Trigger any additional effects like Penetration or Area of Effect.

        Returns:
            int: Final damage dealt to the primary target.
        """
        attacker_entity = self.game_state.get_entity(self.attacker_id)
        target_entity = self.game_state.get_entity(self.target_id)

        if not attacker_entity or not target_entity:
            print(f"[Attack] Attacker {self.attacker_id} or Target {self.target_id} not found.")
            return 0

        attacker_pos = attacker_entity.get("position")
        target_pos = target_entity.get("position")

        if not attacker_pos or not target_pos:
            print(f"[Attack] Attacker or Target position not found.")
            return 0

        distance = calculate_distance_between_entities(self.game_state, self.attacker_id, self.target_id)

        # 1. Check Maximum Range
        if distance > self.weapon.maximum_range:
            print(f"[Attack] Failed. Target is beyond maximum range ({distance:.2f} > {self.weapon.maximum_range}).")
            return 0

        # 2. Calculate Initial Dice Pool and Apply Range Penalty
        attack_pool_size = self.get_attack_traits(attacker_entity["character_ref"].character)
        attack_pool_size = self._apply_range_penalty(attack_pool_size, distance)

        if attack_pool_size <= 0:
            print(f"[Attack] Failed. Dice pool reduced to {attack_pool_size} or less after range penalty.")
            return 0

        # 3. Resolve the primary attack
        damage_dealt, remaining_pool = self._resolve_single_attack(
            self.target_id,
            attack_pool_size
        )

        # 4. Apply post-attack effects (AoE, Penetration)
        if self.weapon.effects:
            context = {
                "game_state": self.game_state,
                "attacker_id": self.attacker_id,
                "primary_target_id": self.target_id,
                "weapon": self.weapon,
                "impact_pos": (target_pos.x, target_pos.y),
                "initial_dice_pool": attack_pool_size,
                "remaining_dice_pool": remaining_pool,
                "primary_damage": damage_dealt,
                "attack_action": self
            }
            for effect in self.weapon.effects:
                effect.apply(self.game_state, context)

        return damage_dealt

    def _resolve_single_attack(self, target_id: str, attack_pool_size: int) -> Tuple[int, int]:
        """
        Resolves a single attack against a specific target.

        Args:
            target_id: The ID of the entity being attacked.
            attack_pool_size: The dice pool for this specific attack.

        Returns:
            A tuple containing (damage_dealt, remaining_dice_pool_for_penetration).
        """
        attacker_entity = self.game_state.get_entity(self.attacker_id)
        target_entity = self.game_state.get_entity(target_id)
        attacker = attacker_entity["character_ref"].character
        target = target_entity["character_ref"].character

        is_close_combat = (hasattr(self.weapon, 'weapon_type') and
                           (self.weapon.weapon_type in ["brawl", "melee"] or
                            (hasattr(self.weapon.weapon_type, 'value') and self.weapon.weapon_type.value in ["brawl", "melee"])))
        is_superficial = hasattr(self.weapon, 'damage_type') and self.weapon.damage_type == "superficial"

        available_defenses_names = self.get_available_defenses(target, is_close_combat, is_superficial)

        chosen_defense_name = None
        if available_defenses_names:
            is_ai_controlled_defender = target_entity.get("ai_controlled", target.is_ai_controlled)
            if is_ai_controlled_defender:
                preferred_order = ["Dodge (close combat)", "Dodge (ranged)", "Parry", "Absorb"]
                for preferred in preferred_order:
                    if preferred in available_defenses_names:
                        chosen_defense_name = preferred
                        break
                if not chosen_defense_name:
                    chosen_defense_name = choice(available_defenses_names)
            else:
                chosen_defense_name = choose_defensive_action(available_defenses_names)

        print(f"[Defense] {target.name} ({target_id}) available defenses: {available_defenses_names}. Chooses: {chosen_defense_name}")

        defense_successes = 0
        if chosen_defense_name:
            if chosen_defense_name == "Dodge (ranged)":
                defense_action = DodgeRangedAction(self.game_state.movement)
                defense_successes = defense_action._execute(target_id, self.game_state)
            elif chosen_defense_name == "Dodge (close combat)":
                defense_action = DodgeCloseCombatAction(self.game_state.movement)
                defense_successes = defense_action._execute(target_id, self.game_state)
            elif chosen_defense_name == "Parry":
                defense_action = ParryAction()
                defense_successes = defense_action._execute(target_id, self.game_state)
            elif chosen_defense_name == "Absorb":
                defense_action = AbsorbAction()
                defense_successes = defense_action._execute(target_id, self.game_state)
            print(f"[Defense] {target.name} uses {chosen_defense_name}, result: {defense_successes} successes.")

        # --- ATTACK ROLL ---
        attack_roll_results = self.dice_roller.roll_pool(attack_pool_size, hunger_dice=attacker.hunger)
        print(f"[Attack] {attacker.name} ({self.attacker_id}) attacks {target.name} ({target_id}) with {self.weapon.name}.")
        print(f"[Attack] Pool: {attack_pool_size}, Roll: {attack_roll_results}")

        current_attack_successes = (
            attack_roll_results["successes"] +
            attack_roll_results["critical_successes"] +
            attack_roll_results["hunger_bestial_successes"]
        )
        net_successes = current_attack_successes

        if chosen_defense_name in ["Dodge (close combat)", "Parry", "Dodge (ranged)"]:
            if defense_successes >= current_attack_successes:
                print(f"[Attack] Failed! {chosen_defense_name} successes ({defense_successes}) vs attack successes ({current_attack_successes}).")
                if chosen_defense_name == "Dodge (close combat)":
                    self._move_defender_randomly(target)
                return 0, 0 # No damage, no remaining dice
            else:
                net_successes = current_attack_successes - defense_successes
                print(f"[Attack] Hits! Net successes: {net_successes} (Attack {current_attack_successes} - {chosen_defense_name} {defense_successes})")
        elif chosen_defense_name == "Absorb":
            if current_attack_successes <= 0:
                print(f"[Attack] Failed! Attack successes: {current_attack_successes} (not enough to hit).")
                return 0, 0
            print(f"[Attack] Hits! Attack successes: {net_successes}. Absorb successes: {defense_successes} (will apply to damage).")
        elif not chosen_defense_name:
            if current_attack_successes <= 0:
                print(f"[Attack] Failed! Attack successes: {current_attack_successes} (not enough to hit).")
                return 0, 0
            print(f"[Attack] Hits! Attack successes: {net_successes}. No defense chosen/available.")

        # --- DAMAGE CALCULATION ---
        if net_successes <= 0:
            print(f"[Attack] Attack effectively defended or failed to achieve margin. Net successes: {net_successes}.")
            return 0, 0

        margin = net_successes - 1
        base_damage = self.weapon.get_damage_bonus() + margin
        print(f"[Damage] Base damage before reductions: {base_damage} (Weapon {self.weapon.get_damage_bonus()} + Margin {margin})")

        if chosen_defense_name == "Absorb":
            base_damage -= defense_successes
            print(f"[Damage] After Absorb reduction ({defense_successes}): {base_damage}")

        if base_damage <= 0:
            print("[Damage] Damage reduced to 0 or less. No damage dealt.")
            return 0, attack_pool_size - target.absorption

        final_damage = self._apply_armor_reduction(base_damage, target_id)

        if final_damage > 0:
            print(f"[Damage] Inflicting {final_damage} {self.weapon.damage_type} damage to {target.name}.")
            self._inflict_damage(target, final_damage, self.weapon.damage_type)
        else:
            print("[Damage] Final damage is 0 or less after all reductions.")

        remaining_pool = attack_pool_size - target.absorption
        return final_damage, remaining_pool

    def _apply_armor_reduction(self, damage: int, target_id: str) -> int:
        """
        Apply armor-based damage reduction based on target's equipment.

        Args:
            damage: Base damage amount before armor reduction
            target_id: ID of the character receiving the damage

        Returns:
            int: Damage amount after armor reduction
        """
        target_entity = self.game_state.get_entity(target_id)
        equipment = target_entity.get("equipment")
        if not equipment or not equipment.armor:
            return damage

        armor = equipment.armor
        armor_value_to_apply = 0
        if hasattr(armor, 'armor_value') and armor.armor_value > 0:
            if self.weapon.damage_type == "superficial":
                armor_value_to_apply = armor.armor_value
            elif self.weapon.damage_type == "aggravated" and hasattr(armor, 'aggravated_soak') and armor.aggravated_soak > 0:
                armor_value_to_apply = armor.aggravated_soak

        if armor_value_to_apply > 0:
            reduced_damage = max(0, damage - armor_value_to_apply)
            print(f"[Damage] Armor ({armor.name}, value {armor_value_to_apply}) reduces damage from {damage} to {reduced_damage}.")
            return reduced_damage
        return damage

    def _apply_range_penalty(self, dice_pool: int, distance: float) -> int:
        """
        Apply dice pool penalties based on attack range.

        Args:
            dice_pool: The current dice pool.
            distance: The distance to the target.

        Returns:
            int: Dice pool size after range adjustments.
        """
        if distance > self.weapon.weapon_range:
            range_increments = floor((distance - 0.01) / self.weapon.weapon_range)
            if range_increments > 0:
                penalty_multiplier = 0.5 ** range_increments
                new_pool_size = floor(dice_pool * penalty_multiplier)
                print(f"[Attack] Range penalty applied. Distance {distance:.2f} > Normal Range {self.weapon.weapon_range}. "
                      f"Pool {dice_pool} -> {new_pool_size}.")
                return new_pool_size
        return dice_pool

    def _inflict_damage(self, target: Character, damage: int, damage_type: str) -> None:
        """
        Apply damage to the target character and publish damage event.

        Args:
            target: Character receiving damage
            damage: Amount of damage to inflict
            damage_type: Type of damage ("superficial" or "aggravated")

        Side effects:
            - Updates target's health
            - Publishes damage_inflicted event if event_bus exists on game_state

        Note:
            Characters with Fortitude discipline level 2+ can downgrade aggravated damage to superficial
        """
        if damage <= 0:
            return

        actual_damage_type = damage_type
        fortitude_level = target.traits.get("Disciplines", {}).get("Fortitude", 0)
        if damage_type == "aggravated" and fortitude_level >= 2:
            print(f"[Damage] {target.name} has Fortitude {fortitude_level}, attempting to downgrade aggravated damage.")
            actual_damage_type = "superficial"

        if actual_damage_type == "superficial":
            target.take_damage(damage, damage_type="superficial")
        elif actual_damage_type == "aggravated":
            target.take_damage(damage, damage_type="aggravated")
        else:
            target.take_damage(damage, damage_type=actual_damage_type)

        if hasattr(self.game_state, 'event_bus') and self.game_state.event_bus:
            self.game_state.event_bus.publish(
                "damage_inflicted",
                attacker_id=self.attacker_id,
                target_id=self.target_id,
                damage_amount=damage,
                damage_type=actual_damage_type,
                weapon_used=self.weapon.name
            )

    def _handle_unintended_targets_placeholder(self, attacker: Character, target: Character) -> None:
        """
        Placeholder method for handling splash damage or missed attacks that hit unintended targets.

        Args:
            attacker: Character performing the attack
            target: Original intended target of the attack

        Note:
            Currently unimplemented. Could be extended to handle:
            - Area effect weapons
            - Missed attacks hitting nearby entities
            - Environmental damage
        """
        pass


class RegisteredAttackAction(Action):
    """
    Attack action implementation registered with the ActionSystem.

    This class wraps the AttackAction functionality as an Action for integration
    with the game's ActionSystem, allowing attacks to be queued, validated, and
    executed through the standard action pipeline.

    Attributes:
        name (str): Display name of the action
        action_type (ActionType): Category of action (PRIMARY, BONUS, etc)
        keywords (list): Tags used for filtering/categorizing this action
        incompatible_keywords (list): Tags of actions that cannot be used with this one
        per_turn_limit (int, optional): Maximum uses per turn, if any

    Example:
        ```python
        # Register the attack action with the action system
        attack_action = RegisteredAttackAction(
            name="Sword Attack",
            action_type=ActionType.PRIMARY
        )
        action_system.register_action(attack_action)

        # Execute through action system
        action_system.execute_action(
            "player1",
            "Attack",
            target_id="enemy1",
            weapon=player_sword
        )
        ```
    """

    def __init__(self, name="Attack", action_type=ActionType.PRIMARY, keywords=None, incompatible_keywords=None,
                 per_turn_limit=None):
        """
        Initialize attack action and register with action system.

        Args:
            name: Display name of the action
            action_type: Category of action from ActionType enum
            keywords: List of tags for this action
            incompatible_keywords: List of action tags that cannot be used together with this
            per_turn_limit: Maximum number of times this action can be performed per turn
        """
        super().__init__(
            name=name,
            action_type=action_type,
            execute_func=self._execute,
            is_available_func=self._is_available,
            description="Perform an attack with a chosen weapon against a target.",
            keywords=keywords or ["attack"],
            incompatible_keywords=incompatible_keywords or [],
            per_turn_limit=per_turn_limit
        )

    def _is_available(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Check if the attack action is available for the given entity.

        Args:
            entity_id: ID of entity attempting the attack
            game_state: Current game state
            **action_params: Additional parameters including target_id and weapon

        Returns:
            bool: True if action can be performed, False otherwise

        Validation checks:
            - Entity must exist
            - Target must exist
            - Weapon must be provided
            - Weapon must have ammunition if it requires it
        """
        attacker_entity = game_state.get_entity(entity_id)
        if not attacker_entity: return False

        target_id = action_params.get("target_id")
        weapon = action_params.get("weapon")

        if not target_id or not weapon:
            return False

        target_entity = game_state.get_entity(target_id)
        if not target_entity:
            return False

        if hasattr(weapon, 'ammunition') and hasattr(weapon, 'max_ammunition') and weapon.ammunition <= 0:
            return False

        # Check maximum range: ensure target is within weapon.maximum_range
        distance = calculate_distance_between_entities(game_state, entity_id, target_id)
        if distance > weapon.maximum_range:
            return False

        return True

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> int:
        """
        Execute the attack action through the action system.

        Args:
            entity_id: ID of entity performing the attack
            game_state: Current game state
            **action_params: Parameters including target_id and weapon

        Returns:
            int: Damage dealt, or False/0 if attack failed

        Side effects:
            - Creates and executes an AttackAction
            - Publishes action_failed event if attack parameters are invalid
        """
        attacker_id = entity_id
        target_id = action_params.get("target_id")
        weapon_instance = action_params.get("weapon")

        if not target_id or not weapon_instance:
            print(f"[ActionSystem-Attack] Failed: Missing target_id or weapon for attack by {attacker_id}.")
            if hasattr(game_state, 'event_bus') and game_state.event_bus:
                game_state.event_bus.publish("action_failed", entity_id=attacker_id, action_name=self.name,
                                             reason="Missing params")
            return False

        if not hasattr(game_state, 'movement') or game_state.movement is None:
            print(
                f"[ActionSystem-Attack] CRITICAL WARNING: game_state.movement is not set. Defensive dodges in AttackAction will fail.")

        attack_executor = AttackAction(
            attacker_id=attacker_id,
            target_id=target_id,
            weapon=weapon_instance,
            game_state=game_state
        )
        result = attack_executor.execute()
        return result


class AoEAttackAction:
    """
    Represents an area of effect attack action targeting a tile rather than an entity.

    This class handles area attacks that target a location on the map:
    - Calculates dice pool and range from attacker to targeted tile
    - Determines all entities affected by the AoE based on weapon effects
    - Applies appropriate damage to each affected entity

    Attributes:
        attacker_id (str): The ID of the attacking entity.
        target_tile (Tuple[int, int]): The (x, y) coordinates of the targeted tile.
        weapon (Weapon): The weapon used for the attack.
        game_state (Any): The current game state.
        dice_roller (Dice): Dice roller utility for resolving actions.
    """

    def __init__(self, attacker_id: str, target_tile: Tuple[int, int], weapon: Weapon, game_state: Any):
        """
        Initialize a new AoE attack action.

        Args:
            attacker_id: ID of entity performing the attack
            target_tile: (x, y) coordinates of the targeted tile
            weapon: Weapon object used for the attack
            game_state: Current game state containing entity data and systems
        """
        self.attacker_id = attacker_id
        self.target_tile = target_tile
        self.weapon = weapon
        self.game_state = game_state
        self.dice_roller = Dice()

    def _get_distance_point_to_point(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        """Calculate Manhattan distance between two points."""
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

    def get_attack_traits(self, attacker: Character) -> int:
        """Calculate the total attack dice pool from attacker's traits and weapon."""
        attr_path, skill_path = self.weapon.attack_traits
        attr = self._get_nested_trait(attacker.traits, attr_path)
        skill = self._get_nested_trait(attacker.traits, skill_path)
        return attr + skill

    def _get_nested_trait(self, traits: dict, path: str) -> int:
        """
        Traverse a dot-notation path through a nested dictionary to retrieve a trait value.
        """
        keys = path.split('.')
        value = traits
        for key in keys:
            if not isinstance(value, dict):
                return 0
            value = value.get(key, 0)
        if isinstance(value, int):
            return value
        return 0

    def _apply_range_penalty(self, dice_pool: int, distance: float) -> int:
        """Apply dice pool penalties based on distance to the target tile."""
        if distance > self.weapon.weapon_range:
            range_increments = floor((distance - 0.01) / self.weapon.weapon_range)
            if range_increments > 0:
                penalty_multiplier = 0.5 ** range_increments
                new_pool_size = floor(dice_pool * penalty_multiplier)
                print(f"[AoE Attack] Range penalty applied. Distance {distance:.2f} > Normal Range {self.weapon.weapon_range}. "
                      f"Pool {dice_pool} -> {new_pool_size}.")
                return new_pool_size
        return dice_pool

    def _inflict_damage(self, target_id: str, damage: int, damage_type: str) -> None:
        """Apply damage to a target and publish damage event."""
        target_entity = self.game_state.get_entity(target_id)
        if not target_entity:
            return

        target = target_entity.get("character_ref").character
        if not target:
            return

        if damage <= 0:
            return

        actual_damage_type = damage_type
        fortitude_level = target.traits.get("Disciplines", {}).get("Fortitude", 0)
        if damage_type == "aggravated" and fortitude_level >= 2:
            print(f"[AoE Damage] {target.name} has Fortitude {fortitude_level}, downgrading aggravated to superficial.")
            actual_damage_type = "superficial"

        target.take_damage(damage, damage_type=actual_damage_type)

        if hasattr(self.game_state, 'event_bus') and self.game_state.event_bus:
            self.game_state.event_bus.publish(
                "damage_inflicted",
                attacker_id=self.attacker_id,
                target_id=target_id,
                damage_amount=damage,
                damage_type=actual_damage_type,
                weapon_used=self.weapon.name
            )

    def _apply_armor_reduction(self, damage: int, target_id: str) -> int:
        """Apply armor-based damage reduction."""
        target_entity = self.game_state.get_entity(target_id)
        equipment = target_entity.get("equipment")
        if not equipment or not equipment.armor:
            return damage

        armor = equipment.armor
        armor_value_to_apply = 0
        if hasattr(armor, 'armor_value') and armor.armor_value > 0:
            if self.weapon.damage_type == "superficial":
                armor_value_to_apply = armor.armor_value
            elif self.weapon.damage_type == "aggravated" and hasattr(armor, 'aggravated_soak') and armor.aggravated_soak > 0:
                armor_value_to_apply = armor.aggravated_soak

        if armor_value_to_apply > 0:
            reduced_damage = max(0, damage - armor_value_to_apply)
            print(f"[AoE Damage] Armor ({armor.name}, value {armor_value_to_apply}) reduces damage from {damage} to {reduced_damage}.")
            return reduced_damage
        return damage

    def _resolve_attack_on_entity(self, target_id: str, attack_pool_size: int, distance_from_impact: float = 0) -> int:
        """
        Resolve attack effects on a single entity within the AoE.

        Args:
            target_id: Entity ID being affected
            attack_pool_size: Base dice pool for the attack
            distance_from_impact: Distance from impact center (for damage falloff)

        Returns:
            int: Damage dealt to this entity
        """
        attacker_entity = self.game_state.get_entity(self.attacker_id)
        target_entity = self.game_state.get_entity(target_id)

        if not target_entity:
            return 0

        attacker = attacker_entity["character_ref"].character
        target = target_entity["character_ref"].character

        # Apply distance-based damage falloff if this entity isn't at the center
        if distance_from_impact > 0 and hasattr(self.weapon, 'effects'):
            for effect in self.weapon.effects:
                if hasattr(effect, 'decay'):
                    attack_pool_size = floor(attack_pool_size * (effect.decay ** distance_from_impact))
                    break

        # Roll attack dice
        attack_roll_results = self.dice_roller.roll_pool(attack_pool_size, hunger_dice=attacker.hunger)

        current_attack_successes = (
            attack_roll_results["successes"] +
            attack_roll_results["critical_successes"] +
            attack_roll_results["hunger_bestial_successes"]
        )

        print(f"[AoE Attack] {attacker.name} AoE affects {target.name} ({target_id}). "
              f"Pool: {attack_pool_size}, Successes: {current_attack_successes}")

        if current_attack_successes <= 0:
            print(f"[AoE Attack] Failed to affect {target.name}. Not enough successes.")
            return 0

        # Calculate damage (simpler than normal attack - no defense rolls in AoE)
        base_damage = self.weapon.get_damage_bonus() + (current_attack_successes - 1)
        print(f"[AoE Damage] Base damage for {target.name}: {base_damage}")

        # Apply armor reduction
        final_damage = self._apply_armor_reduction(base_damage, target_id)

        if final_damage > 0:
            print(f"[AoE Damage] Inflicting {final_damage} {self.weapon.damage_type} damage to {target.name}.")
            self._inflict_damage(target_id, final_damage, self.weapon.damage_type)
        else:
            print(f"[AoE Damage] Final damage to {target.name} is 0 or less after reductions.")

        return final_damage

    def execute(self) -> Dict[str, int]:
        """
        Execute the AoE attack, affecting all entities in the targeted area.

        Returns:
            Dict[str, int]: Mapping of entity_ids to damage amounts
        """
        attacker_entity = self.game_state.get_entity(self.attacker_id)
        if not attacker_entity:
            print(f"[AoE Attack] Attacker {self.attacker_id} not found.")
            return {}

        attacker_pos = attacker_entity.get("position")
        if not attacker_pos:
            print(f"[AoE Attack] Attacker position not found.")
            return {}

        # Calculate distance from attacker's anchor to target tile
        attacker_pos_tuple = (attacker_pos.x, attacker_pos.y)
        distance_to_target = self._get_distance_point_to_point(attacker_pos_tuple, self.target_tile)

        # Check if the target is within maximum range
        if distance_to_target > self.weapon.maximum_range:
            print(f"[AoE Attack] Failed. Target tile is beyond maximum range ({distance_to_target:.2f} > {self.weapon.maximum_range}).")
            return {}

        # Calculate initial dice pool with range penalty
        attacker = attacker_entity["character_ref"].character
        attack_pool_size = self.get_attack_traits(attacker)
        attack_pool_size = self._apply_range_penalty(attack_pool_size, distance_to_target)

        if attack_pool_size <= 0:
            print(f"[AoE Attack] Failed. Dice pool reduced to {attack_pool_size} after range penalty.")
            return {}

        # Track entities affected and damage dealt
        damage_results = {}

        # Find all entities affected by each effect
        for effect in self.weapon.effects:
            if hasattr(effect, 'get_affected_entities'):
                affected_entities = effect.get_affected_entities(
                    self.game_state,
                    self.target_tile,
                    {"attacker_id": self.attacker_id}
                )

                print(f"[AoE Attack] {self.weapon.name} affects {len(affected_entities)} entities.")

                # Process each affected entity
                for entity_id in affected_entities:
                    # Skip attacker if they're somehow in the AoE
                    if entity_id == self.attacker_id:
                        continue

                    # Get target position
                    target_entity = self.game_state.get_entity(entity_id)
                    if not target_entity or not target_entity.get("position"):
                        continue

                    target_pos = target_entity.get("position")
                    target_pos_tuple = (target_pos.x, target_pos.y)

                    # Calculate distance from impact center (for damage falloff)
                    distance_from_impact = self._get_distance_point_to_point(self.target_tile, target_pos_tuple)

                    # Check line of sight from impact point to target
                    if not self.game_state.los_manager.has_los(self.target_tile, target_pos_tuple):
                        print(f"[AoE Attack] No line of sight to {entity_id} from impact point.")
                        continue

                    # Resolve attack on this entity with potential distance-based falloff
                    damage_dealt = self._resolve_attack_on_entity(
                        entity_id,
                        attack_pool_size,
                        distance_from_impact
                    )

                    damage_results[entity_id] = damage_dealt

        return damage_results

