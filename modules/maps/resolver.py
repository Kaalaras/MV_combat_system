
"""Utilities for resolving the active :class:`~modules.maps.components.MapComponent`."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from modules.maps.components import MapComponent, MapGrid

CURRENT_MAP_REQUESTED = "current_map_requested"
"""Published by systems that require the active map entity."""

CURRENT_MAP_CHANGED = "current_map_changed"
"""Notification emitted when the active map entity changes."""


@dataclass(frozen=True)
class MapResolution:
    """Lightweight record returned by :class:`ActiveMapResolver`."""

    entity_id: str
    component: MapComponent

    @property
    def grid(self) -> MapGrid:
        return self.component.grid


class ActiveMapResolver:
    """Resolve the currently active map using the ECS and/or event bus."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: Optional[object] = None,
    ) -> None:
        self._ecs_manager = ecs_manager
        self._event_bus = event_bus
        self._cached: Optional[MapResolution] = None

        if event_bus is not None:
            subscribe = getattr(event_bus, "subscribe", None)
            if callable(subscribe):
                subscribe(CURRENT_MAP_CHANGED, self._on_map_changed)

    def _on_map_changed(self, **payload: object) -> None:
        entity_id = payload.get("entity_id")
        component = payload.get("map_component")

        if isinstance(entity_id, str) and isinstance(component, MapComponent):
            self._cached = MapResolution(entity_id=entity_id, component=component)
            return

        if isinstance(entity_id, str):
            component = self._fetch_component(entity_id)
            if component is not None:
                self._cached = MapResolution(entity_id=entity_id, component=component)
                return

        self._cached = None

    def get_active_map(self) -> MapResolution:
        """Return the active map entity/component pair."""

        if self._cached is None:
            self._cached = self._resolve_active_map()
        return self._cached

    def invalidate(self) -> None:
        """Clear any cached map reference."""

        self._cached = None

    def _resolve_active_map(self) -> MapResolution:
        if self._event_bus is not None:
            resolution = self._resolve_via_event_bus()
            if resolution is not None:
                return resolution

        for entity_id, component in self._ecs_manager.iter_with_id(MapComponent):
            return MapResolution(entity_id=entity_id, component=component)

        raise LookupError("No active map entity providing MapComponent was found.")

    def _resolve_via_event_bus(self) -> Optional[MapResolution]:
        provided: dict[str, object] = {}

        def _provider(
            entity_id: Optional[str] = None,
            map_component: Optional[MapComponent] = None,
        ) -> None:
            if map_component is None and isinstance(entity_id, str):
                fetched = self._fetch_component(entity_id)
            else:
                fetched = map_component

            if isinstance(entity_id, str) and isinstance(fetched, MapComponent):
                provided["entity_id"] = entity_id
                provided["map_component"] = fetched

        publish = getattr(self._event_bus, "publish", None)
        if callable(publish):
            publish(CURRENT_MAP_REQUESTED, provide=_provider)

        entity_id = provided.get("entity_id")
        component = provided.get("map_component")
        if isinstance(entity_id, str) and isinstance(component, MapComponent):
            return MapResolution(entity_id=entity_id, component=component)
        return None

    def _fetch_component(self, entity_id: str) -> Optional[MapComponent]:
        components = self._ecs_manager.get_components_for_entity(entity_id, MapComponent)
        if components:
            return components[0]
        return None


__all__ = [
    "ActiveMapResolver",
    "CURRENT_MAP_CHANGED",
    "CURRENT_MAP_REQUESTED",
    "MapResolution",
]
