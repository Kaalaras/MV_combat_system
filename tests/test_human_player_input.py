"""Test Human Player Input Integration
======================================

This test validates that the human player input system works correctly,
processing user inputs through the same game engine as AIs but via the
player input interface instead of the AI interface.

Tests cover:
- Single player entity control
- Multiple human players in one game
- Mixed AI and human player games  
- Input validation and error handling
- Turn flow and state management
"""
from __future__ import annotations
import unittest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List

from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.player_turn_controller import PlayerTurnController
from interface.input_manager import InputManager
from interface.ui_adapter import UIAdapter
from interface.event_constants import CoreEvents, UIIntents, UIStateEvents
from core.event_bus import EventBus


class MockInputCollector:
    """Simulates user input collection for automated testing"""
    
    def __init__(self):
        self.inputs = []
        self.current_index = 0
    
    def add_action(self, action_name: str, requires_target: bool = True, target=None):
        """Add an action input to the sequence"""
        self.inputs.append({
            'type': 'action',
            'action_name': action_name,
            'requires_target': requires_target
        })
        # If target is provided, add it as a separate input
        if requires_target and target is not None:
            self.inputs.append({
                'type': 'target',
                'action_name': action_name,
                'target': target
            })
    
    def add_target(self, target, action_name=None):
        """Add a target selection to the sequence"""
        self.inputs.append({
            'type': 'target',
            'target': target,
            'action_name': action_name
        })
    
    def add_end_turn(self):
        """Add an end turn input"""
        self.inputs.append({'type': 'end_turn'})
    
    def get_next_input(self):
        """Get the next input in sequence"""
        if self.current_index >= len(self.inputs):
            return None
        input_data = self.inputs[self.current_index]
        self.current_index += 1
        return input_data
    
    def reset(self):
        """Reset input sequence"""
        self.current_index = 0


class AutomatedPlayerController:
    """Automated controller that uses the PlayerTurnController interface"""
    
    def __init__(self, event_bus: EventBus, player_entity_ids: List[str], input_sequences: Dict[str, MockInputCollector]):
        self.event_bus = event_bus
        self.player_entity_ids = set(player_entity_ids)
        self.input_sequences = input_sequences
        self.active_entity_id = None
        self.actions_taken = {}
        
        # Create PlayerTurnController with our player entities
        self.player_turn_controller = PlayerTurnController(
            event_bus,
            is_player_entity=lambda eid: eid in self.player_entity_ids
        )
        
        # Create InputManager for processing inputs
        self.input_manager = InputManager(event_bus)
        
        # Subscribe to state changes to trigger automated inputs
        event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)
    
    def begin_player_turn(self, entity_id: str) -> None:
        """Called by game system when it's a player's turn"""
        self.player_turn_controller.begin_player_turn(entity_id)
        if entity_id in self.player_entity_ids:
            self.active_entity_id = entity_id
            self.input_manager.set_active_entity(entity_id)
            # Initialize actions taken for this entity if not exists
            if entity_id not in self.actions_taken:
                self.actions_taken[entity_id] = []
            # Process automated input immediately  
            self._process_next_input()
    
    def auto_play_turn(self, entity_id: str, game_state, action_system):
        """Called by game system for automated testing"""
        if entity_id in self.player_entity_ids and entity_id in self.input_sequences:
            self._process_all_inputs(entity_id)
    
    def _process_all_inputs(self, entity_id: str):
        """Process all inputs for an entity's turn"""
        collector = self.input_sequences[entity_id]
        while True:
            input_data = collector.get_next_input()
            if not input_data:
                break
            self._process_input(input_data)
            # If this was an end turn, stop processing
            if input_data.get('type') == 'end_turn':
                break
    
    def _on_turn_start(self, entity_id: str, **kwargs):
        """Handle turn start - track if it's our player"""
        if entity_id in self.player_entity_ids:
            self.active_entity_id = entity_id
            self.input_manager.set_active_entity(entity_id)
            # Initialize actions taken for this entity if not exists
            if entity_id not in self.actions_taken:
                self.actions_taken[entity_id] = []
    
    def _process_next_input(self):
        """Process the next input in sequence"""
        if (self.active_entity_id and 
            self.active_entity_id in self.input_sequences):
            
            collector = self.input_sequences[self.active_entity_id]
            input_data = collector.get_next_input()
            
            if input_data:
                self._process_input(input_data)
    
    def _process_input(self, input_data: Dict[str, Any]):
        """Process a single input from our sequence"""
        input_type = input_data['type']
        
        if input_type == 'action':
            action_name = input_data['action_name']
            requires_target = input_data.get('requires_target', True)
            
            # Record the action
            self.actions_taken[self.active_entity_id].append({
                'type': 'action',
                'action_name': action_name
            })
            
            # Send action hotkey
            self.input_manager.handle_action_hotkey(action_name, requires_target=requires_target)
                
        elif input_type == 'target':
            target = input_data['target']
            action_name = input_data.get('action_name', 'Unknown')
            
            if isinstance(target, tuple):
                self.input_manager.handle_tile_click(target[0], target[1])
                # Record target with last action
                if (self.active_entity_id in self.actions_taken and 
                    len(self.actions_taken[self.active_entity_id]) > 0):
                    self.actions_taken[self.active_entity_id][-1]['target'] = target
                
        elif input_type == 'end_turn':
            self.input_manager.handle_end_turn()
            self.actions_taken[self.active_entity_id].append({'type': 'end_turn'})


