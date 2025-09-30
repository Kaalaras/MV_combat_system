import arcade
from core.event_bus import EventBus
from core.game_state import GameState
from core.preparation_manager import PreparationManager
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
        self.event_bus = None
        self.cell_size = 64
        
        # Set up the game components
        self.setup()
        
    @log_calls
    def setup(self):
        """Set up the game and initialize the game state."""
        # Core state containers
        self.game_state = GameState()
        self.event_bus = EventBus()
        self.game_state.set_event_bus(self.event_bus)
        self.prep_manager = PreparationManager(self.game_state)

        # --- Terrain setup ---
        terrain = self.prep_manager.create_grid_terrain(20, 15, cell_size=48)
        self.cell_size = terrain.cell_size

        # Keep a few spawn cells clear while scattering cover
        spawn_points = {(5, 5), (15, 10)}
        self.prep_manager.scatter_walls(count=25, avoid=spawn_points, margin=1, seed=7)

        # --- Entity creation ---
        player_character = Character(
            name="Player",
            clan="Brujah",
            generation=12,
            archetype="Rebel",
            sprite_path="assets/sprites/characters/player.png"
        )
        self.prep_manager.spawn_character(
            player_character,
            (5, 5),
            entity_id="player",
            team="coterie",
            weapons={"melee": Sword(), "ranged": LightPistol()},
        )

        opponent = Character(
            name="Opponent",
            clan="Ventrue",
            generation=11,
            archetype="Leader",
            sprite_path="assets/sprites/characters/opponent.png"
        )
        self.prep_manager.spawn_character(
            opponent,
            (15, 10),
            entity_id="opponent",
            team="rivals",
            weapons={"ranged": LightPistol()},
        )

        # Precompute caches (pathfinding, attack pools, etc.)
        self.prep_manager.prepare()

        # Resize the window to match the terrain
        self.set_size(terrain.width * self.cell_size, terrain.height * self.cell_size)
        arcade.set_background_color(arcade.color.DARK_SLATE_GRAY)
        
    def on_draw(self):
        """Render the screen."""
        arcade.start_render()
        
        # Draw the grid
        self._draw_grid()
        
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
        for entity_id, components in self.game_state.entities.items():
            pos = terrain.get_entity_position(entity_id)
            if not pos:
                continue

            char_ref = components.get("character_ref")
            team = getattr(char_ref.character, "team", None) if char_ref else None
            if team == "coterie":
                color = arcade.color.BLUE
            elif team == "rivals":
                color = arcade.color.RED
            else:
                color = arcade.color.LIGHT_GRAY

            arcade.draw_rectangle_filled(
                (pos[0] + 0.5) * terrain.cell_size,
                (pos[1] + 0.5) * terrain.cell_size,
                terrain.cell_size * 0.7,
                terrain.cell_size * 0.7,
                color
            )

    def _draw_grid(self):
        terrain = self.game_state.terrain
        cell = terrain.cell_size
        width_px = terrain.width * cell
        height_px = terrain.height * cell

        # Filled background for clarity
        arcade.draw_lrtb_rectangle_filled(0, width_px, height_px, 0, arcade.color.ASH_GREY)

        # Grid lines
        for x in range(terrain.width + 1):
            px = x * cell
            arcade.draw_line(px, 0, px, height_px, arcade.color.DARK_SLATE_BLUE, 1)
        for y in range(terrain.height + 1):
            py = y * cell
            arcade.draw_line(0, py, width_px, py, arcade.color.DARK_SLATE_BLUE, 1)
                
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
