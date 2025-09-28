"""Combat UI Demo Application
============================

Demo application showcasing the new comprehensive combat UI with:
- Visual battlefield with character portraits
- Initiative bar with scrolling
- Resource gauges and action interfaces  
- Character relationship indicators
- Minimap and menu systems

Usage:
    python -m demo.combat_ui_demo --players 2
"""
from __future__ import annotations
import argparse
import sys
from typing import List, Dict, Any

try:
    import arcade
    from interface.combat_ui import create_combat_ui
    from tests.manual.game_initializer import initialize_game, EntitySpec
    ARCADE_AVAILABLE = True
except ImportError as e:
    print(f"Required dependencies not available: {e}")
    ARCADE_AVAILABLE = False


def create_demo_scenario(num_players: int = 1, num_ai: int = 3) -> Dict[str, Any]:
    """Create a demo combat scenario"""
    
    # Create diverse character specs
    player_specs = []
    ai_specs = []
    
    # Player characters with different portraits
    portraits = ["default_human", "default_vampire_male", "default_vampire_female", "default_policeman"]
    weapons = ["club", "pistol"]
    
    for i in range(num_players):
        player_specs.append(
            EntitySpec(
                team=f"Players",  # Same team for cooperative play
                weapon_type=weapons[i % len(weapons)],
                size=(1, 1),
                pos=(2 + i, 2 + i),
                sprite_path=f"assets/sprites/characters/{portraits[i % len(portraits)]}.png"
            )
        )
    
    # AI opponents with different portraits and teams
    ai_teams = ["Enemies", "Neutrals", "Hostiles"]
    for i in range(num_ai):
        ai_specs.append(
            EntitySpec(
                team=ai_teams[i % len(ai_teams)],
                weapon_type=weapons[(i + 1) % len(weapons)],
                size=(1, 1), 
                pos=(12 - i, 12 - i),
                sprite_path=f"assets/sprites/characters/{portraits[(i + 2) % len(portraits)]}.png"
            )
        )
    
    # Initialize the game
    all_specs = player_specs + ai_specs
    game_setup = initialize_game(
        entity_specs=all_specs,
        grid_size=15,
        max_rounds=20,
        map_dir="battle_maps"
    )
    
    # Mark player entities as human-controlled
    for i in range(num_players):
        entity_id = game_setup["all_ids"][i]
        entity = game_setup["game_state"].get_entity(entity_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            char.is_ai_controlled = False
            # Set sprite path for proper portrait loading
            if not hasattr(char, 'sprite_path') or not char.sprite_path:
                char.sprite_path = f"assets/sprites/characters/{portraits[i % len(portraits)]}.png"
    
    return game_setup


class CombatUIDemo:
    """Demo application for the combat UI"""
    
    def __init__(self, num_players: int = 1, num_ai: int = 3):
        if not ARCADE_AVAILABLE:
            raise ImportError("Arcade library is required for the UI demo")
        
        self.num_players = num_players
        self.num_ai = num_ai
        self.game_setup = None
        self.ui = None
        
    def run(self):
        """Run the demo"""
        print(f"Creating combat scenario with {self.num_players} player(s) and {self.num_ai} AI opponents...")
        
        # Create game scenario
        self.game_setup = create_demo_scenario(self.num_players, self.num_ai)
        player_ids = self.game_setup["all_ids"][:self.num_players]
        
        print("Player-controlled entities:", player_ids)
        print("AI-controlled entities:", self.game_setup["all_ids"][self.num_players:])
        
        # Create and configure UI
        self.ui = create_combat_ui(self.game_setup, player_ids)
        
        print("\n" + "="*60)
        print("COMBAT UI DEMO - Controls")
        print("="*60)
        print("Mouse:")
        print("  - Click on grid: Move character / Select target")
        print("  - Click on initiative bar: Scroll through turns")
        print("  - Click on minimap: Center view (planned)")
        print("")
        print("Keyboard:")
        print("  - A: Select attack action")
        print("  - M: Select move action") 
        print("  - E: End turn")
        print("  - ESC: Cancel current action")
        print("")
        print("UI Elements:")
        print("  - Top: Initiative bar (shows turn order)")
        print("  - Left: Player character portraits")
        print("  - Bottom: Main interface with actions and resources")
        print("  - Bottom-left: Minimap with zoom controls")
        print("  - Right: Menu buttons")
        print("")
        print("Character Colors:")
        print("  - Green circle: Your characters")
        print("  - Blue circle: Allied characters") 
        print("  - Yellow circle: Neutral characters")
        print("  - Red circle: Enemy characters")
        print("="*60)
        print("Close the window to exit the demo.")
        
        # Start the UI
        arcade.run()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Combat UI Demo")
    parser.add_argument('--players', type=int, default=1,
                       help='Number of human players (default: 1)')
    parser.add_argument('--ai', type=int, default=3,
                       help='Number of AI opponents (default: 3)')
    
    args = parser.parse_args()
    
    if not ARCADE_AVAILABLE:
        print("ERROR: This demo requires the Arcade library and other dependencies.")
        print("Please ensure all requirements are installed:")
        print("  pip install arcade")
        return 1
    
    try:
        demo = CombatUIDemo(args.players, args.ai)
        demo.run()
        return 0
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())