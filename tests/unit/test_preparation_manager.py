import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from core.game_state import GameState
from core.preparation_manager import PreparationManager
from ecs.ecs_manager import ECSManager
from ecs.systems.action_system import ActionSystem
from ecs.components.attack_pool_cache import AttackPoolCacheComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.equipment import EquipmentComponent
from entities.default_entities.characters import DefaultHuman
from entities.default_entities.weapons import Fists


class PreparationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ecs_manager = ECSManager()
        self.game_state = GameState(ecs_manager=self.ecs_manager)
        self.prep_manager = PreparationManager(self.game_state)
        self.action_system = ActionSystem(self.game_state)
        self.prep_manager.action_system = self.action_system

        self.character = DefaultHuman()
        self.character_ref = CharacterRefComponent(self.character)
        self.equipment = EquipmentComponent()
        melee_weapon = Fists()
        self.equipment.weapons["melee"] = melee_weapon
        self.equipment.equipped_weapon = melee_weapon

        self.entity_id = "char-1"
        self.game_state.add_entity(
            self.entity_id,
            {
                "character_ref": self.character_ref,
                "equipment": self.equipment,
            },
        )

    def test_prepare_materializes_attack_cache_component(self) -> None:
        self.prep_manager.prepare()

        internal_id = self.ecs_manager.resolve_entity(self.entity_id)
        self.assertIsNotNone(internal_id)
        attack_cache = self.ecs_manager.get_component(internal_id, AttackPoolCacheComponent)
        self.assertIsInstance(attack_cache, AttackPoolCacheComponent)
        self.assertGreater(attack_cache.weapon_pools.get("melee", 0), 0)
        self.assertGreater(attack_cache.defense_pools.get("dodge_close", 0), 0)
        self.assertGreater(attack_cache.defense_pools.get("parry", 0), 0)
        self.assertGreater(attack_cache.defense_pools.get("absorb", 0), 0)
        self.assertGreater(attack_cache.utility_pools.get("jump", 0), 0)
        self.assertIs(
            self.game_state.entities[self.entity_id]["attack_pool_cache"],
            attack_cache,
        )

    def test_initialize_character_actions_registers_via_ecs(self) -> None:
        self.prep_manager.prepare()
        self.prep_manager.initialize_character_actions()

        registered_actions = self.action_system.available_actions.get(self.entity_id, [])
        action_names = {action.name for action in registered_actions}
        self.assertIn("Attack", action_names)

    def test_refresh_entity_dice_pools_updates_existing_cache(self) -> None:
        self.prep_manager.prepare()

        internal_id = self.ecs_manager.resolve_entity(self.entity_id)
        self.assertIsNotNone(internal_id)
        attack_cache = self.ecs_manager.get_component(internal_id, AttackPoolCacheComponent)

        baseline_melee = attack_cache.weapon_pools.get("melee", 0)
        baseline_jump = attack_cache.utility_pools.get("jump", 0)

        self.character.traits["Attributes"]["Physical"]["Dexterity"] = 5
        self.character.traits["Attributes"]["Physical"]["Strength"] = 4

        self.prep_manager.refresh_entity_dice_pools(self.entity_id)

        updated_cache = self.ecs_manager.get_component(internal_id, AttackPoolCacheComponent)
        self.assertIs(attack_cache, updated_cache)
        self.assertGreater(attack_cache.weapon_pools.get("melee", 0), baseline_melee)
        self.assertGreater(attack_cache.utility_pools.get("jump", 0), baseline_jump)


if __name__ == "__main__":
    unittest.main(verbosity=2)
