"""Event definitions for map loading and activation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

from modules.maps.components import MapMeta
from modules.maps.spec import MapSpec
from modules.maps.gen.params import MapGenParams


LOAD_MAP_FROM_TILED = "maps.load_from_tiled"
"""Event topic requesting a TMX map to be imported into the ECS."""

MAP_LOADED = "maps.loaded"
"""Event topic emitted when a map entity has been created."""

GENERATE_MAP = "maps.generate"
"""Event topic requesting a procedural map to be generated."""

MAP_GENERATED = "maps.generated"
"""Event topic emitted once a procedural :class:`MapSpec` is available."""


@runtime_checkable
class _PublishesEvents(Protocol):
    """Protocol capturing the subset of the event bus used here."""

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event to all subscribers."""


@dataclass(frozen=True, slots=True)
class LoadMapFromTiled:
    """Request loading of a Tiled TMX map into the ECS."""

    path: str

    topic: ClassVar[str] = LOAD_MAP_FROM_TILED

    def publish(self, bus: _PublishesEvents) -> None:
        """Convenience helper mirroring ``EventBus.publish``."""

        bus.publish(self.topic, path=self.path)


@dataclass(frozen=True, slots=True)
class MapLoaded:
    """Notification emitted once a map entity is available in the ECS."""

    map_entity_id: str
    meta: MapMeta

    topic: ClassVar[str] = MAP_LOADED

    def publish(self, bus: _PublishesEvents) -> None:
        """Convenience helper mirroring ``EventBus.publish``."""

        bus.publish(self.topic, map_entity_id=self.map_entity_id, meta=self.meta)


@dataclass(frozen=True, slots=True)
class GenerateMap:
    """Request procedural map generation using ``params``."""

    params: MapGenParams

    topic: ClassVar[str] = GENERATE_MAP

    def publish(self, bus: _PublishesEvents) -> None:
        bus.publish(self.topic, params=self.params)


@dataclass(frozen=True, slots=True)
class MapGenerated:
    """Notification containing the freshly generated :class:`MapSpec`."""

    spec: MapSpec

    topic: ClassVar[str] = MAP_GENERATED

    def publish(self, bus: _PublishesEvents) -> None:
        bus.publish(self.topic, spec=self.spec)


__all__ = [
    "LoadMapFromTiled",
    "MapLoaded",
    "MAP_LOADED",
    "LOAD_MAP_FROM_TILED",
    "GenerateMap",
    "MapGenerated",
    "GENERATE_MAP",
    "MAP_GENERATED",
]
