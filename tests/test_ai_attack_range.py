import unittest
from MV_combat_system.tests.test_fixtures import BaseAITestCase, MockWeapon
from ecs.systems.ai import targeting

class TestAIAttackRange(BaseAITestCase):
    def test_ranged_attack_within_range(self):
        """Test that AI can attack targets within weapon range."""
        # Set up a ranged weapon with specific range
        weapon = MockWeapon(name="Test Rifle", weapon_range=10)
        self.entities["player_1"]["equipment"].weapons["ranged"] = weapon

        # Position enemy within range
        self.entities["enemy_1"]["position"] = (10, 10)  # 7 tiles away from (5,5)

        # Create context and test
        ctx = self.create_fresh_context("player_1")

        # Mock LOS to return True
        self.mock_los_manager.has_los.return_value = True

        # Test that the enemy is detected as a valid target
        target = targeting.choose_ranged_target(ctx)
        self.assertEqual(target, "enemy_1")

    def test_ranged_attack_out_of_range(self):
        """Test that AI cannot attack targets beyond weapon range."""
        # Set up a ranged weapon with limited range
        weapon = MockWeapon(name="Test Pistol", weapon_range=3)
        self.entities["player_1"]["equipment"].weapons["ranged"] = weapon

        # Position enemy beyond range
        self.entities["enemy_1"]["position"] = (20, 20)  # Far away from (5,5)

        # Create context and test
        ctx = self.create_fresh_context("player_1")

        # Mock LOS to return True (range is the limiting factor)
        self.mock_los_manager.has_los.return_value = True

        # Test that no target is found due to range
        target = targeting.choose_ranged_target(ctx)
        self.assertIsNone(target)

    def test_melee_attack_range(self):
        """Test that AI can only melee attack adjacent enemies."""
        # Position enemy adjacent to player
        self.entities["enemy_1"]["position"] = (5, 4)  # Adjacent to (5,5)

        # Create context and test
        ctx = self.create_fresh_context("player_1")

        # Test that adjacent enemy is detected
        target = targeting.choose_melee_target(ctx)
        self.assertEqual(target, "enemy_1")

    def test_melee_attack_not_adjacent(self):
        """Test that AI cannot melee attack non-adjacent enemies."""
        # Position enemy not adjacent to player
        self.entities["enemy_1"]["position"] = (7, 7)  # Not adjacent to (5,5)

        # Create context and test
        ctx = self.create_fresh_context("player_1")

        # Test that no melee target is found
        target = targeting.choose_melee_target(ctx)
        self.assertIsNone(target)
