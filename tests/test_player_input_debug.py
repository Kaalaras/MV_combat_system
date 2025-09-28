"""Debug test for human player input flow"""
from __future__ import annotations
import unittest
from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.player_turn_controller import PlayerTurnController
from interface.input_manager import InputManager
from interface.event_constants import CoreEvents, UIIntents
from core.event_bus import EventBus


class TestPlayerInputDebug(unittest.TestCase):
    """Debug player input step by step"""

    def test_debug_action_flow(self):
        """Debug the action flow step by step"""
        # Create minimal game setup
        player_specs = [EntitySpec(team="Player", weapon_type="club", size=(1,1), pos=(5, 5))]
        game_setup = initialize_game(entity_specs=player_specs, grid_size=15, max_rounds=1, map_dir="battle_maps")
        
        # Mark as player controlled
        player_id = game_setup["all_ids"][0]
        char = game_setup["game_state"].get_entity(player_id)["character_ref"].character
        char.is_ai_controlled = False
        
        event_bus = game_setup["event_bus"]
        
        # Track all events with separate functions for each type
        action_requested_events = []
        select_action_events = []
        select_target_events = []
        end_turn_events = []
        
        def track_action_requested(**kwargs):
            action_requested_events.append(kwargs)
            
        def track_select_action(**kwargs):
            select_action_events.append(kwargs)
            
        def track_select_target(**kwargs):
            select_target_events.append(kwargs)
            
        def track_end_turn(**kwargs):
            end_turn_events.append(kwargs)
        
        # Subscribe to all relevant events
        event_bus.subscribe(CoreEvents.ACTION_REQUESTED, track_action_requested)
        event_bus.subscribe(UIIntents.SELECT_ACTION, track_select_action) 
        event_bus.subscribe(UIIntents.SELECT_TARGET, track_select_target)
        event_bus.subscribe(UIIntents.END_TURN, track_end_turn)
        
        # Create PlayerTurnController
        player_turn_controller = PlayerTurnController(
            event_bus,
            is_player_entity=lambda eid: eid == player_id
        )
        
        # Create InputManager
        input_manager = InputManager(event_bus)
        input_manager.set_active_entity(player_id)
        
        # Begin player turn
        player_turn_controller.begin_player_turn(player_id)
        
        print(f"Events after begin_player_turn:")
        print(f"  ACTION_REQUESTED: {len(action_requested_events)}")
        print(f"  SELECT_ACTION: {len(select_action_events)}")
        print(f"  SELECT_TARGET: {len(select_target_events)}")
        
        # Step 1: Send action selection
        print("\nSending action selection...")
        input_manager.handle_action_hotkey("Standard Move")
        
        print(f"Events after action selection:")
        print(f"  ACTION_REQUESTED: {len(action_requested_events)}")
        print(f"  SELECT_ACTION: {len(select_action_events)}")
        print(f"  SELECT_TARGET: {len(select_target_events)}")
        
        if select_action_events:
            print(f"  SELECT_ACTION event: {select_action_events[-1]}")
        
        # Check pending action
        print(f"Pending action: {player_turn_controller.pending_action}")
        
        # Step 2: Send target selection  
        print("\nSending target selection...")
        input_manager.handle_tile_click(6, 5)
        
        print(f"Events after target selection:")
        print(f"  ACTION_REQUESTED: {len(action_requested_events)}")
        print(f"  SELECT_ACTION: {len(select_action_events)}")
        print(f"  SELECT_TARGET: {len(select_target_events)}")
        
        if select_target_events:
            print(f"  SELECT_TARGET event: {select_target_events[-1]}")
        
        if action_requested_events:
            print(f"  ACTION_REQUESTED event: {action_requested_events[-1]}")
        
        # Verify we got an ACTION_REQUESTED event with target_tile
        self.assertGreater(len(action_requested_events), 0, "No ACTION_REQUESTED events received")
        
        action_request = action_requested_events[-1]
        print(f"Final action request: {action_request}")
        
        # Check if target_tile is in the kwargs
        self.assertIn('target_tile', action_request)
        self.assertEqual(action_request['target_tile'], (6, 5))


if __name__ == '__main__':
    unittest.main()