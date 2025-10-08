from __future__ import annotations

import logging
from typing import Callable, Mapping, Protocol

from modules.maps.events import GenerateMap, MapGenerated
from modules.maps.gen import MapGenParams, decorate, generate_layout, get_rng
from modules.maps.gen.spawns import assign_spawn_zones
from modules.maps.gen.validate import ensure_valid_map
from modules.maps.spec import MapSpec
from core.event_bus import Topic


logger = logging.getLogger(__name__)


class _EventBus(Protocol):
    def subscribe(self, event_type: Topic, callback: Callable[..., None]) -> None:
        ...

    def publish(
        self, event_type: Topic, payload: Mapping[str, object] | None = None, /, **kwargs: object
    ) -> None:
        ...


def generate_map_spec(params: MapGenParams) -> MapSpec:
    """Run the procedural pipeline and return a validated :class:`MapSpec`."""

    rng = get_rng(params.seed)
    spec = generate_layout(params)
    spec = decorate(spec, params, rng)
    spec = ensure_valid_map(
        spec,
        reassign_spawns=lambda current: assign_spawn_zones(current, max_spawns=2),
        max_fixups=6,
    )
    return spec


class MapGeneratorSystem:
    """Listen for :class:`GenerateMap` events and publish :class:`MapGenerated`."""

    def __init__(self, *, event_bus: _EventBus) -> None:
        self._bus = event_bus
        self._bus.subscribe(GenerateMap.topic, self._on_generate_requested)

    def _on_generate_requested(self, *, params: MapGenParams, **_: object) -> None:
        try:
            spec = generate_map_spec(params)
        except Exception:
            logger.exception("Map generation failed for params: size=%s biome=%s seed=%s", params.size, params.biome, params.seed)
            raise
        MapGenerated(spec=spec).publish(self._bus)


__all__ = ["MapGeneratorSystem", "generate_map_spec"]

