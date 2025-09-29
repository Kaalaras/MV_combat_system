# ecs/ecs_manager.py
"""
Entity Component System Manager Module
=====================================

This module provides a centralized manager for an Entity Component System (ECS) architecture
using the esper framework. It handles entity creation, component management, and system processing.

The ECSManager serves as the primary interface for interacting with the ECS world, providing
convenience methods for common operations like entity creation/deletion and component management.

Example:
    # Create an event bus
    event_bus = EventBus()

    # Initialize the ECS manager
    ecs_manager = ECSManager(event_bus)

    # Add a processor system
    movement_system = MovementSystem()
    ecs_manager.add_processor(movement_system, priority=1)

    # Create an entity with components
    player_entity = ecs_manager.create_entity(
        Position(x=5, y=10),
        Renderable(sprite_path="player.png"),
        Velocity(dx=0, dy=0)
    )

    # Add a component to an existing entity
    ecs_manager.add_component(player_entity, Health(max_hp=100))

    # Process all systems
    ecs_manager.process(dt=0.016)
"""
import esper
from typing import Any, Optional, List


# Placeholder for actual component imports if needed directly by ECSManager
# from ecs.components.position import Position # etc.

class ECSManager:
    """
    Manages the Entity Component System architecture for the game.

    This class wraps the esper module functions and provides convenience methods
    for entity and component management, as well as system processing.

    Attributes:
        world_id (str): The unique identifier for this world in esper
        event_bus: The event system used for communication between game components
    """

    def __init__(self, event_bus: Optional[Any] = None, world_id: str = "default"):
        """
        Initialize the ECS Manager with an optional event bus.

        Args:
            event_bus: The event system for communication between components
                       (Default: None)
            world_id: Unique identifier for this world (Default: "default")
        """
        self.world_id = world_id
        self.event_bus = event_bus
        
        # Switch to our world (esper uses a global context)
        esper.switch_world(self.world_id)
        
        # Systems that need to be processed each frame/tick by esper
        # esper.Processor instances are added directly to the world.
        # Other systems might just subscribe to events and not need a process() method.

    def add_processor(self, processor_instance: esper.Processor, priority: int = 0):
        """
        Adds a system processor to the ECS world with the specified priority.

        Higher priority processors are processed first.

        Args:
            processor_instance (esper.Processor): The processor to add
            priority (int): Processing order priority (Default: 0)

        Example:
            > movement_system = MovementSystem()
            > ecs_manager.add_processor(movement_system, priority=2)
        """
        esper.switch_world(self.world_id)
        esper.add_processor(processor_instance, priority)

    def remove_processor(self, processor_instance: esper.Processor):
        """
        Removes a system processor from the ECS world.

        Args:
            processor_instance (esper.Processor): The processor to remove

        Example:
            > ecs_manager.remove_processor(movement_system)
        """
        esper.switch_world(self.world_id)
        esper.remove_processor(processor_instance)

    def get_processor(self, processor_type: type) -> Optional[esper.Processor]:
        """
        Gets a processor of a specific type from the ECS world.

        Args:
            processor_type (type): The type of processor to retrieve

        Returns:
            Optional[esper.Processor]: The processor instance if found, None otherwise

        Example:
            > movement_sys = ecs_manager.get_processor(MovementSystem)
            > if movement_sys:
            >     movement_sys.set_speed_multiplier(1.5)
        """
        esper.switch_world(self.world_id)
        return esper.get_processor(processor_type)

    def process(self, *args, **kwargs):
        """
        Processes all registered processors in the world.

        This should be called each game tick/frame to update all systems.

        Args:
            *args: Variable length argument list passed to each processor
            **kwargs: Arbitrary keyword arguments passed to each processor

        Example:
            > # Process systems with delta time
            > ecs_manager.process(dt=0.016)
        """
        esper.switch_world(self.world_id)
        esper.process(*args, **kwargs)  # Pass any necessary context like dt, game_state

    # Entity creation helpers can remain here or be moved to a factory
    def create_entity(self, *components: Any) -> int:
        """
        Creates a new entity with the given components.

        Args:
            *components: Variable number of component instances to add to the entity

        Returns:
            int: The newly created entity ID

        Example:
            > player_entity = ecs_manager.create_entity(
            >     Position(x=5, y=10),
            >     Renderable(sprite_path="player.png")
            > )
        """
        esper.switch_world(self.world_id)
        return esper.create_entity(*components)

    def delete_entity(self, entity_id: int):
        """
        Deletes an entity and all its components from the world.

        Args:
            entity_id (int): The ID of the entity to delete

        Example:
            > ecs_manager.delete_entity(enemy_entity)
        """
        esper.switch_world(self.world_id)
        esper.delete_entity(entity_id)

    def add_component(self, entity_id: int, component_instance: Any):
        """
        Adds a component to an existing entity.

        If the entity already has a component of the same type,
        it will be replaced with this new instance.

        Args:
            entity_id (int): The ID of the entity
            component_instance: The component instance to add

        Example:
            > ecs_manager.add_component(player_entity, Health(max_hp=100))
        """
        esper.switch_world(self.world_id)
        esper.add_component(entity_id, component_instance)

    def get_component(self, entity_id: int, component_type: type) -> Any:
        """
        Retrieves a component instance for an entity.

        Args:
            entity_id (int): The ID of the entity
            component_type (type): The type of component to retrieve

        Returns:
            Any: The component instance

        Raises:
            KeyError: If the entity does not have the specified component

        Example:
            > position = ecs_manager.get_component(player_entity, Position)
            > position.x += 5
        """
        esper.switch_world(self.world_id)
        return esper.component_for_entity(entity_id, component_type)

    def get_components(self, *component_types: type) -> List[Any]:
        """
        Retrieves all entities and their specified component instances.

        Args:
            *component_types: Variable number of component types to query for

        Returns:
            List[Any]: A list containing tuples of (entity_id, (component1, component2, ...))

        Example:
            > # Get all entities with both Position and Renderable components
            > for entity_id, (position, renderable) in ecs_manager.get_components(Position, Renderable):
            >     print(f"Entity {entity_id} is at position {position.x}, {position.y}")
        """
        esper.switch_world(self.world_id)
        return esper.get_components(*component_types)

    def try_get_component(self, entity_id: int, component_type: type) -> Optional[Any]:
        """
        Tries to retrieve a component for an entity, returns None if not found.

        This is a safer alternative to get_component() when you're not sure
        if the entity has the component.

        Args:
            entity_id (int): The ID of the entity
            component_type (type): The type of component to retrieve

        Returns:
            Optional[Any]: The component instance if found, None otherwise

        Example:
            > health = ecs_manager.try_get_component(entity_id, Health)
            > if health:
            >     health.current -= 10
        """
        esper.switch_world(self.world_id)
        return esper.try_component(entity_id, component_type)

    def entity_exists(self, entity_id: int) -> bool:
        """
        Check if an entity exists in the world.

        Args:
            entity_id (int): The ID of the entity to check

        Returns:
            bool: True if the entity exists, False otherwise

        Example:
            > if ecs_manager.entity_exists(player_entity):
            >     print("Player entity exists")
        """
        esper.switch_world(self.world_id)
        return esper.entity_exists(entity_id)

    def get_all_entities(self) -> List[int]:
        """
        Get a list of all entity IDs in the world.

        Returns:
            List[int]: List of all entity IDs

        Example:
            > all_entities = ecs_manager.get_all_entities()
            > print(f"Total entities: {len(all_entities)}")
        """
        esper.switch_world(self.world_id)
        # In esper, all entities are stored as keys in _entities
        return list(esper._entities.keys())

    def add_entity(self, entity_id: int, *components: Any) -> None:
        """
        Add an entity with a specific ID and components.

        This is useful for migration scenarios where you need to preserve entity IDs.

        Args:
            entity_id (int): The desired entity ID
            *components: Variable number of component instances to add to the entity

        Example:
            > ecs_manager.add_entity(123, Position(x=5, y=10), Health(100))
        """
        esper.switch_world(self.world_id)
        
        # Create a temporary entity to get components properly set up
        temp_id = esper.create_entity(*components)
        
        # If we got the desired ID, we're done
        if temp_id == entity_id:
            return
        
        # Otherwise, manually reassign the entity ID
        if temp_id in esper._entities:
            # Move the entity record
            esper._entities[entity_id] = esper._entities[temp_id]
            del esper._entities[temp_id]
            
            # Update all component mappings
            for component_type, component in esper._components.items():
                if temp_id in component:
                    component[entity_id] = component[temp_id]
                    del component[temp_id]
