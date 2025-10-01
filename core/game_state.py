# core/game_state.py
import logging
from typing import Dict, List, Any, Optional

from ecs.components.entity_id import EntityIdComponent
from ecs.components.initiative import InitiativeComponent
from ecs.components.movement_usage import MovementUsageComponent
from ecs.components.team import TeamComponent


# (Assuming EventBus and MovementSystem types are imported or defined elsewhere)
# from core.event_bus import EventBus # Example
# from core.movement_system import MovementSystem # Example

logger = logging.getLogger(__name__)


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
    from ecs.ecs_manager import ECSManager

    # Create game state and ECS manager
    ecs_manager = ECSManager()
    game_state = GameState(ecs_manager=ecs_manager)

    # Initialize systems and set references
    terrain = TerrainGrid(100, 100)
    game_state.set_terrain(terrain)

    event_bus = EventBus()
    game_state.set_event_bus(event_bus)

    movement_system = MovementSystem(game_state, ecs_manager, event_bus=event_bus)
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

    def __init__(self, ecs_manager: Optional[Any] = None):
        """
        Initialize an empty game state with no entities or system references.
        """
        self.entities: Dict[str, Dict[str, Any]] = {}  # entity_id -> component dict
        self.terrain: Any = None  # Replace Any with actual Terrain type
        self._event_bus: Optional[Any] = None  # Optional: reference to EventBus, replace Any
        self.teams: Dict[str, List[str]] = {}
        self.movement: Optional[Any] = None  # Optional: reference to MovementSystem, replace Any
        self.movement_turn_usage: Dict[str, Dict[str, Any]] = {}  # {'distance':int}
        self.condition_system: Any = None  # New: reference to ConditionSystem
        self.cover_system: Any = None  # New: reference to CoverSystem
        self.terrain_effect_system: Any = None  # Reference to TerrainEffectSystem
        self.terrain_version = 0  # increments on wall add/remove
        self.blocker_version = 0  # increments on blocking entity move / cover changes
        self.vision_system: Optional[Any] = None  # Optional: VisionSystem auto-wired on set_terrain
        self.ecs_manager: Optional[Any] = ecs_manager
        self._ecs_entities: Dict[str, int] = {}
        self._movement_event_registered = False
        self._movement_subscription_bus: Optional[Any] = None
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

        # Ensure initiative data is mirrored into ECS when characters are present
        if "character_ref" in components and "initiative" not in components:
            components["initiative"] = InitiativeComponent()

        # Add the entity and its components to the dictionary
        self.entities[entity_id] = components

        if self.ecs_manager:
            try:
                internal_id = self._mirror_entity(entity_id, components)
                self._ecs_entities[entity_id] = internal_id
            except (TypeError, ValueError) as exc:
                # Ensure partial failures do not leave stale references
                self.entities.pop(entity_id, None)
                self._cleanup_partial_ecs_entity(entity_id)
                logger.error(
                    "Failed to create ECS entity for %s: %s",
                    entity_id,
                    exc,
                )
                raise

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
        internal_id = self._ecs_entities.pop(entity_id, None)
        if self.ecs_manager and internal_id is not None:
            try:
                self.ecs_manager.delete_entity(internal_id)
            except KeyError as exc:
                logger.warning(
                    "Failed to delete ECS entity %s for %s: %s",
                    internal_id,
                    entity_id,
                    exc,
                )
                raise
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
        previous_bus = self._movement_subscription_bus if self._movement_event_registered else None
        if previous_bus and previous_bus is not event_bus and hasattr(previous_bus, "unsubscribe"):
            for event_name, handler in (
                ("movement_reset_requested", self._handle_movement_reset_requested),
                ("movement_distance_spent", self._handle_movement_distance_spent),
            ):
                try:
                    previous_bus.unsubscribe(event_name, handler)
                except (AttributeError, KeyError, ValueError) as exc:  # pragma: no cover - defensive cleanup
                    logger.warning(
                        "Failed to unsubscribe %s handler from previous bus: %s",
                        event_name,
                        exc,
                    )
        if previous_bus and previous_bus is not event_bus:
            self._movement_event_registered = False
            self._movement_subscription_bus = None

        self._event_bus = event_bus

        subscribe = getattr(self._event_bus, "subscribe", None)
        if callable(subscribe) and not self._movement_event_registered:
            subscribe(
                "movement_reset_requested",
                self._handle_movement_reset_requested,
            )
            subscribe(
                "movement_distance_spent",
                self._handle_movement_distance_spent,
            )
            self._movement_subscription_bus = self._event_bus
            self._movement_event_registered = True

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

    @property
    def event_bus(self) -> Optional[Any]:
        return self._event_bus

    @event_bus.setter
    def event_bus(self, event_bus: Optional[Any]) -> None:
        self.set_event_bus(event_bus)

    def set_ecs_manager(self, ecs_manager: Any) -> None:
        """Attach an ``ecs_manager`` and mirror existing entities into the ECS world."""

        if ecs_manager is self.ecs_manager:
            return
        self.ecs_manager = ecs_manager
        self._ecs_entities.clear()
        if not self.ecs_manager:
            return
        for entity_id, components in self.entities.items():
            try:
                internal_id = self._mirror_entity(entity_id, components)
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Failed to mirror entity %s into ECS: %s",
                    entity_id,
                    exc,
                )
                continue
            self._ecs_entities[entity_id] = internal_id

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
        if self.ecs_manager:
            teams: Dict[str, List[str]] = {}
            for entity_id, team_component in self.ecs_manager.iter_with_id(TeamComponent):
                team_id = getattr(team_component, "team_id", None)
                if team_id in (None, ""):
                    continue
                teams.setdefault(str(team_id), []).append(entity_id)
            self.teams = teams
            return

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
    def _handle_movement_reset_requested(self, entity_id: str, **_: Any) -> None:
        """Event callback to reset an entity's tracked movement usage."""

        self.reset_movement_usage(entity_id)

    def _handle_movement_distance_spent(self, entity_id: str, distance: int, **_: Any) -> None:
        """Event callback updating cached movement usage totals."""

        if distance <= 0:
            return
        if entity_id not in self.movement_turn_usage:
            self.movement_turn_usage[entity_id] = {"distance": 0}
        self.movement_turn_usage[entity_id]["distance"] += distance

    def reset_movement_usage(self, entity_id: str):
        """Reset per-turn movement tracking for an entity (called at turn start)."""
        self.movement_turn_usage[entity_id] = {"distance": 0}
        if self.ecs_manager:
            internal_id = self._ecs_entities.get(entity_id)
            if internal_id is None and self.ecs_manager:
                internal_id = self.ecs_manager.resolve_entity(entity_id)
            if internal_id is not None:
                component = self.ecs_manager.try_get_component(internal_id, MovementUsageComponent)
                if component is None:
                    component = MovementUsageComponent()
                    self.ecs_manager.add_component(internal_id, component)
                else:
                    component.reset()

    def add_movement_steps(self, entity_id: str, steps: int):
        if entity_id not in self.movement_turn_usage:
            self.reset_movement_usage(entity_id)
        self.movement_turn_usage[entity_id]["distance"] += steps
        if self.ecs_manager and steps:
            internal_id = self._ecs_entities.get(entity_id)
            if internal_id is None:
                internal_id = self.ecs_manager.resolve_entity(entity_id)
            if internal_id is not None:
                component = self.ecs_manager.try_get_component(internal_id, MovementUsageComponent)
                if component is None:
                    component = MovementUsageComponent()
                    self.ecs_manager.add_component(internal_id, component)
                component.add(steps)

    def get_movement_used(self, entity_id: str) -> int:
        if self.ecs_manager:
            internal_id = self._ecs_entities.get(entity_id)
            if internal_id is None:
                internal_id = self.ecs_manager.resolve_entity(entity_id)
            if internal_id is not None:
                component = self.ecs_manager.try_get_component(internal_id, MovementUsageComponent)
                if component is not None:
                    return int(getattr(component, "distance", 0))
        return self.movement_turn_usage.get(entity_id, {}).get("distance", 0)

    # Version bump helpers for LOS / cover caching
    def bump_terrain_version(self):
        self.terrain_version += 1

    def bump_blocker_version(self):
        self.blocker_version += 1

    # Internal helpers ---------------------------------------------------
    def _mirror_entity(self, entity_id: str, components: Dict[str, Any]) -> int:
        """Create an ECS entity mirroring ``entity_id`` and return its internal id."""

        if not self.ecs_manager:
            raise ValueError("ECS manager is not configured on GameState.")

        ecs_components = [self._build_identity_component(entity_id, components)]
        ecs_components.extend(components.values())
        return self.ecs_manager.create_entity(*ecs_components)

    def _cleanup_partial_ecs_entity(self, entity_id: str) -> None:
        """Attempt to delete any ECS entity created for ``entity_id`` during a failed mirror."""

        if not self.ecs_manager:
            return

        internal_id = self._ecs_entities.pop(entity_id, None)
        if internal_id is None:
            internal_id = self.ecs_manager.resolve_entity(entity_id)

        if internal_id is None:
            return

        try:
            self.ecs_manager.delete_entity(internal_id)
        except (AttributeError, KeyError) as cleanup_exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to clean up orphaned ECS entity for %s (internal id %s): %s",
                entity_id,
                internal_id,
                cleanup_exc,
            )
        except Exception as unexpected_exc:  # pragma: no cover - truly unexpected
            logger.exception(
                "Unexpected error during cleanup of ECS entity for %s (internal id %s):",
                entity_id,
                internal_id,
            )

    def _build_identity_component(self, entity_id: str, components: Dict[str, Any]) -> EntityIdComponent:
        """Construct an :class:`EntityIdComponent` linked to ``BaseObject`` ids when present."""

        base_object_id: Optional[int] = None
        char_ref = components.get("character_ref")
        if char_ref is not None:
            character = getattr(char_ref, "character", None)
            base_object_id = getattr(character, "id", None)
        return EntityIdComponent(entity_id, base_object_id)

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
