import unittest
from unittest.mock import MagicMock, patch, call
from math import floor

from ecs.actions.attack_actions import AttackAction
from entities.character import Character
from entities.weapon import Weapon, WeaponType
from entities.effects import PenetrationEffect, RadiusAoE, ConeAoE

class MockGameState:
    """A mock GameState to simulate the game world for testing."""
    def __init__(self):
        self.entities = {}
        self.terrain = MagicMock()
        self.terrain.entity_positions = {}
        self.los_manager = MagicMock()
        self.event_bus = MagicMock()
        self.movement = MagicMock()

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def add_entity(self, entity, entity_id, x, y, width=1, height=1, armor=None):
        """Adds a character entity to the mock state."""
        # Mock the armor component if provided
        mock_armor = None
        if armor:
            mock_armor = MagicMock()
            mock_armor.name = armor.get("name", "Test Armor")
            mock_armor.armor_value = armor.get("armor_value", 0)
            mock_armor.aggravated_soak = armor.get("aggravated_soak", 0)

        # Create a mock position with the necessary attributes for bounding box calculations
        mock_position = MagicMock()
        mock_position.x = x
        mock_position.y = y
        mock_position.width = width
        mock_position.height = height
        # Add bounding box attributes for the new logic
        mock_position.x1 = x
        mock_position.y1 = y
        mock_position.x2 = x + width - 1
        mock_position.y2 = y + height - 1

        self.entities[entity_id] = {
            "id": entity_id,
            "character_ref": MagicMock(character=entity),
            "position": mock_position,
            "equipment": MagicMock(armor=mock_armor, weapons={}) # Ensure weapons dict exists
        }
        self.terrain.entity_positions[entity_id] = (x, y)

        # Make get_entity_at return the correct id for the position
        def get_entity_at_side_effect(ex, ey):
            for eid, pos in self.terrain.entity_positions.items():
                if pos == (ex, ey):
                    return eid
            return None
        self.terrain.get_entity_at.side_effect = get_entity_at_side_effect

        # Add get_occupied_tiles for multi-tile compatibility
        def get_occupied_tiles(anchor_tile=None, width=width, height=height):
            # If anchor_tile is provided, use it as the top-left
            x0, y0 = (anchor_tile if anchor_tile is not None else (x, y))
            return [(x0 + dx, y0 + dy) for dx in range(width) for dy in range(height)]
        self.entities[entity_id]["get_occupied_tiles"] = get_occupied_tiles
        self.entities[entity_id]["occupied_tiles"] = get_occupied_tiles()


