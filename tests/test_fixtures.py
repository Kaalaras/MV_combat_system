# tests/test_fixtures.py
"""
Shared test fixtures and utilities for AI testing to prevent environment contamination.
"""
import unittest
from unittest.mock import MagicMock, PropertyMock
from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional
import copy

@dataclass
class MockEntitySpec:
    """Specification for a mock entity in tests"""
    team: str
    position: Tuple[int, int]
    weapon_type: str = "ranged"  # "ranged" or "melee"
    health_damage: Tuple[int, int] = (0, 0)  # (superficial, aggravated)
    is_dead: bool = False
    entity_id: Optional[str] = None  # Will be auto-assigned if None

class MockCharacter:
    def __init__(self, team, health_damage=(0, 0), is_dead=False):
        self.team = team
        self.is_ai_controlled = True
        self.ai_script = "basic"
        self._health_damage = {"superficial": health_damage[0], "aggravated": health_damage[1]}
        self.is_dead = is_dead

    def get_alliance(self, other_id):
        # Parse entity ID to determine team affiliation
        other_team = other_id.split('_')[0]
        # Special case for test IDs: check if both are from the same team ("player" or "enemy")
        if "player" in other_id and self.team == "A":
            return "ally"
        if "ally" in other_id and self.team == "A":
            return "ally"
        if "enemy" in other_id and self.team == "B":
            return "ally"

        # Otherwise check first letter of team ID
        return "ally" if other_team == self.team else "enemy"

class MockWeapon:
    def __init__(self, name="Test Weapon", weapon_range=25, ammunition=10):
        self.name = name
        self.weapon_range = weapon_range
        self.ammunition = ammunition

