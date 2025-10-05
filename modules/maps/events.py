"""Event definitions for map loading and activation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

from modules.maps.components import MapMeta


LOAD_MAP_FROM_TILED = "maps.load_from_tiled"
"""Event topic requesting a TMX map to be imported into the ECS."""

MAP_LOADED = "maps.loaded"
"""Event topic emitted when a map entity has been created."""


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


__all__ = [
    "LoadMapFromTiled",
    "MapLoaded",
    "MAP_LOADED",
    "LOAD_MAP_FROM_TILED",
]
