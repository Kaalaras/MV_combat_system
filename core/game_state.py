# core/game_state.py
from typing import Dict, List, Any, Optional


# (Assuming EventBus and MovementSystem types are imported or defined elsewhere)
# from core.event_bus import EventBus # Example
# from core.movement_system import MovementSystem # Example

class GameState:
    """
    Central state management for a game using an Entity-Component System (ECS) architecture.

    This class maintains the game's entities and their components, terrain information,
    teams, and references to various game systems like event handling and movement.

    Attributes:
        entities: Dictionary mapping entity IDs to their component dictionaries
        terrain: The game's terrain data
        event_bus: Reference to the event management system
        teams: Dictionary mapping team identifiers to lists of entity IDs
        movement: Reference to the movement system

    Example usage:

    ```python
    # Create game state
    game_state = GameState()

    # Initialize systems and set references
    event_bus = EventBus()
    movement_system = MovementSystem()
    terrain = TerrainGrid(width=100, height=100)

    game_state.set_event_bus(event_bus)
    game_state.set_movement_system(movement_system)
    game_state.set_terrain(terrain)

    # Add entities with components
    player_components = {
        "position": Position(x=10, y=20),
        "character_ref": CharacterRef(character=Character(team="blue")),
        "sprite": Sprite(image_path="player.png")
    }
    game_state.add_entity("player1", player_components)

    # Update team assignments based on entity components
    game_state.update_teams()

    # Access entity components
    player_position = game_state.get_component("player1", "position")
    ```
    """

    def __init__(self):
        """
        Initialize an empty game state with no entities or system references.
        """
        self.entities: Dict[str, Dict[str, Any]] = {}  # entity_id -> component dict
        self.terrain: Any = None  # Replace Any with actual Terrain type
        self.event_bus: Optional[Any] = None  # Optional: reference to EventBus, replace Any
        self.teams: Dict[str, List[str]] = {}
        self.movement: Optional[Any] = None  # Optional: reference to MovementSystem, replace Any
        # Add other global state or system references as needed
        # e.g., self.action_system_ref for quick access if needed by some non-ECS logic

    def add_entity(self, entity_id: str, components: Dict[str, Any]) -> None:
        """
        Add a new entity with associated components to the game state.

        Args:
            entity_id: Unique identifier for the entity
            components: Dictionary of component name -> component instance

        Returns:
            None

        Example:
            ```python
            # Create new entity with position and health components
            components = {
                "position": {"x": 10, "y": 20},
                "health": {"current": 100, "max": 100}
            }
            game_state.add_entity("enemy1", components)
            ```
        """
        self.entities[entity_id] = components

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve all components for a specific entity.

        Args:
            entity_id: The unique identifier for the entity

        Returns:
            Dictionary of components if entity exists, None otherwise

        Example:
            ```python
            # Get all components for an entity
            if player := game_state.get_entity("player1"):
                # Entity exists, access its components
                position = player.get("position")
            else:
                # Entity doesn't exist
                print("Player not found")
            ```
        """
        return self.entities.get(entity_id)

    def remove_entity(self, entity_id: str) -> None:
        """
        Remove an entity and all its components from the game state.

        Args:
            entity_id: The unique identifier for the entity to remove

        Returns:
            None

        Example:
            ```python
            # Remove an enemy that has been defeated
            game_state.remove_entity("enemy42")
            ```
        """
        if entity_id in self.entities:
            del self.entities[entity_id]
        # else:
        # print(f"Warning: Entity {entity_id} not found in GameState during remove.")

    def get_teams(self) -> Dict[str, List[str]]:
        """
        Get the current team assignments.

        Returns:
            Dictionary mapping team identifiers to lists of entity IDs

        Example:
            ```python
            # Check which entities belong to each team
            teams = game_state.get_teams()
            blue_team_entities = teams.get("blue", [])
            red_team_entities = teams.get("red", [])
            ```
        """
        return self.teams

    def update_teams(self) -> None:
        """
        Update team assignments based on current entity character components.

        This method reads the team attribute from each entity's character_ref component
        and updates the teams dictionary accordingly.

        Returns:
            None

        Example:
            ```python
            # After adding/removing entities or changing team affiliations
            game_state.update_teams()

            # Now the teams collections are up-to-date
            red_team = game_state.teams.get("red", [])
            ```
        """
        teams: Dict[str, List[str]] = {}
        for entity_id, entity_components in self.entities.items():
            # Assuming 'character_ref' component holds a Character object with a 'team' attribute
            char_ref_comp = entity_components.get("character_ref")
            if char_ref_comp:
                character = getattr(char_ref_comp, "character", None)
                if character:
                    team = getattr(character, "team", None)
                    if team is not None:
                        teams.setdefault(str(team), []).append(entity_id)
        self.teams = teams

    def set_terrain(self, terrain: Any) -> None:
        """
        Set the terrain instance for the game.

        Args:
            terrain: Terrain data structure (grid, map, etc.)

        Returns:
            None

        Example:
            ```python
            # Create and set terrain
            terrain = TerrainGrid(100, 100)
            terrain.load_from_file("desert_map.json")
            game_state.set_terrain(terrain)
            ```
        """
        self.terrain = terrain

    def set_event_bus(self, event_bus: Any) -> None:
        """
        Set the event bus system reference for the game.

        Args:
            event_bus: Event bus instance for handling game events

        Returns:
            None

        Example:
            ```python
            # Create and set event bus
            event_bus = EventBus()
            game_state.set_event_bus(event_bus)

            # Now systems can access the event bus through game state
            # game_systems.combat.handle_combat(entity1, entity2, game_state.event_bus)
            ```
        """
        self.event_bus = event_bus

    def set_movement_system(self, movement_system: Any) -> None:
        """
        Set the movement system reference for the game.

        Args:
            movement_system: Movement system instance for handling entity movement

        Returns:
            None

        Example:
            ```python
            # Create and set movement system
            movement_system = MovementSystem()
            game_state.set_movement_system(movement_system)

            # Later, other systems can use this reference
            # destination = (10, 20)
            # game_state.movement.move_entity("player1", destination)
            ```
        """
        self.movement = movement_system

    def get_component(self, entity_id: str, component_name: str) -> Optional[Any]:
        """
        Get a specific component for an entity.

        Args:
            entity_id: The unique identifier for the entity
            component_name: Name of the component to retrieve

        Returns:
            The component if it exists for the entity, None otherwise

        Example:
            ```python
            # Get the position component of an entity
            position = game_state.get_component("player1", "position")
            if position:
                player_x, player_y = position.x, position.y
            else:
                print("Player has no position component")
            ```
        """
        entity = self.get_entity(entity_id)
        if entity:
            return entity.get(component_name)
        return None

    def get_entity_size(self, entity_id: str) -> tuple[int, int]:
        """
        Get the width and height of an entity's footprint.

        Args:
            entity_id: The unique identifier for the entity

        Returns:
            Tuple (width, height) representing the entity's size in grid cells, default (1, 1)

        Example:
            ```python
            # Get entity size for pathfinding or collision detection
            entity_width, entity_height = game_state.get_entity_size("ogre1")
            print(f"Ogre size: {entity_width}x{entity_height} cells")
            ```
        """
        entity = self.get_entity(entity_id)
        if entity and "position" in entity:
            pos_comp = entity["position"]
            return getattr(pos_comp, 'width', 1), getattr(pos_comp, 'height', 1)
        return 1, 1  # Default size if entity doesn't exist or has no position

    # ------------------------------------------------------------------
    # Convenience helpers (used by AI and other high-level systems)
    # ------------------------------------------------------------------
    def is_tile_occupied(self, x: int, y: int) -> bool:
        """Return True if a single grid cell is occupied by an entity.
        Thin wrapper over terrain.is_occupied for clarity / decoupling.
        Walls are handled separately via movement/terrain walkability checks."""
        terrain = getattr(self, 'terrain', None)
        if not terrain:
            return False
        # check_walls False: we only care about entity bodies here
        return terrain.is_occupied(x, y, 1, 1, check_walls=False)
    # ------------------------------------------------------------------
