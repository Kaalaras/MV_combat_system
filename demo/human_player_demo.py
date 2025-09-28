"""Human Player Input Demonstration
====================================

This module demonstrates how to integrate human players into the combat system
using different input methods, including Arcade-based GUI input and console input.

The system supports:
- Multiple human players in the same game
- Mixed human and AI players  
- Non-blocking input processing
- Integration with existing game systems

Usage:
    # Console-based demo (uses existing manual test)
    python -m demo.human_player_demo console --players 2
    
    # Arcade-based demo (requires arcade library)
    python -m demo.human_player_demo arcade --players 1
"""
from __future__ import annotations
import argparse
import sys
from typing import List, Dict, Any

# Console demo imports
from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.player_turn_controller import PlayerTurnController  
from interface.input_manager import InputManager
from tests.test_human_player_input import MockInputCollector, AutomatedPlayerController

# Optional arcade imports
try:
    import arcade
    ARCADE_AVAILABLE = True
except ImportError:
    ARCADE_AVAILABLE = False
    arcade = None


def create_demo_game(num_players: int, num_ai: int = 2) -> Dict[str, Any]:
    """Create a demo game with specified number of human players and AI"""
    
    # Create player specs
    player_specs = []
    ai_specs = []
    
    # Add human players
    for i in range(num_players):
        player_specs.append(
            EntitySpec(
                team=f"Player{i+1}", 
                weapon_type="club" if i % 2 == 0 else "pistol",
                size=(1,1), 
                pos=(2 + i*2, 2 + i*2)
            )
        )
    
    # Add AI players
    for i in range(num_ai):
        ai_specs.append(
            EntitySpec(
                team=f"AI{i+1}",
                weapon_type="pistol" if i % 2 == 0 else "club", 
                size=(1,1),
                pos=(12 - i*2, 12 - i*2)
            )
        )
    
    # Initialize game
    all_specs = player_specs + ai_specs
    game_setup = initialize_game(
        entity_specs=all_specs,
        grid_size=15,
        max_rounds=10,
        map_dir="battle_maps"
    )
    
    # Mark first N entities as player-controlled
    for i in range(num_players):
        entity_id = game_setup["all_ids"][i]
        char = game_setup["game_state"].get_entity(entity_id)["character_ref"].character
        char.is_ai_controlled = False
        
    return game_setup


def demo_console_players(num_players: int):
    """Demonstrate console-based human player input with automated sequences"""
    
    print(f"Starting console demo with {num_players} human player(s)")
    
    # Create game
    game_setup = create_demo_game(num_players, num_ai=2)
    player_ids = game_setup["all_ids"][:num_players]
    
    print(f"Player-controlled entities: {player_ids}")
    print(f"AI-controlled entities: {game_setup['all_ids'][num_players:]}")
    
    # Create automated input sequences for demo
    input_sequences = {}
    for i, player_id in enumerate(player_ids):
        collector = MockInputCollector()
        
        # Different strategies for different players
        if i % 2 == 0:
            # Player moves forward, then attacks
            collector.add_action("Standard Move", requires_target=True, target=(6 + i, 5 + i))
            collector.add_action("Standard Move", requires_target=True, target=(7 + i, 6 + i))
            collector.add_end_turn()
        else:
            # Player moves defensively
            collector.add_action("Standard Move", requires_target=True, target=(3 - i, 3 - i))  
            collector.add_end_turn()
        
        input_sequences[player_id] = collector
    
    # Create automated controller
    controller = AutomatedPlayerController(
        game_setup["event_bus"],
        player_ids,
        input_sequences
    )
    
    # Set controller on game system
    game_setup["game_system"].set_player_controller(controller)
    
    print("\n" + "="*50)
    print("GAME START - Human Players Using Automated Input")
    print("="*50)
    
    # Run game
    game_setup["game_system"].run_game_loop(max_rounds=5)
    
    print("\n" + "="*50)
    print("GAME END - Human Player Actions Summary:")
    print("="*50)
    
    # Show actions taken by each player
    for player_id in player_ids:
        if player_id in controller.actions_taken:
            actions = controller.actions_taken[player_id]
            print(f"\n{player_id} actions:")
            for action in actions:
                action_name = action.get('action_name', action.get('type'))
                target = action.get('target', '')
                target_str = f" -> {target}" if target else ""
                print(f"  - {action_name}{target_str}")
        else:
            print(f"\n{player_id}: No actions taken")


