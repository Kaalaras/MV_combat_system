"""Enhanced Human Player Test Scenarios
========================================

Comprehensive test suite with varying configurations:
- 1 character per player (AI and human)
- 3 characters per player  
- 10 characters per player
- Different equipment for each character
- Symmetric tests between players
- Manual test suite for validation

This test suite reuses existing input mechanisms to ensure completeness.
"""
from __future__ import annotations
import unittest
from typing import Dict, Any, List, Tuple
import time

from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.player_turn_controller import PlayerTurnController
from interface.input_manager import InputManager
from interface.ui_adapter import UIAdapter
from interface.event_constants import CoreEvents, UIIntents
from core.event_bus import EventBus


class MockInputCollector:
    """Enhanced input collector for complex scenarios"""
    
    def __init__(self, name: str = "Player"):
        self.name = name
        self.inputs = []
        self.current_index = 0
    
    def add_action_sequence(self, action_name: str, target=None, requires_target: bool = True):
        """Add complete action sequence (action + target if needed)"""
        self.inputs.append({
            'type': 'action',
            'action_name': action_name,
            'requires_target': requires_target
        })
        if requires_target and target is not None:
            self.inputs.append({
                'type': 'target', 
                'action_name': action_name,
                'target': target
            })
    
    def add_end_turn(self):
        """Add end turn input"""
        self.inputs.append({'type': 'end_turn'})
    
    def get_next_input(self):
        """Get next input in sequence"""
        if self.current_index < len(self.inputs):
            input_data = self.inputs[self.current_index]
            self.current_index += 1
            return input_data
        return None
    
    def reset(self):
        """Reset input sequence"""
        self.current_index = 0
    
    def has_inputs(self) -> bool:
        """Check if more inputs available"""
        return self.current_index < len(self.inputs)


class AutomatedPlayerController:
    """Controls multiple player entities with pre-defined input sequences"""
    
    def __init__(self, event_bus: EventBus, player_entities: List[str], input_collectors: Dict[str, MockInputCollector]):
        self.event_bus = event_bus
        self.player_entities = set(player_entities)
        self.input_collectors = input_collectors
        self.input_manager = InputManager(event_bus)
        
        # Create player turn controller
        self.player_controller = PlayerTurnController(
            event_bus,
            is_player_entity=lambda eid: eid in self.player_entities
        )
        
        # Subscribe to player turn events
        event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)
        event_bus.subscribe(UIIntents.SELECT_ACTION, self._on_action_selected)
        
        self.current_entity = None
        self.processing_turn = False
    
    def _on_turn_start(self, entity_id: str, **kwargs):
        """Handle turn start for player entities"""
        if entity_id in self.player_entities:
            self.current_entity = entity_id
            self.processing_turn = True
            self._process_turn()
    
    def _process_turn(self):
        """Process automated inputs for current entity"""
        if not self.current_entity:
            return
        
        # Find collector for this entity
        collector = None
        for entity_pattern, coll in self.input_collectors.items():
            if self.current_entity.startswith(entity_pattern) or entity_pattern == "all":
                collector = coll
                break
        
        if not collector:
            # Default end turn if no inputs
            self.input_manager.handle_end_turn()
            return
        
        # Process next input
        input_data = collector.get_next_input()
        if input_data:
            self._execute_input(input_data)
        else:
            # No more inputs, end turn
            self.input_manager.handle_end_turn()
    
    def _execute_input(self, input_data: Dict[str, Any]):
        """Execute a single input"""
        input_type = input_data['type']
        
        if input_type == 'action':
            action_name = input_data['action_name']
            requires_target = input_data.get('requires_target', True)
            self.input_manager.handle_action_hotkey(action_name, requires_target=requires_target)
        
        elif input_type == 'target':
            target = input_data['target']
            if isinstance(target, tuple) and len(target) == 2:
                # Tile target
                self.input_manager.handle_tile_click(target[0], target[1])
            else:
                # Entity target (mock)
                self.input_manager.handle_tile_click(5, 5)  # Default position
        
        elif input_type == 'end_turn':
            self.input_manager.handle_end_turn()
            self.processing_turn = False
    
    def _on_action_selected(self, **kwargs):
        """Continue processing after action selection"""
        if self.processing_turn and self.current_entity:
            # Small delay to allow event processing
            self._process_turn()


