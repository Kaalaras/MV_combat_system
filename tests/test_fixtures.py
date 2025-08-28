import unittest
from unittest.mock import MagicMock
from core.game_state import GameState
from core.event_bus import EventBus
from ecs.systems.condition_system import ConditionSystem
from ecs.systems.ai.main import AITurnContext

class EquipmentStub:
    def __init__(self):
        self.weapons = {"ranged": None, "melee": None, "mental": None, "social": None, "special": None}
        self.armor = None

class SimpleChar:
    def __init__(self, entity_id: str, alliances: dict, superficial=0, aggravated=0):
        self.entity_id = entity_id
        self._alliances = alliances  # mapping other_id -> relation string
        self.is_dead = False
        self._health_damage = {'superficial': superficial, 'aggravated': aggravated}
    def get_alliance(self, other_id: str) -> str:
        return self._alliances.get(other_id, 'ally' if other_id.startswith('ally') else ('enemy' if other_id.startswith('enemy') else 'neutral'))

class CharRef:
    def __init__(self, character):
        self.character = character

class MockWeapon:
    def __init__(self, name="Mock Weapon", weapon_range=6, damage_bonus=2, maximum_range=None):
        self.name = name
        self.weapon_range = weapon_range
        self.damage_bonus = damage_bonus
        self.weapon_type = "ranged"
        self.maximum_range = maximum_range if maximum_range is not None else weapon_range

class TerrainStub:
    def __init__(self, width=30, height=30):
        self.width = width
        self.height = height
    def is_walkable(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

class BaseAITestCase(unittest.TestCase):
    def setUp(self):
        # Core systems
        self.game_state = GameState()
        self.event_bus = EventBus()
        self.game_state.set_event_bus(self.event_bus)
        self.condition_system = ConditionSystem(self.game_state)
        self.game_state.set_condition_system(self.condition_system)
        self.game_state.terrain = TerrainStub()

        # Mocks for systems AI expects
        self.mock_game_state = MagicMock(wraps=self.game_state)
        self.mock_movement_system = MagicMock()
        self.mock_action_system = MagicMock()
        self.mock_event_bus = MagicMock()
        self.mock_los_manager = MagicMock()
        # New mock turn order system with reserved_tiles support
        class _MockTurnOrder:
            def __init__(self):
                self.reserved_tiles = set()
            def start_new_round(self):
                # Real implementation may do more; tests only need clearing behavior
                self.reserved_tiles.clear()
        self.mock_turn_order_system = _MockTurnOrder()

        # Provide default movement/occupancy helpers
        self.mock_movement_system.get_reachable_tiles.return_value = [(6,5,1)]
        self.mock_movement_system.is_walkable.return_value = True
        self.mock_game_state.is_tile_occupied = MagicMock(return_value=False)

        # Alliances from player perspective
        player_alliances = {
            'ally_1': 'ally',
            'enemy_1': 'enemy',
            'enemy_2_damaged': 'enemy',
            'enemy_3_isolated': 'enemy'
        }

        # Base entity layout with character_ref
        self.entities = {
            "player_1": {
                "position": (5,5),
                "equipment": EquipmentStub(),
                "character_ref": CharRef(SimpleChar('player_1', player_alliances))
            },
            # Keep enemies near player except the isolated one far away
            "enemy_1": {"position": (8,8), "equipment": EquipmentStub(), "character_ref": CharRef(SimpleChar('enemy_1', {}))},
            # Mark enemy_2_damaged with superficial damage for most-damaged tests
            "enemy_2_damaged": {"position": (9,9), "equipment": EquipmentStub(), "character_ref": CharRef(SimpleChar('enemy_2_damaged', {}, superficial=2))},
            # Place isolated enemy far away so distance remains maximal even after ally repositioning in tests
            "enemy_3_isolated": {"position": (25,25), "equipment": EquipmentStub(), "character_ref": CharRef(SimpleChar('enemy_3_isolated', {}))},
            "ally_1": {"position": (6,6), "equipment": EquipmentStub(), "character_ref": CharRef(SimpleChar('ally_1', {}))},
        }
        # Equip default long-range weapon so distant isolation tests include far enemy
        self.entities["player_1"]["equipment"].weapons["ranged"] = MockWeapon(name="Longbow", weapon_range=50, maximum_range=50)

        # Provide fake actions for AI system
        class FakeAction:
            def __init__(self, name):
                self.name = name
        self.mock_action_system.available_actions = {
            'player_1': [FakeAction('Attack'), FakeAction('Reload'), FakeAction('Standard Move'), FakeAction('Sprint'), FakeAction('End Turn')]
        }
        # Default can_perform_action True unless overridden in specific tests
        self.mock_action_system.can_perform_action.return_value = True

        # Provide get_entity and entities attribute on mock
        def get_entity(eid):
            return self.entities.get(eid)
        self.mock_game_state.get_entity.side_effect = get_entity
        type(self.mock_game_state).entities = unittest.mock.PropertyMock(return_value=self.entities)

    def reset_entity_positions(self):
        """Helper used by some movement simulation tests to restore original layout."""
        self.entities["player_1"]["position"] = (5,5)
        # Align enemy_1 with tests expecting LOS target at (10,10)
        self.entities["enemy_1"]["position"] = (10,10)
        self.entities["enemy_2_damaged"]["position"] = (9,9)
        self.entities["enemy_3_isolated"]["position"] = (25,25)
        self.entities["ally_1"]["position"] = (6,6)

    def create_fresh_context(self, char_id: str) -> AITurnContext:
        return AITurnContext(
            char_id=char_id,
            game_state=self.mock_game_state,
            los_manager = self.mock_los_manager,
            movement_system=self.mock_movement_system,
            action_system=self.mock_action_system,
            turn_order_system=self.mock_turn_order_system,
            event_bus=self.mock_event_bus
        )

class MockCharacter:
    """Lightweight stand-in used by edge case tests when synthesizing missing entities."""
    def __init__(self, team="A", health_damage=(0, 0), is_dead=False):
        self.team = team
        self.is_dead = is_dead
        self._health_damage = {"superficial": health_damage[0], "aggravated": health_damage[1]}

__all__ = ["BaseAITestCase", "MockWeapon", "MockCharacter"]
