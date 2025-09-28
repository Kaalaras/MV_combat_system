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
    terrain = TerrainGrid(100, 100)
    game_state.set_terrain(terrain)

    event_bus = EventBus()
    game_state.set_event_bus(event_bus)

    movement_system = MovementSystem()
    game_state.set_movement_system(movement_system)

    # Add an entity
    game_state.add_entity("player1", {
        "position": PositionComponent(10, 10),
        "health": HealthComponent(100)
    })

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
        self.movement_turn_usage: Dict[str, Dict[str, Any]] = {}  # {'distance':int}
        self.condition_system: Any = None  # New: reference to ConditionSystem
        self.cover_system: Any = None  # New: reference to CoverSystem
        self.terrain_effect_system: Any = None  # Reference to TerrainEffectSystem
        self.terrain_version = 0  # increments on wall add/remove
        self.blocker_version = 0  # increments on blocking entity move / cover changes
        self.vision_system: Optional[Any] = None  # Optional: VisionSystem auto-wired on set_terrain
        # Add other global state or system references as needed
        # e.g., self.action_system_ref for quick access if needed by some non-ECS logic

    def add_entity(self, entity_id: str, components: Dict[str, Any]) -> None:
        """
        Add a new entity with associated components to the game state.

        Args:
            entity_id: Unique identifier for the entity
            components: Dictionary of components to associate with the entity

        Returns:
            None

        Example:
            ```python
            # Add a player entity
            game_state.add_entity("player1", {
                "position": PositionComponent(x=10, y=10),
                "health": HealthComponent(max_health=100, current_health=100),
                "inventory": InventoryComponent(items=[])
            })
            ```
        """
        # Validate that the entity ID is unique
        if entity_id in self.entities:
            raise ValueError(f"Entity with ID '{entity_id}' already exists.")

        # Optionally validate components (if there's a schema)
        # For simplicity, we assume components are already properly formed

        # Add the entity and its components to the dictionary
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
            # Remove an entity when it is destroyed
            game_state.remove_entity("ogre1")
            ```
        """
        if entity_id in self.entities:
            del self.entities[entity_id]
        # If the entity had a mapped position in a terrain grid, update that too if needed

    def get_component(self, entity_id: str, component_name: str) -> Optional[Any]:
        """
        Retrieve a specific component from an entity.

        Args:
            entity_id: The unique identifier for the entity
            component_name: The name of the component to retrieve

        Returns:
            The requested component if available, None otherwise

        Example:
            ```python
            # Retrieve the position component of an entity
            position = game_state.get_component("player1", "position")
            if position:
                print(f"Player is at ({position.x}, {position.y})")
            ```
        """
        entity = self.get_entity(entity_id)
        if entity:
            return entity.get(component_name)
        return None

    def set_component(self, entity_id: str, component_name: str, component_value: Any) -> None:
        """
        Set (or replace) a specific component on an entity.

        Args:
            entity_id: The unique identifier for the entity
            component_name: The name of the component to set
            component_value: The new value for the component

        Returns:
            None

        Example:
            ```python
            # Update a health component after taking damage
            health = game_state.get_component("player1", "health")
            if health:
                health.current_health -= 10
                game_state.set_component("player1", "health", health)
            ```
        """
        if entity_id in self.entities:
            self.entities[entity_id][component_name] = component_value

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
        # Auto-wire vision system if missing
        if self.vision_system is None:
            try:
                from core.vision_system import VisionSystem
                self.vision_system = VisionSystem(self, terrain)
            except Exception:
                self.vision_system = None

    def set_event_bus(self, event_bus: Any) -> None:
        """
        Set the event bus for cross-system event handling.

        Args:
            event_bus: The event bus instance

        Returns:
            None

        Example:
            ```python
            # Connect event bus to the game
            game_state.set_event_bus(EventBus())

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

    def set_condition_system(self, condition_system: Any) -> None:
        """
        Set the condition system reference for the game.

        Args:
            condition_system: Condition system instance
        """
        self.condition_system = condition_system

    def set_cover_system(self, cover_system: Any) -> None:
        """
        Set the cover system reference for the game.

        Args:
            cover_system: Cover system instance
        """
        self.cover_system = cover_system

    def set_terrain_effect_system(self, tes: Any) -> None:
        """
        Set the terrain effect system reference for the game.
        """
        self.terrain_effect_system = tes

    def update_teams(self) -> None:
        """
        Rebuild the mapping of teams to entity IDs based on current entity components.

        Returns:
            None
        """
        teams: Dict[str, List[str]] = {}
        for eid, comps in self.entities.items():
            cref = comps.get("character_ref")
            if not cref:
                continue
            char = getattr(cref, 'character', None)
            if not char:
                continue
            tm = getattr(char, 'team', None)
            if tm is not None:
                teams.setdefault(str(tm), []).append(eid)
        self.teams = teams

    def get_entity_size(self, entity_id: str) -> tuple[int, int]:
        """
        Retrieve the width and height of an entity's position (if any).

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

    # Movement tracking --------------------------------------------------
    def reset_movement_usage(self, entity_id: str):
        """Reset per-turn movement tracking for an entity (called at turn start)."""
        self.movement_turn_usage[entity_id] = {"distance": 0}

    def add_movement_steps(self, entity_id: str, steps: int):
        if entity_id not in self.movement_turn_usage:
            self.reset_movement_usage(entity_id)
        self.movement_turn_usage[entity_id]["distance"] += steps

    def get_movement_used(self, entity_id: str) -> int:
        return self.movement_turn_usage.get(entity_id, {}).get("distance", 0)

    # Version bump helpers for LOS / cover caching
    def bump_terrain_version(self):
        self.terrain_version += 1

    def bump_blocker_version(self):
        self.blocker_version += 1

    # Optional helpers to apply lethal/cleanup logic
    def kill_entity(self, entity_id: str, killer_id: Optional[str] = None, cause: str = 'unknown') -> bool:
        ent = self.get_entity(entity_id)
        if not ent:
            return False
        # Mark dead if there's a character; allow missing fields gracefully
        cref = ent.get('character_ref')
        char = getattr(cref, 'character', None) if cref else None
        if char:
            try:
                setattr(char, 'is_dead', True)
                # Max out health aggravated to ensure downstream checks consider entity dead
                if hasattr(char, 'max_health') and hasattr(char, '_health_damage'):
                    char._health_damage['aggravated'] = char.max_health
                    char._health_damage['superficial'] = 0
            except Exception:
                pass
        if hasattr(char, 'max_willpower') and hasattr(char, '_willpower_damage'):
            try:
                # Do not necessarily kill via willpower but ensure consistency if logic checks it
                char._willpower_damage['aggravated'] = max(getattr(char, '_willpower_damage', {}).get('aggravated', 0), 0)
            except Exception:
                pass
        if self.event_bus:
            try:
                self.event_bus.publish('entity_died', entity_id=entity_id, killer_id=killer_id, cause=cause)
            except Exception:
                pass
        return True

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
    
    def get_teams(self) -> Dict[str, List[str]]:
        """
        Get current team mappings.

        Returns:
            Dictionary mapping team identifiers to lists of entity IDs

        Example:
            ```python
            teams = game_state.get_teams()
            for team_id, entity_list in teams.items():
                print(f"Team {team_id} has {len(entity_list)} entities")
            ```
        """
        return self.teams
