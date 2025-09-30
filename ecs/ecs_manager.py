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
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type

try:  # pragma: no cover - import guard for environments without esper
    import esper  # type: ignore
except Exception:  # pragma: no cover - fallback for missing dependency
    esper = None

from ecs.components.entity_id import EntityIdComponent


ProcessorType = getattr(esper, "Processor", Any)


class _FallbackWorld:
    """Lightweight stand-in when ``esper.World`` is unavailable.

    Notes:
        This implementation favors portability over performance. Component
        lookups rely on standard Python dictionaries and lack the indexing
        optimizations provided by ``esper.World``, so large-scale simulations
        will process noticeably slower when running against the fallback.
    """

    def __init__(self) -> None:
        self._next_entity_id = 1
        self._components: Dict[int, Dict[Type[Any], Any]] = {}
        self._processors: List[Tuple[int, Any]] = []

    def create_entity(self, *components: Any) -> int:
        entity_id = self._next_entity_id
        self._next_entity_id += 1
        self._components[entity_id] = {}
        for component in components:
            self.add_component(entity_id, component)
        return entity_id

    def delete_entity(self, entity_id: int) -> None:
        self._components.pop(entity_id, None)

    def add_component(self, entity_id: int, component_instance: Any) -> None:
        self._components.setdefault(entity_id, {})[type(component_instance)] = component_instance

    def component_for_entity(self, entity_id: int, component_type: Type[Any]) -> Any:
        try:
            return self._components[entity_id][component_type]
        except KeyError as exc:  # pragma: no cover - parity with esper error shape
            raise KeyError(component_type) from exc

    def get_components(self, *component_types: Type[Any]):
        results = []
        for entity_id, components in self._components.items():
            try:
                comp_tuple = tuple(components[ctype] for ctype in component_types)
            except KeyError:
                continue
            results.append((entity_id, comp_tuple))
        return results

    # Processor support -------------------------------------------------
    def add_processor(self, processor_instance: Any, priority: int = 0) -> None:
        self._processors.append((priority, processor_instance))
        self._processors.sort(key=lambda item: item[0])

    def remove_processor(self, processor_instance: Any) -> None:
        self._processors = [item for item in self._processors if item[1] is not processor_instance]

    def get_processor(self, processor_type: Type[Any]) -> Optional[Any]:
        for _, processor in self._processors:
            if isinstance(processor, processor_type):
                return processor
        return None

    def process(self, *args: Any, **kwargs: Any) -> None:
        for _, processor in self._processors:
            if hasattr(processor, "process"):
                processor.process(*args, **kwargs)


WorldType = getattr(esper, "World", _FallbackWorld)

class ECSManager:
    """
    Manages the Entity Component System architecture for the game.

    This class wraps the esper.World instance and provides convenience methods
    for entity and component management, as well as system processing.

    Attributes:
        world (esper.World): The esper world instance that handles entities and components
        event_bus: The event system used for communication between game components
    """

    def __init__(self, event_bus: Optional[Any] = None):
        """
        Initialize the ECS Manager with an optional event bus.

        Args:
            event_bus: The event system for communication between components
                       (Default: None)
        """
        self.world = WorldType()
        self.event_bus = event_bus
        self._entity_lookup: Dict[str, int] = {}
        self._reverse_lookup: Dict[int, str] = {}
        # Systems that need to be processed each frame/tick by esper
        # esper.Processor instances are added directly to the world.
        # Other systems might just subscribe to events and not need a process() method.

    def add_processor(self, processor_instance: ProcessorType, priority: int = 0):
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
        if hasattr(self.world, "add_processor"):
            self.world.add_processor(processor_instance, priority)

    def remove_processor(self, processor_instance: ProcessorType):
        """
        Removes a system processor from the ECS world.

        Args:
            processor_instance (esper.Processor): The processor to remove

        Example:
            > ecs_manager.remove_processor(movement_system)
        """
        if hasattr(self.world, "remove_processor"):
            self.world.remove_processor(processor_instance)

    def get_processor(self, processor_type: type) -> Optional[ProcessorType]:
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
        if hasattr(self.world, "get_processor"):
            return self.world.get_processor(processor_type)
        return None

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
        self.world.process(*args, **kwargs)  # Pass any necessary context like dt, game_state

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
        entity_id = self.world.create_entity(*components)
        for component in components:
            self._register_entity_identity(entity_id, component)
        return entity_id

    def delete_entity(self, entity_id: int):
        """
        Deletes an entity and all its components from the world.

        Args:
            entity_id (int): The ID of the entity to delete

        Example:
            > ecs_manager.delete_entity(enemy_entity)
        """
        string_id = self._reverse_lookup.pop(entity_id, None)
        if string_id:
            self._entity_lookup.pop(string_id, None)
        self.world.delete_entity(entity_id)

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
        self.world.add_component(entity_id, component_instance)
        self._register_entity_identity(entity_id, component_instance)

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
        return self.world.component_for_entity(entity_id, component_type)

    def get_components(self, *component_types: type):
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
        return self.world.get_components(*component_types)

    # New helpers ---------------------------------------------------------------
    def resolve_entity(self, entity_id: str) -> Optional[int]:
        """Return the internal ECS integer id for a string ``entity_id``."""

        return self._entity_lookup.get(entity_id)

    def get_component_for_entity(self, entity_id: str, component_type: Type[Any]) -> Optional[Any]:
        """Return a specific component for the entity identified by ``entity_id``."""

        components = self.get_components_for_entity(entity_id, component_type)
        if components is None:
            return None
        return components[0]

    def iter_with_id(self, *component_types: Type[Any]) -> Iterator[Tuple[str, ...]]:
        """
        Yield tuples of ``(entity_id_str, components...)`` for entities that
        provide ``EntityIdComponent`` in addition to ``component_types``.
        """

        query_types = (EntityIdComponent,) + component_types
        for _, components in self.world.get_components(*query_types):
            entity_id_component: EntityIdComponent = components[0]
            yield (entity_id_component.entity_id, *components[1:])

    def get_components_for_entity(self, entity_id: str, *component_types: Type[Any]) -> Optional[Tuple[Any, ...]]:
        """
        Return component instances for the entity identified by ``entity_id``.

        Returns ``None`` if the entity does not exist or lacks any requested
        component.
        """

        internal_id = self.resolve_entity(entity_id)
        if internal_id is None:
            return None
        try:
            return tuple(
                self.world.component_for_entity(internal_id, comp_type)
                for comp_type in component_types
            )
        except KeyError:
            return None

    # Internal helpers ---------------------------------------------------
    def _register_entity_identity(self, internal_id: int, component: Any) -> None:
        """Track mappings whenever an :class:`EntityIdComponent` is encountered."""

        if isinstance(component, EntityIdComponent):
            self._entity_lookup[component.entity_id] = internal_id
            self._reverse_lookup[internal_id] = component.entity_id

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
        try:
            return self.world.component_for_entity(entity_id, component_type)
        except KeyError:
            return None