def create_equipment_configurations() -> List[Dict[str, str]]:
    """Create diverse equipment configurations for characters"""
    return [
        {"weapon_type": "club", "armor_type": None, "sprite": "human_warrior"},
        {"weapon_type": "pistol", "armor_type": None, "sprite": "human_gunner"},
        {"weapon_type": "rifle", "armor_type": None, "sprite": "human_sniper"},
        {"weapon_type": "fists", "armor_type": None, "sprite": "human_brawler"},
        {"weapon_type": "club", "armor_type": None, "sprite": "vampire_male"},
        {"weapon_type": "pistol", "armor_type": None, "sprite": "vampire_female"},
        {"weapon_type": "rifle", "armor_type": None, "sprite": "policeman"},
        {"weapon_type": "fists", "armor_type": None, "sprite": "human_medic"},
        {"weapon_type": "club", "armor_type": None, "sprite": "human_scout"},
        {"weapon_type": "pistol", "armor_type": None, "sprite": "human_guard"},
    ]


def create_test_scenario(human_chars_per_player: int, ai_chars_per_player: int, 
                        num_human_players: int = 1, num_ai_players: int = 1) -> Dict[str, Any]:
    """Create a balanced test scenario with the specified configuration"""
    equipment_configs = create_equipment_configurations()
    entity_specs = []
    all_player_entities = []
    
    # Create human player entities
    for player_num in range(num_human_players):
        team = f"Human_Team_{player_num + 1}"
        for char_num in range(human_chars_per_player):
            config_idx = (player_num * human_chars_per_player + char_num) % len(equipment_configs)
            config = equipment_configs[config_idx]
            
            # Position characters in different corners
            base_x = 2 + player_num * 4
            base_y = 2 + char_num * 2
            pos = (base_x, base_y)
            
            spec = EntitySpec(
                team=team,
                weapon_type=config["weapon_type"],
                size=(1, 1),
                pos=pos,
                sprite_path=f"assets/sprites/characters/{config['sprite']}.png"
            )
            entity_specs.append(spec)
    
    # Create AI entities with symmetric equipment
    for player_num in range(num_ai_players):
        team = f"AI_Team_{player_num + 1}"
        for char_num in range(ai_chars_per_player):
            # Use same equipment as corresponding human character for symmetry
            config_idx = (player_num * ai_chars_per_player + char_num) % len(equipment_configs)
            config = equipment_configs[config_idx]
            
            # Position on opposite side
            base_x = 12 - player_num * 4
            base_y = 12 - char_num * 2
            pos = (base_x, base_y)
            
            spec = EntitySpec(
                team=team,
                weapon_type=config["weapon_type"],
                size=(1, 1),
                pos=pos,
                sprite_path=f"assets/sprites/characters/{config['sprite']}.png"
            )
            entity_specs.append(spec)
    
    # Initialize game
    game_setup = initialize_game(
        entity_specs=entity_specs,
        grid_size=15,
        max_rounds=10,
        map_dir="battle_maps"
    )
    
    # Mark human player entities
    num_human_entities = num_human_players * human_chars_per_player
    for i in range(num_human_entities):
        entity_id = game_setup["all_ids"][i]
        entity = game_setup["game_state"].get_entity(entity_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            char.is_ai_controlled = False
        all_player_entities.append(entity_id)
    
    game_setup["player_entities"] = all_player_entities
    game_setup["human_entities"] = num_human_entities
    game_setup["ai_entities"] = num_ai_players * ai_chars_per_player
    
    return game_setup


class TestEnhancedHumanPlayerScenarios(unittest.TestCase):
    """Enhanced test scenarios for human player input validation"""
    
    def test_single_character_per_player(self):
        """Test 1 character per player (1 human vs 1 AI)"""
        print("\n=== Testing 1 Character Per Player ===")
        
        game_setup = create_test_scenario(
            human_chars_per_player=1,
            ai_chars_per_player=1,
            num_human_players=1,
            num_ai_players=1
        )
        
        # Create input sequence for human player
        human_inputs = MockInputCollector("Human Player")
        human_inputs.add_action_sequence("Standard Move", target=(6, 6))
        human_inputs.add_action_sequence("Basic Attack", target=(10, 10))
        human_inputs.add_end_turn()
        
        # Set up automated controller
        controller = AutomatedPlayerController(
            game_setup["event_bus"],
            game_setup["player_entities"],
            {"Human": human_inputs}
        )
        
        # Run a few turns
        game_system = game_setup["game_system"]
        game_system.run_game_loop(max_rounds=2)
        
        # Verify the game ran successfully
        self.assertGreater(game_setup["game_state"].round_number, 0)
        print(f"✅ Completed {game_setup['game_state'].round_number} rounds")
        print(f"   Human entities: {game_setup['human_entities']}")
        print(f"   AI entities: {game_setup['ai_entities']}")
    
    def test_three_characters_per_player(self):
        """Test 3 characters per player"""
        print("\n=== Testing 3 Characters Per Player ===")
        
        game_setup = create_test_scenario(
            human_chars_per_player=3,
            ai_chars_per_player=3,
            num_human_players=1,
            num_ai_players=1
        )
        
        # Create diverse input sequences
        human_inputs = MockInputCollector("Human Squad")
        
        # Character 1: Aggressive
        human_inputs.add_action_sequence("Standard Move", target=(7, 7))
        human_inputs.add_action_sequence("Basic Attack", target=(8, 8))
        human_inputs.add_end_turn()
        
        # Character 2: Defensive
        human_inputs.add_action_sequence("Standard Move", target=(4, 4))
        human_inputs.add_end_turn()
        
        # Character 3: Mobile
        human_inputs.add_action_sequence("Sprint", target=(9, 5))
        human_inputs.add_end_turn()
        
        controller = AutomatedPlayerController(
            game_setup["event_bus"],
            game_setup["player_entities"],
            {"Human": human_inputs}
        )
        
        game_system = game_setup["game_system"]
        game_system.run_game_loop(max_rounds=2)
        
        self.assertGreater(game_setup["game_state"].round_number, 0)
        self.assertEqual(game_setup["human_entities"], 3)
        self.assertEqual(game_setup["ai_entities"], 3)
        print(f"✅ Squad battle completed: {game_setup['human_entities']} humans vs {game_setup['ai_entities']} AI")
    
    def test_ten_characters_per_player(self):
        """Test 10 characters per player (large battle)"""
        print("\n=== Testing 10 Characters Per Player ===")
        
        game_setup = create_test_scenario(
            human_chars_per_player=10,
            ai_chars_per_player=10,
            num_human_players=1,
            num_ai_players=1
        )
        
        # Create varied input sequences for large army
        human_inputs = MockInputCollector("Human Army")
        
        # Mix of different actions for variety
        actions = ["Standard Move", "Basic Attack", "Sprint"]
        targets = [(6, 6), (7, 7), (8, 8), (5, 9), (9, 5)]
        
        for i in range(10):
            action = actions[i % len(actions)]
            target = targets[i % len(targets)]
            human_inputs.add_action_sequence(action, target=target)
            human_inputs.add_end_turn()
        
        controller = AutomatedPlayerController(
            game_setup["event_bus"],
            game_setup["player_entities"],
            {"Human": human_inputs}
        )
        
        game_system = game_setup["game_system"]
        game_system.run_game_loop(max_rounds=1)  # Just 1 round for large battle
        
        self.assertGreater(game_setup["game_state"].round_number, 0)
        self.assertEqual(game_setup["human_entities"], 10)
        self.assertEqual(game_setup["ai_entities"], 10)
        print(f"✅ Large battle completed: {game_setup['human_entities']} humans vs {game_setup['ai_entities']} AI")
    
    def test_multiple_human_players(self):
        """Test multiple human players with different strategies"""
        print("\n=== Testing Multiple Human Players ===")
        
        game_setup = create_test_scenario(
            human_chars_per_player=2,
            ai_chars_per_player=2,
            num_human_players=2,
            num_ai_players=1
        )
        
        # Different strategies for different players
        player1_inputs = MockInputCollector("Aggressive Player")
        player1_inputs.add_action_sequence("Basic Attack", target=(8, 8))
        player1_inputs.add_end_turn()
        player1_inputs.add_action_sequence("Standard Move", target=(9, 9))
        player1_inputs.add_end_turn()
        
        player2_inputs = MockInputCollector("Tactical Player")
        player2_inputs.add_action_sequence("Standard Move", target=(5, 7))
        player2_inputs.add_end_turn()
        player2_inputs.add_action_sequence("Sprint", target=(7, 5))
        player2_inputs.add_end_turn()
        
        controller = AutomatedPlayerController(
            game_setup["event_bus"],
            game_setup["player_entities"],
            {
                "Human_Team_1": player1_inputs,
                "Human_Team_2": player2_inputs,
                "all": player1_inputs  # Fallback
            }
        )
        
        game_system = game_setup["game_system"]
        game_system.run_game_loop(max_rounds=2)
        
        self.assertGreater(game_setup["game_state"].round_number, 0)
        self.assertEqual(game_setup["human_entities"], 4)  # 2 players * 2 chars
        print(f"✅ Multi-player battle: {game_setup['human_entities']} human entities")


class ManualTestSuite:
    """Interactive test suite for manual validation"""
    
    def __init__(self):
        self.scenarios = [
            ("Single Character Duel", lambda: create_test_scenario(1, 1, 1, 1)),
            ("Squad Combat", lambda: create_test_scenario(3, 3, 1, 1)),
            ("Army Battle", lambda: create_test_scenario(10, 10, 1, 1)),
            ("Multi-Player Scenario", lambda: create_test_scenario(2, 2, 2, 1)),
        ]
    
    def run_interactive_session(self):
        """Run interactive session for manual testing"""
        print("\n" + "="*60)
        print("MANUAL TEST SUITE - HUMAN PLAYER INPUT VALIDATION")
        print("="*60)
        
        for i, (name, scenario_fn) in enumerate(self.scenarios, 1):
            print(f"\n{i}. {name}")
            
            # Create scenario
            game_setup = scenario_fn()
            
            print(f"   - Human entities: {game_setup['human_entities']}")
            print(f"   - AI entities: {game_setup['ai_entities']}")
            print(f"   - Total entities: {len(game_setup['all_ids'])}")
            
            # Show entity positions and equipment
            print(f"   - Entity details:")
            for j, entity_id in enumerate(game_setup["all_ids"][:5]):  # Show first 5
                entity = game_setup["game_state"].get_entity(entity_id)
                if entity and "character_ref" in entity and "position" in entity:
                    char = entity["character_ref"].character
                    pos = entity["position"]
                    weapon = getattr(char, 'weapon', None)
                    weapon_name = weapon.name if weapon else "None"
                    is_human = not getattr(char, 'is_ai_controlled', True)
                    player_type = "HUMAN" if is_human else "AI"
                    print(f"     [{player_type}] {entity_id[:8]}: {weapon_name} at ({pos.x}, {pos.y})")
            
            if len(game_setup["all_ids"]) > 5:
                print(f"     ... and {len(game_setup['all_ids']) - 5} more entities")
            
            print(f"   ✅ Scenario configured successfully")
        
        print(f"\n{'='*60}")
        print("All scenarios configured and ready for manual testing!")
        print("Use demo/combat_ui_demo.py to run these scenarios interactively.")
        print("="*60)


if __name__ == "__main__":
    # Run automated tests
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run manual test suite
    manual_suite = ManualTestSuite()
    manual_suite.run_interactive_session()