class BaseAITestCase(unittest.TestCase):
    """
    Base test case that provides clean isolation for AI tests.
    Prevents environment contamination between test runs.
    """

    def setUp(self):
        """Set up a completely clean mock environment for each test."""
        # Create fresh mock objects for each test
        self.mock_game_state = MagicMock()
        self.mock_los_manager = MagicMock()
        self.mock_movement_system = MagicMock()
        self.mock_action_system = MagicMock()
        self.mock_event_bus = MagicMock()
        self.mock_turn_order_system = MagicMock()

        # Ensure reserved_tiles is a fresh set for each test
        self.mock_turn_order_system.reserved_tiles = set()

        # Clear any potential module-level caches
        self._clear_module_caches()

        # Initialize default entity specs
        self._setup_default_entities()

        # Setup default mock behaviors
        self._setup_mock_behaviors()

    def tearDown(self):
        """Clean up after each test to prevent contamination."""
        # Clear all mock state
        self.mock_game_state.reset_mock()
        self.mock_los_manager.reset_mock()
        self.mock_movement_system.reset_mock()
        self.mock_action_system.reset_mock()
        self.mock_event_bus.reset_mock()
        self.mock_turn_order_system.reset_mock()

        # Clear reserved tiles explicitly
        if hasattr(self.mock_turn_order_system, 'reserved_tiles'):
            self.mock_turn_order_system.reserved_tiles.clear()

        # Clear any module-level caches again
        self._clear_module_caches()

    def _clear_module_caches(self):
        """Clear any module-level caches that might cause contamination."""
        # Import here to avoid circular imports
        from ecs.systems.ai import utils, targeting, movement

        # Clear any module-level caches if they exist
        for module in [utils, targeting, movement]:
            if hasattr(module, '_cache'):
                module._cache.clear()
            if hasattr(module, 'cache'):
                module.cache.clear()

    def _setup_default_entities(self):
        """Setup default entity configuration."""
        entity_specs = [
            MockEntitySpec(team="player", position=(5, 5), entity_id="player_1"),
            MockEntitySpec(team="player", position=(5, 6), entity_id="ally_1"),
            MockEntitySpec(team="enemy", position=(10, 10), entity_id="enemy_1"),
            MockEntitySpec(team="enemy", position=(15, 15), weapon_type="melee", health_damage=(10, 0), entity_id="enemy_2_damaged"),
            MockEntitySpec(team="enemy", position=(20, 20), entity_id="enemy_3_isolated"),
        ]

        # Create entities from specs
        self.entities = {}
        for spec in entity_specs:
            entity_id = spec.entity_id
            team_prefix = "A" if spec.team == "player" else "B"

            # Create character with appropriate team
            character = MockCharacter(team=team_prefix, health_damage=spec.health_damage, is_dead=spec.is_dead)

            # Create appropriate weapons based on spec
            weapons = {}
            if spec.weapon_type == "ranged":
                weapons["ranged"] = MockWeapon(name="Test Ranged", weapon_range=35)
                weapons["melee"] = MockWeapon(name="Fist", weapon_range=1)
            else:  # melee
                weapons["melee"] = MockWeapon(name="Club", weapon_range=1)

            # Create entity with all needed components
            self.entities[entity_id] = {
                "position": spec.position,
                "character_ref": MagicMock(character=character),
                "equipment": MagicMock(weapons=weapons)
            }

    def _setup_mock_behaviors(self):
        """Setup default mock behaviors."""
        # Configure the mock game_state to return our entities
        def safe_get_entity(eid):
            if eid in self.entities:
                return self.entities[eid]
            # Return a default mock entity for missing entities
            mock_character = MockCharacter(team="B", health_damage=(0, 0), is_dead=True)
            return {
                "position": (0, 0),
                "character_ref": MagicMock(character=mock_character),
                "equipment": MagicMock(weapons={})
            }

        self.mock_game_state.get_entity.side_effect = safe_get_entity
        type(self.mock_game_state).entities = PropertyMock(return_value=self.entities)

        # Set default behavior for line of sight checks
        self.mock_los_manager.has_los.return_value = True

        # Setup default actions
        self._setup_mock_actions()

    def _setup_mock_actions(self):
        """Setup mock actions with clean state."""
        # Create proper mock actions with the required name attribute
        self.mock_attack_action = MagicMock()
        self.mock_attack_action.name = "Attack"

        self.mock_move_action = MagicMock()
        self.mock_move_action.name = "Standard Move"

        self.mock_sprint_action = MagicMock()
        self.mock_sprint_action.name = "Sprint"

        self.mock_end_turn_action = MagicMock()
        self.mock_end_turn_action.name = "End Turn"

        self.mock_reload_action = MagicMock()
        self.mock_reload_action.name = "Reload"

        # Set up the action system to return these mock actions
        self.mock_action_system.available_actions = {
            "player_1": [
                self.mock_attack_action,
                self.mock_move_action,
                self.mock_sprint_action,
                self.mock_end_turn_action,
                self.mock_reload_action
            ]
        }

        # Default can_perform_action behavior
        self.mock_action_system.can_perform_action.return_value = True

    def create_fresh_context(self, char_id):
        """
        Create a completely fresh AITurnContext with isolated state.
        """
        from ecs.systems.ai.main import AITurnContext

        # Create fresh turn order system to avoid contamination
        fresh_turn_order = MagicMock()
        fresh_turn_order.reserved_tiles = set()

        ctx = AITurnContext(
            char_id=char_id,
            game_state=self.mock_game_state,
            los_manager=self.mock_los_manager,
            movement_system=self.mock_movement_system,
            action_system=self.mock_action_system,
            turn_order_system=fresh_turn_order,
            event_bus=self.mock_event_bus
        )

        # Ensure caches are fresh
        ctx.metrics_cache = {}
        ctx.tile_static_cache = {}

        return ctx

    def reset_entity_positions(self):
        """Reset all entity positions to their default values."""
        defaults = {
            "player_1": (5, 5),
            "ally_1": (5, 6),
            "enemy_1": (10, 10),
            "enemy_2_damaged": (15, 15),
            "enemy_3_isolated": (20, 20)
        }

        for entity_id, default_pos in defaults.items():
            if entity_id in self.entities:
                self.entities[entity_id]["position"] = default_pos
