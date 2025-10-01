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
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, Iterator, List, Optional, Tuple, Type

try:  # pragma: no cover - import guard for environments without esper
    import esper  # type: ignore
except ImportError:  # pragma: no cover - fallback for missing dependency
    esper = None

from ecs.components.entity_id import EntityIdComponent

if TYPE_CHECKING:  # pragma: no cover - import hints only
    from ecs.components.character_ref import CharacterRefComponent
    from ecs.components.position import PositionComponent


ProcessorType = getattr(esper, "Processor", Any) if esper else Any


@dataclass(frozen=True)
class CharacterTeamSnapshot:
    """Immutable view of a character entity's team-related ECS data."""

    entity_id: str
    character_ref: "CharacterRefComponent"
    character: Any
    position: Optional["PositionComponent"]
    team_id: Optional[str]
    is_alive: bool


@dataclass(frozen=True)
class TeamSnapshot:
    """Aggregate team state derived from :class:`CharacterTeamSnapshot` data."""

    team_id: str
    members: Tuple[CharacterTeamSnapshot, ...]
    member_ids: Tuple[str, ...]
    alive_member_ids: Tuple[str, ...]
    defeated_member_ids: Tuple[str, ...]

    @property
    def alive_count(self) -> int:
        return len(self.alive_member_ids)

    @property
    def is_active(self) -> bool:
        return self.alive_count > 0

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
            raise KeyError(
                f"Entity {entity_id} does not have component {component_type}"
            ) from exc

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

    def iter_character_snapshots(
        self,
        include_position: bool = True,
    ) -> Iterator[Tuple[str, "CharacterRefComponent", Optional["PositionComponent"]]]:
        """Yield character-focused component tuples keyed by string entity id.

        Args:
            include_position: When ``True`` (default), attempt to include
                :class:`~ecs.components.position.PositionComponent` data for
                each entity. Entities lacking a position component are still
                yielded with ``None`` in the third slot so callers can decide
                how to handle them.
        """

        from ecs.components.character_ref import CharacterRefComponent as _CharacterRefComponent
        from ecs.components.position import PositionComponent as _PositionComponent

        for entity_id, char_ref in self.iter_with_id(_CharacterRefComponent):
            position_component: Optional[_PositionComponent]
            position_component = None
            if include_position:
                internal_id = self.resolve_entity(entity_id)
                if internal_id is not None:
                    position_component = self.try_get_component(internal_id, _PositionComponent)
            yield entity_id, char_ref, position_component

    def iter_character_team_snapshots(
        self,
        include_position: bool = True,
        include_unassigned: bool = True,
    ) -> Iterator[CharacterTeamSnapshot]:
        """Yield :class:`CharacterTeamSnapshot` records for character entities."""

        from ecs.components.character_ref import CharacterRefComponent as _CharacterRefComponent
        from ecs.components.position import PositionComponent as _PositionComponent

        for entity_id, char_ref in self.iter_with_id(_CharacterRefComponent):
            character = getattr(char_ref, "character", None)
            if character is None:
                continue
            raw_team = getattr(character, "team", None)
            team_id: Optional[str] = None if raw_team is None else str(raw_team)
            if not include_unassigned and team_id is None:
                continue
            position_component: Optional[_PositionComponent] = None
            if include_position:
                internal_id = self.resolve_entity(entity_id)
                if internal_id is not None:
                    position_component = self.try_get_component(internal_id, _PositionComponent)
            is_alive = not getattr(character, "is_dead", False)
            yield CharacterTeamSnapshot(
                entity_id=entity_id,
                character_ref=char_ref,
                character=character,
                position=position_component,
                team_id=team_id,
                is_alive=is_alive,
            )

    def collect_team_rosters(
        self,
        include_position: bool = True,
        include_unassigned: bool = False,
        snapshots: Optional[Iterable[CharacterTeamSnapshot]] = None,
    ) -> Dict[str, TeamSnapshot]:
        """Return a mapping of team identifiers to :class:`TeamSnapshot` data."""

        teams: Dict[str, List[CharacterTeamSnapshot]] = defaultdict(list)
        snapshot_iterable: Iterable[CharacterTeamSnapshot]
        if snapshots is not None:
            snapshot_iterable = snapshots
        else:
            snapshot_iterable = self.iter_character_team_snapshots(
                include_position=include_position,
                include_unassigned=include_unassigned,
            )

        for snapshot in snapshot_iterable:
            if snapshot.team_id is None:
                if include_unassigned:
                    teams.setdefault("__unassigned__", []).append(snapshot)
                continue
            teams[snapshot.team_id].append(snapshot)

        team_state: Dict[str, TeamSnapshot] = {}
        for team_id, members in teams.items():
            ordered_members = tuple(sorted(members, key=lambda snap: snap.entity_id))
            member_ids = tuple(member.entity_id for member in ordered_members)
            alive_ids = tuple(member.entity_id for member in ordered_members if member.is_alive)
            defeated_ids = tuple(
                member.entity_id for member in ordered_members if not member.is_alive
            )
            team_state[team_id] = TeamSnapshot(
                team_id=team_id,
                members=ordered_members,
                member_ids=member_ids,
                alive_member_ids=alive_ids,
                defeated_member_ids=defeated_ids,
            )
        return team_state

    def iter_team_rosters(
        self,
        include_position: bool = True,
        include_unassigned: bool = False,
        snapshots: Optional[Iterable[CharacterTeamSnapshot]] = None,
    ) -> Iterator[TeamSnapshot]:
        """Iterate over :class:`TeamSnapshot` instances grouped by team."""

        yield from self.collect_team_rosters(
            include_position=include_position,
            include_unassigned=include_unassigned,
            snapshots=snapshots,
        ).values()

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