class ArcadePlayerDemo(arcade.Window):
    """Arcade-based human player demonstration"""
    
    def __init__(self, game_setup: Dict[str, Any], player_ids: List[str]):
        super().__init__(800, 600, "Human Player Combat Demo")
        
        self.game_setup = game_setup
        self.player_ids = player_ids
        self.current_player_index = 0
        
        # Create input manager and player controller
        self.input_manager = InputManager(game_setup["event_bus"])
        self.player_turn_controller = PlayerTurnController(
            game_setup["event_bus"],
            is_player_entity=lambda eid: eid in player_ids
        )
        
        # Set up game system with our controller
        self.player_turn_controller.begin_player_turn = self._on_player_turn_start
        game_setup["game_system"].set_player_controller(self.player_turn_controller)
        
        # Game state
        self.game_running = False
        self.current_turn_entity = None
        self.selected_action = None
        self.instructions = [
            "Click on map to move",
            "Press 'A' to attack", 
            "Press 'E' to end turn",
            "Press 'S' to start game"
        ]
        
        # Visual elements
        self.cell_size = 30
        self.offset_x = 50
        self.offset_y = 50
        
    def _on_player_turn_start(self, entity_id: str):
        """Handle player turn start"""
        if entity_id in self.player_ids:
            self.current_turn_entity = entity_id
            self.input_manager.set_active_entity(entity_id)
            print(f"Player {entity_id} turn started")
    
    def on_draw(self):
        """Render the game state"""
        self.clear()
        
        # Draw grid
        for x in range(15):
            for y in range(15):
                screen_x = self.offset_x + x * self.cell_size
                screen_y = self.offset_y + y * self.cell_size
                
                # Grid lines
                arcade.draw_rectangle_outline(
                    screen_x + self.cell_size//2,
                    screen_y + self.cell_size//2, 
                    self.cell_size, self.cell_size,
                    arcade.color.GRAY
                )
        
        # Draw entities
        game_state = self.game_setup["game_state"]
        for entity_id in self.game_setup["all_ids"]:
            entity = game_state.get_entity(entity_id)
            if entity and "position" in entity:
                pos = entity["position"]
                screen_x = self.offset_x + pos.x * self.cell_size + self.cell_size//2
                screen_y = self.offset_y + pos.y * self.cell_size + self.cell_size//2
                
                # Different colors for players vs AI
                if entity_id in self.player_ids:
                    color = arcade.color.BLUE if entity_id == self.current_turn_entity else arcade.color.LIGHT_BLUE
                else:
                    color = arcade.color.RED
                    
                arcade.draw_circle_filled(screen_x, screen_y, self.cell_size//3, color)
                
                # Entity label
                arcade.draw_text(entity_id.split("_")[0], screen_x-10, screen_y-5, 
                               arcade.color.WHITE, 10)
        
        # Draw UI
        y_offset = 500
        for i, instruction in enumerate(self.instructions):
            arcade.draw_text(instruction, 10, y_offset - i*20, arcade.color.WHITE, 14)
        
        # Current turn info
        if self.current_turn_entity:
            arcade.draw_text(f"Current Turn: {self.current_turn_entity}", 
                           10, 450, arcade.color.YELLOW, 16)
    
    def on_key_press(self, key, modifiers):
        """Handle keyboard input"""
        if key == arcade.key.S:
            # Start game
            if not self.game_running:
                self.game_running = True
                # Run game in background thread would be ideal, but for demo keep simple
                print("Game started! Click to interact.")
        
        elif key == arcade.key.A and self.current_turn_entity:
            # Select attack action
            self.selected_action = "Basic Attack"
            self.input_manager.handle_action_hotkey("Basic Attack")
            
        elif key == arcade.key.E and self.current_turn_entity:
            # End turn
            self.input_manager.handle_end_turn()
            
    def on_mouse_press(self, x, y, button, modifiers):
        """Handle mouse input"""
        if not self.current_turn_entity:
            return
            
        # Convert screen coordinates to grid coordinates
        grid_x = int((x - self.offset_x) // self.cell_size)
        grid_y = int((y - self.offset_y) // self.cell_size) 
        
        if 0 <= grid_x < 15 and 0 <= grid_y < 15:
            if self.selected_action:
                # Target selection
                self.input_manager.handle_tile_click(grid_x, grid_y)
                self.selected_action = None
            else:
                # Movement
                self.input_manager.handle_action_hotkey("Standard Move")
                self.input_manager.handle_tile_click(grid_x, grid_y)


def demo_arcade_players(num_players: int):
    """Demonstrate Arcade-based human player input"""
    
    if not ARCADE_AVAILABLE:
        print("ERROR: Arcade library not available. Install with: pip install arcade")
        return
        
    print(f"Starting Arcade demo with {num_players} human player(s)")
    
    # Create game
    game_setup = create_demo_game(num_players, num_ai=1)
    player_ids = game_setup["all_ids"][:num_players]
    
    print("Instructions:")
    print("- Click on the map to move your character")
    print("- Press 'A' to select attack, then click target")
    print("- Press 'E' to end your turn")
    print("- Press 'S' to start the game")
    print("\nClose window when done.")
    
    # Create and run Arcade window
    window = ArcadePlayerDemo(game_setup, player_ids)
    arcade.run()


def main():
    """Main entry point for the human player demonstration"""
    
    parser = argparse.ArgumentParser(description="Human Player Input Demonstration")
    parser.add_argument('mode', choices=['console', 'arcade'], 
                       help='Demo mode: console (automated) or arcade (interactive)')
    parser.add_argument('--players', type=int, default=1,
                       help='Number of human players (default: 1)')
    
    args = parser.parse_args()
    
    if args.mode == 'console':
        demo_console_players(args.players)
    elif args.mode == 'arcade':
        demo_arcade_players(args.players)


if __name__ == '__main__':
    main()