# core/game_state.py
from typing import Dict, List, Any, Optional


class GameState:
    """
    Central state management for a game using a proper Entity-Component System (ECS) architecture.

    **IMPORTANT**: This class has been refactored to eliminate the ECS architecture violation
    identified in the multiplayer readiness review. The problematic `self.entities` dictionary
    has been REMOVED to enforce proper ECS usage through the ECSManager.

    This class now serves as a coordinator between systems rather than storing entities directly,
    which is essential for multiplayer synchronization and proper ECS architecture.

    Attributes:
        ecs_manager: THE SINGLE SOURCE OF TRUTH for entities and components
        terrain: The game's terrain data
        event_bus: Reference to the enhanced event management system
        teams: Dictionary mapping team identifiers to lists of entity IDs
        movement: Reference to the movement system
        
    Example usage:

    ```python
    # Create game state with proper ECS
    ecs_manager = ECSManager()
    game_state = GameState(ecs_manager)

    # Initialize systems and set references
    terrain = TerrainGrid(100, 100)
    game_state.set_terrain(terrain)

    event_bus = EnhancedEventBus()
    game_state.set_event_bus(event_bus)

    # Add an entity through ECS (CORRECT WAY)
    entity_id = ecs_manager.create_entity(
        PositionComponent(10, 10),
        HealthComponent(100)
    )
    
    # Access entity components through ECS (CORRECT WAY)
    position = ecs_manager.get_component(entity_id, PositionComponent)
    ```
    
    **MIGRATION NOTE**: Code that previously used `game_state.get_entity()` or 
    `game_state.entities[id]` must be updated to use the ECS manager directly.
    """

    def __init__(self, ecs_manager: Optional[Any] = None):
        """
        Initialize game state with ECS manager reference.
        
        Args:
            ecs_manager: The ECS manager that handles all entity/component operations
                        If None, a default ECS manager will be created for backward compatibility
        """
        # ===== ECS ARCHITECTURE FIX =====
        # REMOVED: self.entities = {} -- This was the critical ECS violation
        # All entity operations now go through the ECS manager
        
        # Auto-create ECS manager if none provided (for backward compatibility with tests)
        if ecs_manager is None:
            from ecs.ecs_manager import ECSManager
            from core.event_bus import EventBus
            event_bus = EventBus()
            ecs_manager = ECSManager(event_bus)
        
        self.ecs_manager: Optional[Any] = ecs_manager
        
        # ===== SYSTEM REFERENCES =====
        self.terrain: Any = None  # Replace Any with actual Terrain type
        self.event_bus: Optional[Any] = None  # Optional: reference to EventBus, replace Any
        self.movement: Optional[Any] = None  # Optional: reference to MovementSystem, replace Any
        self.condition_system: Any = None  # Reference to ConditionSystem
        self.cover_system: Any = None  # Reference to CoverSystem
        self.terrain_effect_system: Any = None  # Reference to TerrainEffectSystem
        self.vision_system: Optional[Any] = None  # Optional: VisionSystem auto-wired on set_terrain
        
        # ===== GAME STATE DATA =====
        self.teams: Dict[str, List[str]] = {}
        self.movement_turn_usage: Dict[str, Dict[str, Any]] = {}  # {'distance':int}
        self.terrain_version = 0  # increments on wall add/remove
        self.blocker_version = 0  # increments on blocking entity move / cover changes
        
        # ===== MULTIPLAYER SUPPORT =====
        self.round_number: int = 0
        self.turn_number: int = 0
        self.current_player: Optional[str] = None

    # ===== DEPRECATED ENTITY METHODS =====
    # These methods have been REMOVED to fix ECS architecture violations.
    # Use the ECS manager directly instead.

    def add_entity(self, entity_id: str, components: Dict[str, Any]) -> None:
        """
        MIGRATION BRIDGE: Temporarily supports legacy code while enforcing ECS migration.
        
        This method provides backward compatibility during the ECS migration but will
        be removed once all code is migrated to proper ECS usage.
        """
        import warnings
        warnings.warn(
            "add_entity() is deprecated. Use ecs_manager.create_entity() with component instances instead. "
            "Example: entity_id = ecs_manager.create_entity(PositionComponent(x, y), HealthComponent(hp))",
            DeprecationWarning,
            stacklevel=2
        )
        
        if self.ecs_manager is None:
            raise RuntimeError("ECS manager not initialized. Cannot add entity without ECS manager.")
        
        # Convert dict components to ECS components and add to ECS
        from ecs.components.position import PositionComponent
        from ecs.components.character_ref import CharacterRefComponent
        from ecs.components.health import HealthComponent
        from ecs.components.equipment import EquipmentComponent
        
        ecs_components = []
        for comp_name, comp_value in components.items():
            if comp_name == 'position' and hasattr(comp_value, 'x') and hasattr(comp_value, 'y'):
                ecs_components.append(PositionComponent(comp_value.x, comp_value.y, 
                                                        getattr(comp_value, 'width', 1), 
                                                        getattr(comp_value, 'height', 1)))
            elif comp_name == 'character_ref':
                ecs_components.append(CharacterRefComponent(comp_value.character if hasattr(comp_value, 'character') else comp_value))
            elif comp_name == 'health':
                ecs_components.append(HealthComponent(getattr(comp_value, 'current', 100), 
                                                      getattr(comp_value, 'maximum', 100)))
            elif comp_name == 'equipment':
                ecs_components.append(EquipmentComponent(comp_value))
        
        if ecs_components:
            # Use create_entity instead of add_entity to avoid the string ID issue
            new_entity_id = self.ecs_manager.create_entity(*ecs_components)
            # Store the mapping for legacy lookups
            if not hasattr(self, '_entity_id_mapping'):
                self._entity_id_mapping = {}
            self._entity_id_mapping[entity_id] = new_entity_id

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        MIGRATION BRIDGE: Temporarily supports legacy code while enforcing ECS migration.
        
        Returns a dict-like object that provides access to entity components
        through the ECS system, maintaining backward compatibility.
        """
        import warnings
        warnings.warn(
            "get_entity() is deprecated. Use ecs_manager.get_component(entity_id, ComponentType) instead. "
            "Example: position = ecs_manager.get_component(entity_id, PositionComponent)",
            DeprecationWarning,
            stacklevel=2
        )
        
        if self.ecs_manager is None:
            return None
        
        # Check if we have a mapping for this entity ID
        if hasattr(self, '_entity_id_mapping') and entity_id in self._entity_id_mapping:
            actual_entity_id = self._entity_id_mapping[entity_id]
        else:
            # Try to convert to int for legacy support
            try:
                actual_entity_id = int(entity_id)
            except (ValueError, TypeError):
                return None
        
        if not self.ecs_manager.entity_exists(actual_entity_id):
            return None
        
        # Return a bridge object that provides dict-like access to ECS components
        return _EntityBridge(self.ecs_manager, actual_entity_id)

    def remove_entity(self, entity_id: str) -> None:
        """
        MIGRATION BRIDGE: Temporarily supports legacy code while enforcing ECS migration.
        """
        import warnings
        warnings.warn(
            "remove_entity() is deprecated. Use ecs_manager.delete_entity(entity_id) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        if self.ecs_manager is None:
            return
        
        if self.ecs_manager.entity_exists(entity_id):
            self.ecs_manager.delete_entity(entity_id)

    def get_component(self, entity_id: str, component_name: str) -> Optional[Any]:
        """
        MIGRATION BRIDGE: Temporarily supports legacy code while enforcing ECS migration.
        """
        import warnings
        warnings.warn(
            "get_component() is deprecated. Use ecs_manager.get_component(entity_id, ComponentType) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        entity = self.get_entity(entity_id)
        if entity is None:
            return None
        return entity.get(component_name)

    def set_component(self, entity_id: str, component_name: str, component_value: Any) -> None:
        """
        MIGRATION BRIDGE: Temporarily supports legacy code while enforcing ECS migration.
        """
        import warnings
        warnings.warn(
            "set_component() is deprecated. Use ecs_manager.add_component(entity_id, component_instance) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        if self.ecs_manager is None:
            return
        
        # Convert to proper ECS component and set
        from ecs.components.position import PositionComponent
        from ecs.components.character_ref import CharacterRefComponent
        from ecs.components.health import HealthComponent
        
        if component_name == 'position' and hasattr(component_value, 'x'):
            self.ecs_manager.add_component(entity_id, 
                PositionComponent(component_value.x, component_value.y,
                                  getattr(component_value, 'width', 1),
                                  getattr(component_value, 'height', 1)))
        elif component_name == 'character_ref':
            self.ecs_manager.add_component(entity_id, CharacterRefComponent(component_value))
        elif component_name == 'health':
            self.ecs_manager.add_component(entity_id, HealthComponent(
                getattr(component_value, 'current', 100),
                getattr(component_value, 'maximum', 100)))

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
        
        **UPDATED**: Now uses ECS manager instead of deprecated entities dictionary.
        
        Returns:
            None
        """
        if not self.ecs_manager:
            return
            
        teams: Dict[str, List[str]] = {}
        
        # Get all entities with character_ref components using ECS
        try:
            from ecs.components.character_ref import CharacterRefComponent
            entities_with_chars = self.ecs_manager.get_components(CharacterRefComponent)
            
            for entity_id, (char_ref,) in entities_with_chars:
                char = getattr(char_ref, 'character', None)
                if not char:
                    continue
                tm = getattr(char, 'team', None)
                if tm is not None:
                    teams.setdefault(str(tm), []).append(str(entity_id))
        except (ImportError, AttributeError):
            # Fallback: no character ref components found
            pass
            
        self.teams = teams

    def get_entity_size(self, entity_id: str) -> tuple[int, int]:
        """
        Retrieve the width and height of an entity's position (if any).
        
        **UPDATED**: Now uses ECS manager instead of deprecated entities dictionary.

        Returns:
            Tuple (width, height) representing the entity's size in grid cells, default (1, 1)
        """
        if not self.ecs_manager:
            return 1, 1
            
        try:
            from ecs.components.position import PositionComponent
            pos_comp = self.ecs_manager.get_component(int(entity_id), PositionComponent)
            return getattr(pos_comp, 'width', 1), getattr(pos_comp, 'height', 1)
        except (ImportError, KeyError, ValueError):
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
        """
        Mark an entity as dead and publish death event.
        
        **UPDATED**: Now uses ECS manager instead of deprecated entities dictionary.
        """
        if not self.ecs_manager:
            return False
            
        try:
            from ecs.components.character_ref import CharacterRefComponent
            cref = self.ecs_manager.get_component(int(entity_id), CharacterRefComponent)
            char = getattr(cref, 'character', None) if cref else None
        except (ImportError, KeyError, ValueError):
            return False
            
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
    
    @property
    def entities(self) -> '_EntitiesBridge':
        """
        MIGRATION BRIDGE: Provides dict-like access to entities through ECS.
        
        This property maintains backward compatibility during ECS migration
        while providing access to entities through the ECS system.
        """
        import warnings
        warnings.warn(
            "Direct access to game_state.entities is deprecated. "
            "Use ecs_manager methods directly for better performance and proper ECS architecture.",
            DeprecationWarning,
            stacklevel=2
        )
        return _EntitiesBridge(self.ecs_manager)


