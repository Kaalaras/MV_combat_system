import arcade
from core.game_state import GameState
from core.preparation_manager import PreparationManager
from renderer.arcade_renderer import ArcadeRenderer
from entities.character import Character
from entities.default_entities.weapons import Sword, LightPistol
from utils.logger import log_calls

class Game(arcade.Window):
    """
    Main game application class.
    """
    def __init__(self, width: int, height: int, title: str):
        super().__init__(width, height, title)
        self.game_state = None
        self.prep_manager = None
        self.renderer = None
        
        # Set up the game components
        self.setup()
        
    @log_calls
    def setup(self):
        """Set up the game and initialize the game state."""
        # Create game state and terrain
        self.game_state = GameState(20, 15)
        self.prep_manager = PreparationManager(self.game_state)
        
        # Create an arena with scattered obstacles
        self.prep_manager.create_simple_arena(20, 15)
        self.prep_manager.create_obstacle_pattern("scattered")
        
        # Create and place a player character
        player_character = Character(
            name="Player", 
            clan="Brujah", 
            generation=12, 
            archetype="Rebel", 
            sprite_path="assets/sprites/characters/player.png"
        )
        player_id = self.prep_manager.place_character(player_character, 5, 5)
        
        # Create an opponent character
        opponent = Character(
            name="Opponent", 
            clan="Ventrue", 
            generation=11, 
            archetype="Leader", 
            sprite_path="assets/sprites/characters/opponent.png"
        )
        opponent_id = self.prep_manager.place_character(opponent, 15, 10)
        
        # Place some weapons
        sword = Sword()
        self.game_state.add_weapon(sword, 8, 8)
        
        pistol = LightPistol()
        self.game_state.add_weapon(pistol, 12, 3)
        
        # Add some random weapons
        self.prep_manager.place_random_weapons(7)
        
        # Set up renderer
        cell_size = self.game_state.terrain.cell_size
        self.width = self.game_state.terrain.width * cell_size
        self.height = self.game_state.terrain.height * cell_size
        
        # Create the renderer
        self.renderer = ArcadeRenderer(self.game_state, "Combat System")
        
    def on_draw(self):
        """Render the screen."""
        arcade.start_render()
        
        # Draw the grid
        self.renderer.draw_grid()
        
        # Draw all game objects
        terrain = self.game_state.terrain
        
        # Draw walls
        for wall_pos in terrain.walls:
            x, y = wall_pos
            arcade.draw_rectangle_filled(
                (x + 0.5) * terrain.cell_size,
                (y + 0.5) * terrain.cell_size,
                terrain.cell_size * 0.9,
                terrain.cell_size * 0.9,
                arcade.color.DARK_BROWN
            )
        
        # Draw entities
        for entity_id, entity in self.game_state.entities.items():
            pos = terrain.get_entity_position(entity_id)
            if pos:
                x, y = pos
                color = arcade.color.BLUE if isinstance(entity, Character) else arcade.color.RED
                
                arcade.draw_rectangle_filled(
                    (x + 0.5) * terrain.cell_size,
                    (y + 0.5) * terrain.cell_size,
                    terrain.cell_size * 0.7,
                    terrain.cell_size * 0.7,
                    color
                )
                
    def on_update(self, delta_time):
        """Movement and game logic."""
        pass
        
    def on_key_press(self, key, modifiers):
        """Called whenever a key is pressed."""
        pass

def main():
    """Main function to start the game."""
    window = Game(1280, 960, "Combat System - Grid Demo")
    arcade.run()

if __name__ == "__main__":
    main()