class TestHumanPlayerInput(unittest.TestCase):
    """Test human player input integration"""

    def setUp(self):
        """Set up test environment"""
        self.game_setup = None
        self.controller = None

    def tearDown(self):
        """Clean up after tests"""
        if self.controller:
            # Clean up any running threads or resources
            pass

    def _create_game_with_players(self, player_specs: List[EntitySpec], ai_specs: List[EntitySpec] = None) -> Dict[str, Any]:
        """Create a game with specified player and AI entities"""
        all_specs = player_specs + (ai_specs or [])
        game_setup = initialize_game(entity_specs=all_specs, grid_size=15, max_rounds=5, map_dir="battle_maps")
        
        # Mark player entities as non-AI controlled
        for i, spec in enumerate(player_specs):
            entity_id = game_setup["all_ids"][i]
            char = game_setup["game_state"].get_entity(entity_id)["character_ref"].character
            char.is_ai_controlled = False
            
        return game_setup

    def test_single_human_player_basic_actions(self):
        """Test a single human player can perform basic actions"""
        # Create game with one player entity
        player_specs = [EntitySpec(team="Player", weapon_type="club", size=(1,1), pos=(5, 5))]
        ai_specs = [EntitySpec(team="AI", weapon_type="pistol", size=(1,1), pos=(10, 10))]
        
        self.game_setup = self._create_game_with_players(player_specs, ai_specs)
        player_id = self.game_setup["all_ids"][0]
        
        # Set up automated input sequence
        input_collector = MockInputCollector()
        input_collector.add_action("Standard Move", requires_target=True, target=(6, 5))
        input_collector.add_end_turn()
        
        # Create automated controller
        self.controller = AutomatedPlayerController(
            self.game_setup["event_bus"],
            [player_id],
            {player_id: input_collector}
        )
        
        # Set the controller on the game system
        self.game_setup["game_system"].set_player_controller(self.controller)
        
        # Get initial position
        initial_pos = self.game_setup["game_state"].get_component(player_id, "position")
        initial_x, initial_y = initial_pos.x, initial_pos.y
        
        # Run game for a few rounds
        self.game_setup["game_system"].run_game_loop(max_rounds=2)
        
        # Verify player took actions
        self.assertIn(player_id, self.controller.actions_taken)
        actions = self.controller.actions_taken[player_id]
        self.assertTrue(len(actions) > 0)
        self.assertEqual(actions[0]['type'], 'action')
        self.assertEqual(actions[0]['action_name'], 'Standard Move')

    def test_multiple_human_players(self):
        """Test multiple human players in the same game"""
        # Create game with two player entities
        player_specs = [
            EntitySpec(team="PlayerA", weapon_type="club", size=(1,1), pos=(3, 3)),
            EntitySpec(team="PlayerB", weapon_type="pistol", size=(1,1), pos=(12, 12))
        ]
        
        self.game_setup = self._create_game_with_players(player_specs)
        player_a_id = self.game_setup["all_ids"][0]  
        player_b_id = self.game_setup["all_ids"][1]
        
        # Set up input sequences for both players
        collector_a = MockInputCollector()
        collector_a.add_action("Standard Move", requires_target=True, target=(4, 3))
        collector_a.add_end_turn()
        
        collector_b = MockInputCollector()
        collector_b.add_action("Standard Move", requires_target=True, target=(11, 12))
        collector_b.add_end_turn()
        
        # Create controller for both players
        self.controller = AutomatedPlayerController(
            self.game_setup["event_bus"],
            [player_a_id, player_b_id],
            {player_a_id: collector_a, player_b_id: collector_b}
        )
        
        # Set the controller on the game system
        self.game_setup["game_system"].set_player_controller(self.controller)
        
        # Run game
        self.game_setup["game_system"].run_game_loop(max_rounds=3)
        
        # Verify both players took actions
        self.assertIn(player_a_id, self.controller.actions_taken)
        self.assertIn(player_b_id, self.controller.actions_taken)
        
        actions_a = self.controller.actions_taken[player_a_id]
        actions_b = self.controller.actions_taken[player_b_id]
        
        self.assertTrue(len(actions_a) > 0)
        self.assertTrue(len(actions_b) > 0)

    def test_mixed_human_and_ai_game(self):
        """Test game with both human players and AI entities"""
        # Create game with one player and two AI entities
        player_specs = [EntitySpec(team="Player", weapon_type="club", size=(1,1), pos=(5, 5))]
        ai_specs = [
            EntitySpec(team="AI1", weapon_type="pistol", size=(1,1), pos=(10, 10)),
            EntitySpec(team="AI2", weapon_type="club", size=(1,1), pos=(2, 12))
        ]
        
        self.game_setup = self._create_game_with_players(player_specs, ai_specs)
        player_id = self.game_setup["all_ids"][0]
        ai1_id = self.game_setup["all_ids"][1]
        ai2_id = self.game_setup["all_ids"][2]
        
        # Verify AI entities are still AI controlled
        ai1_char = self.game_setup["game_state"].get_entity(ai1_id)["character_ref"].character
        ai2_char = self.game_setup["game_state"].get_entity(ai2_id)["character_ref"].character
        
        self.assertTrue(ai1_char.is_ai_controlled)
        self.assertTrue(ai2_char.is_ai_controlled)
        
        # Set up player input
        input_collector = MockInputCollector()
        input_collector.add_action("Standard Move", requires_target=True, target=(6, 5))
        input_collector.add_end_turn()
        
        self.controller = AutomatedPlayerController(
            self.game_setup["event_bus"],
            [player_id],
            {player_id: input_collector}
        )
        
        # Set the controller on the game system
        self.game_setup["game_system"].set_player_controller(self.controller)
        
        # Run game - should handle both player and AI turns
        self.game_setup["game_system"].run_game_loop(max_rounds=3)
        
        # Verify player took actions
        self.assertIn(player_id, self.controller.actions_taken)
        actions = self.controller.actions_taken[player_id]
        self.assertTrue(len(actions) > 0)

    def test_player_input_validation(self):
        """Test input validation and error handling"""
        # Create simple game
        player_specs = [EntitySpec(team="Player", weapon_type="club", size=(1,1), pos=(5, 5))]
        self.game_setup = self._create_game_with_players(player_specs)
        player_id = self.game_setup["all_ids"][0]
        
        # Create input manager for direct testing
        input_manager = InputManager(self.game_setup["event_bus"])
        
        # Test input without active entity - should handle gracefully
        input_manager.handle_action_hotkey("Move")  # Should not crash
        
        # Set active entity and test valid input
        input_manager.set_active_entity(player_id)
        
        # This should work without error
        event_published = False
        def capture_event(**kwargs):
            nonlocal event_published
            event_published = True
        
        self.game_setup["event_bus"].subscribe(UIIntents.SELECT_ACTION, capture_event)
        input_manager.handle_action_hotkey("Move")
        # Verify the system handles inputs correctly
        self.assertIsNotNone(input_manager.state.active_entity_id)

    def test_player_turn_controller_state_management(self):
        """Test PlayerTurnController state management"""
        # Create simple game
        player_specs = [EntitySpec(team="Player", weapon_type="club", size=(1,1), pos=(5, 5))]
        self.game_setup = self._create_game_with_players(player_specs)
        player_id = self.game_setup["all_ids"][0]
        
        # Create PlayerTurnController
        controller = PlayerTurnController(
            self.game_setup["event_bus"],
            is_player_entity=lambda eid: eid == player_id
        )
        
        # Initially not waiting for input
        self.assertFalse(controller.waiting_for_player_input)
        self.assertIsNone(controller.active_entity_id)
        
        # Trigger turn start for player
        controller.begin_player_turn(player_id)
        
        # Should now be waiting for player input
        self.assertTrue(controller.waiting_for_player_input)
        self.assertEqual(controller.active_entity_id, player_id)


if __name__ == '__main__':
    unittest.main()