class TestAttackEffects(unittest.TestCase):
    """Unit tests for Penetration and Area of Effect attack mechanics."""

    def setUp(self):
        """Set up a common environment for all tests."""
        self.game_state = MockGameState()

        # Create common characters
        self.attacker = Character(name="Attacker")
        # Base dice pool of 8 for firearms
        self.attacker.traits = {
            "Attributes": {"Physical": {"Dexterity": 4}},
            "Abilities": {"Skills": {"Firearms": 4}}
        }

        self.target_A = Character(name="TargetA")
        self.target_A.absorption = 2
        self.target_B = Character(name="TargetB")
        self.target_B.absorption = 2
        self.target_C = Character(name="TargetC")
        self.target_C.absorption = 10 # High absorption for one test

        # Add attacker to the game state, targets will be placed per-test
        self.game_state.add_entity(self.attacker, "attacker", 0, 5)

    @patch('ecs.actions.attack_actions.AttackAction._resolve_single_attack')
    def test_penetration_with_max_targets_limit(self, mock_resolve_attack):
        """
        Tests that penetration hits a primary and secondary target but stops
        at the max_penetration limit, even if the dice pool is sufficient.
        """
        # ARRANGE
        # Weapon can hit primary + 1 other target
        weapon = Weapon("Rifle", 4, 20, "aggravated", WeaponType.FIREARM,
                        effects=[PenetrationEffect(max_penetration=1)])

        # Place targets in a line
        self.game_state.add_entity(self.target_A, "target_A", 10, 5)
        self.game_state.add_entity(self.target_B, "target_B", 15, 5)
        self.game_state.add_entity(self.target_C, "target_C", 20, 5)

        # Mock LoS to be clear to all targets
        self.game_state.los_manager.has_los.return_value = True
        # Mock the first attack result: 10 damage, 6 dice remaining (8 pool - 2 absorption)
        mock_resolve_attack.return_value = (10, 6)

        # ACT
        attack_action = AttackAction("attacker", "target_A", weapon, self.game_state)
        attack_action.execute()

        # ASSERT
        # Check that _resolve_single_attack was called for A, then for B, but not for C
        self.assertEqual(mock_resolve_attack.call_count, 2, "Should attack primary and one penetrated target")
        calls = [call("target_A", 8), call("target_B", 6)]
        mock_resolve_attack.assert_has_calls(calls, any_order=False)

    @patch('ecs.actions.attack_actions.AttackAction._resolve_single_attack')
    def test_penetration_blocked_by_terrain_and_stops_on_zero_dice(self, mock_resolve_attack):
        """
        Tests that penetration is stopped by lack of LoS and also when a target's
        absorption reduces the dice pool to zero.
        """
        # ARRANGE
        weapon = Weapon("Cannon", 10, 30, "aggravated", WeaponType.FIREARM,
                        effects=[PenetrationEffect(max_penetration=3)])

        # Target B has high absorption (10)
        self.target_B.absorption = 10

        self.game_state.add_entity(self.target_A, "target_A", 10, 5)
        self.game_state.add_entity(self.target_B, "target_B", 15, 5)
        self.game_state.add_entity(self.target_C, "target_C", 25, 5) # Behind a wall

        # LoS setup: Attacker can see A and B. A wall is between B and C.
        def los_side_effect(pos1, pos2):
            # Unpack potential mock objects
            pos1_tuple = (getattr(pos1, 'x', pos1[0]), getattr(pos1, 'y', pos1[1]))
            pos2_tuple = (getattr(pos2, 'x', pos2[0]), getattr(pos2, 'y', pos2[1]))

            # LoS to C is blocked from the attacker
            if pos2_tuple == (25, 5):
                return False
            return True # Default to clear LoS for all other checks
        self.game_state.los_manager.has_los.side_effect = los_side_effect

        # Mock attack results:
        # 1. Attack on A: returns (damage, remaining_pool = 8 - 2 = 6)
        # 2. Attack on B: returns (damage, remaining_pool = 6 - 10 = -4)
        mock_resolve_attack.side_effect = [(10, 6), (5, -4)]

        # ACT
        attack_action = AttackAction("attacker", "target_A", weapon, self.game_state)
        attack_action.execute()

        # ASSERT
        # Should attack A, then B. Attack on B reduces pool to < 0, so C is not attacked.
        self.assertEqual(mock_resolve_attack.call_count, 2)
        calls = [call("target_A", 8), call("target_B", 6)]
        mock_resolve_attack.assert_has_calls(calls, any_order=False)

    @patch('ecs.actions.attack_actions.AttackAction._resolve_single_attack')
    def test_radius_aoe_with_terrain_occlusion(self, mock_resolve_attack):
        """
        Tests that RadiusAoE hits targets in range with clear LoS from the
        impact point, but not those blocked by cover.
        """
        # ARRANGE
        self.attacker.traits["Abilities"]["Skills"]["Athletics"] = 4  # Grant skill for throwing
        weapon = Weapon("Grenade", 5, 15, "superficial", WeaponType.THROWING,
                        effects=[RadiusAoE(radius=5, decay=0.5)])

        impact_pos = (20, 5)
        self.game_state.add_entity(self.target_A, "target_A", impact_pos[0], impact_pos[1]) # Primary
        self.game_state.add_entity(self.target_B, "target_B", 22, 5) # In radius, clear LoS
        self.game_state.add_entity(self.target_C, "target_C", 20, 8) # In radius, blocked LoS

        # LoS from impact point: B is visible, C is not.
        def los_side_effect(pos1, pos2):
            pos1_tuple = (getattr(pos1, 'x', pos1[0]), getattr(pos1, 'y', pos1[1]))
            pos2_tuple = (getattr(pos2, 'x', pos2[0]), getattr(pos2, 'y', pos2[1]))
            # LoS from impact point to C is blocked
            if pos1_tuple == impact_pos and pos2_tuple == (20, 8):
                return False
            return True # Default to clear LoS for all other checks
        self.game_state.los_manager.has_los.side_effect = los_side_effect
        mock_resolve_attack.return_value = (5, 0) # Primary attack result

        # ACT
        attack_action = AttackAction("attacker", "target_A", weapon, self.game_state)
        attack_action.execute()

        # ASSERT
        # Should attack A (primary), then B (AoE). C is skipped.
        self.assertEqual(mock_resolve_attack.call_count, 2)
        # Check primary attack call (pool of 8, distance 20 > range 15 -> 1 penalty -> pool 4)
        mock_resolve_attack.assert_any_call("target_A", 4)
        # Check AoE attack call on B with decayed pool
        # Distance from (20,5) to (22,5) is 2. Initial pool was 4.
        # Decayed pool = floor(4 * (0.5^2)) = floor(4 * 0.25) = 1
        mock_resolve_attack.assert_any_call("target_B", 1)

    @patch('ecs.actions.attack_actions.AttackAction._resolve_single_attack')
    def test_cone_aoe_boundary_and_directionality(self, mock_resolve_attack):
        """
        Tests that ConeAoE correctly identifies targets within its angle and length
        and aims in the correct direction.
        """
        # ARRANGE
        # Shotgun with a 90-degree cone of 10 units length
        weapon = Weapon("Shotgun", 6, 10, "superficial", WeaponType.FIREARM,
                        effects=[ConeAoE(length=10, angle=90, decay=0.6)])

        # Attacker at (0,5), primary target at (10,5)
        self.game_state.add_entity(self.target_A, "target_A", 10, 5) # Primary
        # B is inside the cone
        self.game_state.add_entity(self.target_B, "target_B", 15, 8)
        # C is outside the cone (too wide an angle)
        self.game_state.add_entity(self.target_C, "target_C", 15, 15)

        self.game_state.los_manager.has_los.return_value = True
        mock_resolve_attack.return_value = (6, 0)

        # ACT
        attack_action = AttackAction("attacker", "target_A", weapon, self.game_state)
        # Adjust decay to be less aggressive to ensure pool is > 0
        weapon.effects[0].decay = 0.8
        attack_action.execute()

        # ASSERT
        # Should attack A (primary) and B (in cone). C is skipped.
        self.assertEqual(mock_resolve_attack.call_count, 2)
        # Pool is 8. Distance 10 <= range 10. No range penalty.
        mock_resolve_attack.assert_any_call("target_A", 8)
        # Distance from impact (10,5) to B (15,8) is sqrt(5^2 + 3^2) = 5.83
        # Initial pool 8. Decay 0.8.
        # Decayed pool = floor(8 * (0.8 ^ 5.83)) = floor(8 * 0.285) = 2
        # The distance is Manhattan now, so sqrt is wrong. dist( (10,5) to (15,8) ) = 5+3=8
        # Decayed pool = floor(8 * (0.8 ^ 8)) = floor(8 * 0.167) = 1
        mock_resolve_attack.assert_any_call("target_B", 1)

    @patch('ecs.actions.attack_actions.AttackAction._resolve_single_attack')
    def test_interaction_of_range_penalty_with_aoe(self, mock_resolve_attack):
        """
        Tests that the dice pool for AoE calculations is the one *after* the
        range penalty has been applied to the primary attack.
        """
        # ARRANGE
        # Weapon range 10, max range 30. Target is at distance 15.
        weapon = Weapon("Grenade Launcher", 5, 10, "superficial", WeaponType.FIREARM,
                        effects=[RadiusAoE(radius=5, decay=0.7)])

        self.game_state.add_entity(self.target_A, "target_A", 15, 5) # Primary
        self.game_state.add_entity(self.target_B, "target_B", 17, 5) # Secondary

        self.game_state.los_manager.has_los.return_value = True
        mock_resolve_attack.return_value = (2, 0)

        # ACT
        attack_action = AttackAction("attacker", "target_A", weapon, self.game_state)
        attack_action.execute()

        # ASSERT
        # Initial pool is 8. Distance is 15, range is 10.
        # This is one range increment beyond normal. Penalty is 0.5.
        # Penalized pool for primary attack = floor(8 * 0.5) = 4.
        mock_resolve_attack.assert_any_call("target_A", 4)

        # AoE on B should be based on the penalized pool of 4.
        # Distance from (15,5) to (17,5) is 2. Decay is 0.7.
        # Decayed pool for B = floor(4 * (0.7 ^ 2)) = floor(4 * 0.49) = 1.
        mock_resolve_attack.assert_any_call("target_B", 1)
        self.assertEqual(mock_resolve_attack.call_count, 2)

    @patch('ecs.actions.attack_actions.AttackAction._resolve_single_attack')
    def test_zero_damage_vs_absorption_in_penetration(self, mock_resolve_attack):
        """
        Tests that a target's absorption reduces the dice pool for subsequent
        penetration attacks, even if the target takes no damage due to armor.
        """
        # ARRANGE
        weapon = Weapon("Piercing Rifle", 2, 20, "aggravated", WeaponType.FIREARM,
                        effects=[PenetrationEffect(max_penetration=2)])

        # Target A has armor that will soak all damage, but still has absorption
        self.target_A.absorption = 3
        self.game_state.add_entity(self.target_A, "target_A", 10, 5, armor={"armor_value": 10})
        self.game_state.add_entity(self.target_B, "target_B", 15, 5)

        self.game_state.los_manager.has_los.return_value = True
        # Mock the attack on A to deal 0 damage, but the remaining pool for penetration
        # should still be reduced by absorption.
        # Pool is 8. Remaining pool = 8 - 3 = 5.
        mock_resolve_attack.return_value = (0, 5)

        # ACT
        attack_action = AttackAction("attacker", "target_A", weapon, self.game_state)
        attack_action.execute()

        # ASSERT
        # Check that the attack on B uses the pool reduced by A's absorption.
        self.assertEqual(mock_resolve_attack.call_count, 2)
        calls = [call("target_A", 8), call("target_B", 5)]
        mock_resolve_attack.assert_has_calls(calls, any_order=False)

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