class _EntityBridge:
    """
    Bridge class that provides dict-like access to ECS entity components.
    
    This maintains backward compatibility during ECS migration while providing
    access to entity data through the proper ECS system.
    """
    
    def __init__(self, ecs_manager: Any, entity_id: str):
        self.ecs_manager = ecs_manager
        self.entity_id = entity_id
        
    def __contains__(self, key: str) -> bool:
        """Check if entity has a component with the given name."""
        if not self.ecs_manager:
            return False
        
        try:
            entity_id_int = int(self.entity_id)
            if not self.ecs_manager.entity_exists(entity_id_int):
                return False
        except (ValueError, TypeError):
            return False
        
        # Map component names to actual component classes
        component_map = {
            'position': 'ecs.components.position.PositionComponent',
            'character_ref': 'ecs.components.character_ref.CharacterRefComponent', 
            'health': 'ecs.components.health.HealthComponent',
            'equipment': 'ecs.components.equipment.EquipmentComponent',
            'willpower': 'ecs.components.willpower.WillpowerComponent',
            'facing': 'ecs.components.facing.FacingComponent',
            'velocity': 'ecs.components.velocity.VelocityComponent',
        }
        
        if key in component_map:
            try:
                module_path, class_name = component_map[key].rsplit('.', 1)
                module = __import__(module_path, fromlist=[class_name])
                component_class = getattr(module, class_name)
                return self.ecs_manager.get_component(entity_id_int, component_class) is not None
            except (ImportError, KeyError, ValueError, AttributeError):
                return False
        
        return False
    
    def get(self, key: str, default=None):
        """Get a component value with a default fallback."""
        if key in self:
            return self[key]
        return default
    
    def __getitem__(self, key: str):
        """Get a component value by name."""
        try:
            entity_id_int = int(self.entity_id)
            if not self.ecs_manager or not self.ecs_manager.entity_exists(entity_id_int):
                raise KeyError(f"Entity {self.entity_id} not found")
        except (ValueError, TypeError):
            raise KeyError(f"Invalid entity ID {self.entity_id}")
        
        # Map component names to actual component classes
        component_map = {
            'position': 'ecs.components.position.PositionComponent',
            'character_ref': 'ecs.components.character_ref.CharacterRefComponent',
            'health': 'ecs.components.health.HealthComponent', 
            'equipment': 'ecs.components.equipment.EquipmentComponent',
            'willpower': 'ecs.components.willpower.WillpowerComponent',
            'facing': 'ecs.components.facing.FacingComponent',
            'velocity': 'ecs.components.velocity.VelocityComponent',
        }
        
        if key in component_map:
            try:
                module_path, class_name = component_map[key].rsplit('.', 1)
                module = __import__(module_path, fromlist=[class_name])
                component_class = getattr(module, class_name)
                component = self.ecs_manager.get_component(entity_id_int, component_class)
                if component is not None:
                    return component
            except (ImportError, KeyError, ValueError, AttributeError):
                pass
        
        raise KeyError(f"Component '{key}' not found for entity {self.entity_id}")


