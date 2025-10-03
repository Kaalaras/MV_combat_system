# ecs/actions/aoe_attack_actions.py
from ecs.systems.action_system import Action, ActionType
from entities.weapon import Weapon
from entities.character import Character
from entities.dice import Dice
from typing import Any, Tuple, Optional, List, Dict
from math import floor, sqrt
from interface.event_constants import CoreEvents


class RegisteredAoEAttackAction(Action):
    """
    Area of Effect attack action implementation registered with the ActionSystem.

    This class wraps the AoEAttackAction functionality as an Action for integration
    with the game's ActionSystem, allowing area attacks to be queued, validated, and
    executed through the standard action pipeline.

    Unlike RegisteredAttackAction which targets entities, this targets tiles and affects
    all entities within the weapon's area of effect.

    Attributes:
        name (str): Display name of the action
        action_type (ActionType): Category of action (PRIMARY, BONUS, etc)
        keywords (list): Tags used for filtering/categorizing this action
        incompatible_keywords (list): Tags of actions that cannot be used with this one
        per_turn_limit (int, optional): Maximum uses per turn, if any
    """

    def __init__(self, name="Area Attack", action_type=ActionType.PRIMARY, keywords=None, incompatible_keywords=None,
                 per_turn_limit=None):
        """
        Initialize area attack action and register with action system.

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
            description="Perform an area attack with a chosen weapon targeting a tile.",
            keywords=keywords or ["attack", "area", "aoe"],
            incompatible_keywords=incompatible_keywords or [],
            per_turn_limit=per_turn_limit
        )

    def _is_available(self, entity_id: str, game_state: Any, **action_params) -> bool:
        """
        Check if the area attack action is available for the given entity.

        Args:
            entity_id: ID of entity attempting the attack
            game_state: Current game state
            **action_params: Additional parameters including target_tile and weapon

        Returns:
            bool: True if action can be performed, False otherwise

        Validation checks:
            - Entity must exist
            - Target tile must be provided
            - Weapon must be provided
            - Weapon must have AoE effects
            - Weapon must have ammunition if it requires it
        """
        attacker_entity = game_state.get_entity(entity_id)
        if not attacker_entity:
            return False

        target_tile = action_params.get("target_tile")
        weapon = action_params.get("weapon")

        if not target_tile or not weapon:
            return False

        # Check if the weapon has any AoE effects
        has_aoe_effects = False
        if hasattr(weapon, 'effects'):
            for effect in weapon.effects:
                if hasattr(effect, 'get_affected_entities'):
                    has_aoe_effects = True
                    break

        if not has_aoe_effects:
            return False

        # Check ammunition
        if hasattr(weapon, 'ammunition') and hasattr(weapon, 'max_ammunition') and weapon.ammunition <= 0:
            return False

        return True

    def _execute(self, entity_id: str, game_state: Any, **action_params) -> Dict[str, int]:
        """
        Execute the area attack action through the action system.

        Args:
            entity_id: ID of entity performing the attack
            game_state: Current game state
            **action_params: Parameters including target_tile and weapon

        Returns:
            Dict[str, int]: Mapping of entity IDs to damage dealt, or {} if attack failed

        Side effects:
            - Creates and executes an AoEAttackAction
            - Publishes action_failed event if attack parameters are invalid
        """
        from ecs.actions.attack_actions import AoEAttackAction  # Import here to avoid circular imports

        attacker_id = entity_id
        target_tile = action_params.get("target_tile")
        weapon_instance = action_params.get("weapon")

        if not target_tile or not weapon_instance:
            print(f"[ActionSystem-AoEAttack] Failed: Missing target_tile or weapon for attack by {attacker_id}.")
            if hasattr(game_state, 'event_bus') and game_state.event_bus:
                game_state.event_bus.publish(
                    CoreEvents.ACTION_FAILED,
                    entity_id=attacker_id,
                    action_name=self.name,
                    reason="Missing params",
                )
            return {}

        if not hasattr(game_state, 'los_manager') or game_state.los_manager is None:
            print(f"[ActionSystem-AoEAttack] CRITICAL WARNING: game_state.los_manager is not set. AoE line of sight checks will fail.")

        # Consume ammunition if needed
        if hasattr(weapon_instance, 'ammunition') and not weapon_instance.infinite_ammunition:
            if not weapon_instance.consume_ammunition(1):
                print(f"[ActionSystem-AoEAttack] Failed: Weapon {weapon_instance.name} has no ammunition left.")
                if hasattr(game_state, 'event_bus') and game_state.event_bus:
                    game_state.event_bus.publish(
                        CoreEvents.ACTION_FAILED,
                        entity_id=attacker_id,
                        action_name=self.name,
                        reason="No ammunition",
                    )
                return {}

        attack_executor = AoEAttackAction(
            attacker_id=attacker_id,
            target_tile=target_tile,
            weapon=weapon_instance,
            game_state=game_state
        )
        result = attack_executor.execute()

        # Publish a summary of the AoE attack results
        if hasattr(game_state, 'event_bus') and game_state.event_bus and result:
            total_damage = sum(result.values())
            entities_hit = len(result)
            game_state.event_bus.publish(
                "aoe_attack_summary",
                attacker_id=attacker_id,
                weapon_name=weapon_instance.name,
                target_tile=target_tile,
                entities_hit=entities_hit,
                total_damage=total_damage
            )

        return result
