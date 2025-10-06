from __future__ import annotations

from collections import defaultdict

from modules.maps.events import GenerateMap, MapGenerated
from modules.maps.gen import MapGenParams
from modules.maps.spec import MapSpec
from modules.maps.systems.map_generator import MapGeneratorSystem


class _DummyBus:
    def __init__(self) -> None:
        self.subscribers = defaultdict(list)
        self.published: list[tuple[str, dict[str, object]]] = []

    def subscribe(self, event_type: str, callback) -> None:
        self.subscribers[event_type].append(callback)

    def publish(self, event_type: str, **payload: object) -> None:
        self.published.append((event_type, payload))
        for callback in self.subscribers.get(event_type, []):
            callback(**payload)


def test_map_generator_system_emits_map_generated_event():
    bus = _DummyBus()
    MapGeneratorSystem(event_bus=bus)

    params = MapGenParams(
        size="xs",
        biome="forest",
        decor_density="mid",
        cover_ratio=0.1,
        hazard_ratio=0.0,
        difficult_ratio=0.0,
        chokepoint_limit=0.2,
        room_count=None,
        corridor_width=(1, 2),
        symmetry="none",
        seed=7,
    )

    for callback in bus.subscribers[GenerateMap.topic]:
        callback(params=params)

    generated_events = [payload for event, payload in bus.published if event == MapGenerated.topic]
    assert generated_events, "Expected a MapGenerated event"
    spec = generated_events[-1]["spec"]
    assert isinstance(spec, MapSpec)
    assert spec.meta.biome == params.biome
    assert spec.width == MapGenParams.SIZE_DIMENSIONS[params.size][0]

