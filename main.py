from typing import Optional

import arcade

from core.event_bus import EventBus
from core.game_state import GameState
from core.preparation_manager import PreparationManager
from entities.character import Character
from entities.default_entities.weapons import Sword, LightPistol
from renderer.arcade_renderer import ArcadeRenderer
from ecs.ecs_manager import ECSManager
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
        self.ecs_manager: Optional[ECSManager] = None
        self.cell_size = 64
        self.renderer: Optional[ArcadeRenderer] = None
        
        # Set up the game components
        self.setup()
        
    @log_calls
    def setup(self):
        """Set up the game and initialize the game state."""
        # Core state containers
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)
        self.game_state = GameState(ecs_manager=self.ecs_manager)
        self.game_state.set_event_bus(self.event_bus)
        self.prep_manager = PreparationManager(self.game_state)

        # --- Terrain setup ---
        cell_size = 48
        terrain = self.prep_manager.create_grid_terrain(20, 15, cell_size=cell_size)
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

        # Build renderer after the world has been initialized
        self.renderer = ArcadeRenderer(self.game_state, ecs_manager=self.ecs_manager)

        # Resize the window to match the terrain
        self.set_size(terrain.width * self.cell_size, terrain.height * self.cell_size)
        arcade.set_background_color(arcade.color.DARK_SLATE_GRAY)
        
    def on_draw(self):
        """Render the screen."""
        arcade.start_render()
        
        if self.renderer:
            self.renderer.draw()

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