class _EntitiesBridge:
    """
    Bridge class that provides dict-like access to all entities through ECS.
    
    This maintains backward compatibility during ECS migration while providing
    access to entities through the proper ECS system.
    """
    
    def __init__(self, ecs_manager: Any):
        self.ecs_manager = ecs_manager
        
    def __contains__(self, entity_id: str) -> bool:
        """Check if entity exists."""
        if not self.ecs_manager:
            return False
        try:
            return self.ecs_manager.entity_exists(int(entity_id))
        except (ValueError, TypeError):
            return False
    
    def __getitem__(self, entity_id: str) -> _EntityBridge:
        """Get entity bridge by ID."""
        if entity_id not in self:
            raise KeyError(f"Entity {entity_id} not found")
        return _EntityBridge(self.ecs_manager, entity_id)
    
    def get(self, entity_id: str, default=None):
        """Get entity with default fallback."""
        if entity_id in self:
            return self[entity_id]
        return default
    
    def items(self):
        """Iterate over entity_id, entity_bridge pairs."""
        if not self.ecs_manager:
            return
        
        # Get all entity IDs from ECS manager
        try:
            for entity_id in self.ecs_manager.get_all_entities():
                yield str(entity_id), _EntityBridge(self.ecs_manager, str(entity_id))
        except (AttributeError, TypeError):
            # Fallback if get_all_entities doesn't exist
            pass
    
    def keys(self):
        """Get all entity IDs."""
        for entity_id, _ in self.items():
            yield entity_id
    
    def values(self):
        """Get all entity bridges.""" 
        for _, entity_bridge in self.items():
            yield entity_bridge
