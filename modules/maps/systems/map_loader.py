"""Event-driven system responsible for importing maps into the ECS."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Protocol

from ecs.components.entity_id import EntityIdComponent
from modules.maps.components import MapComponent, MapMeta
from modules.maps.events import LoadMapFromTiled, MapLoaded
from modules.maps.spec import to_map_component
from modules.maps.tiled_importer import TiledImporter


class _EventBus(Protocol):
    """Subset of the event bus interface required by :class:`MapLoaderSystem`."""

    def subscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        ...

    def publish(self, event_type: str, **payload: object) -> None:
        ...


class MapLoaderSystem:
    """Listen for :class:`LoadMapFromTiled` requests and create map entities."""

    def __init__(
        self,
        ecs_manager: "ECSManager",
        *,
        event_bus: _EventBus,
        importer: Optional[TiledImporter] = None,
    ) -> None:
        self._ecs = ecs_manager
        self._bus = event_bus
        self._importer = importer or TiledImporter()
        self._active_internal_id: Optional[int] = None
        self._active_entity_id: Optional[str] = None

        self._bus.subscribe(LoadMapFromTiled.topic, self._on_load_requested)

    # ------------------------------------------------------------------
    def _on_load_requested(self, *, path: str, **_: object) -> None:
        spec = self._importer.load(path)
        map_component = to_map_component(spec)

        self._despawn_active_map()

        entity_id = self._derive_entity_id(spec.meta, path)
        internal_id = self._ecs.create_entity(
            EntityIdComponent(entity_id),
            map_component,
        )
        self._active_internal_id = internal_id
        self._active_entity_id = entity_id

        MapLoaded(map_entity_id=entity_id, meta=map_component.meta).publish(self._bus)

    def _despawn_active_map(self) -> None:
        if self._active_internal_id is None:
            return
        self._ecs.delete_entity(self._active_internal_id)
        self._active_internal_id = None
        self._active_entity_id = None

    def _derive_entity_id(self, meta: MapMeta, path: str) -> str:
        base = self._normalise_identifier(meta.name)
        if not base:
            base = self._normalise_identifier(Path(path).stem)
        if not base:
            base = "map"

        candidate = f"map:{base}"
        suffix = 1
        while True:
            existing = self._ecs.resolve_entity(candidate)
            if existing is None:
                break
            suffix += 1
            candidate = f"map:{base}:{suffix}"
        return candidate

    @staticmethod
    def _normalise_identifier(raw: str | None) -> str:
        if not raw:
            return ""
        lowered = raw.lower()
        normalised = [
            ch if ch.isalnum() else "_"
            for ch in lowered
        ]
        collapsed = "".join(normalised).strip("_")
        while "__" in collapsed:
            collapsed = collapsed.replace("__", "_")
        return collapsed

    # Public API -------------------------------------------------------
    def get_active_map(self) -> tuple[str, MapComponent]:
        """Return the active map entity id and component."""

        if self._active_entity_id is None:
            raise LookupError("No active map has been loaded.")

        component = self._ecs.get_component_for_entity(self._active_entity_id, MapComponent)
        if component is None:
            raise LookupError("Active map component is missing from the ECS.")
        return self._active_entity_id, component


def get_active_map(ecs_manager: "ECSManager") -> tuple[str, MapComponent]:
    """Helper that queries the ECS for the single active map component."""

    candidates = list(ecs_manager.iter_with_id(MapComponent))
    if not candidates:
        raise LookupError("No map entities are currently registered in the ECS.")
    if len(candidates) > 1:
        raise LookupError("Multiple map entities detected; cannot determine the active map.")
    entity_id, component = candidates[0]
    return entity_id, component


__all__ = [
    "MapLoaderSystem",
    "get_active_map",
]
