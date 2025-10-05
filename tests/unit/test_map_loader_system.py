from core.event_bus import EventBus
from ecs.ecs_manager import ECSManager
from modules.maps.components import MapComponent, MapMeta
from modules.maps.events import MAP_LOADED, LoadMapFromTiled
from modules.maps.systems.map_loader import MapLoaderSystem, get_active_map


def test_load_map_from_tiled_creates_entity_and_emits_event():
    bus = EventBus()
    ecs_manager = ECSManager(event_bus=bus)
    loader = MapLoaderSystem(ecs_manager, event_bus=bus)

    captured: dict[str, object] = {}

    def _on_map_loaded(*, map_entity_id: str, meta: MapMeta, **_: object) -> None:
        captured["map_entity_id"] = map_entity_id
        captured["meta"] = meta

    bus.subscribe(MAP_LOADED, _on_map_loaded)

    LoadMapFromTiled("assets/maps/test.tmx").publish(bus)

    assert "map_entity_id" in captured
    assert "meta" in captured

    entity_id = captured["map_entity_id"]
    meta = captured["meta"]

    assert isinstance(entity_id, str)
    assert meta.name == "Test Map"
    assert meta.biome == "test_biome"

    component = ecs_manager.get_component_for_entity(entity_id, MapComponent)
    assert isinstance(component, MapComponent)
    assert component.grid.width == 2
    assert component.grid.height == 2

    active_id, active_component = loader.get_active_map()
    assert active_id == entity_id
    assert active_component is component

    helper_id, helper_component = get_active_map(ecs_manager)
    assert helper_id == entity_id
    assert helper_component is component
