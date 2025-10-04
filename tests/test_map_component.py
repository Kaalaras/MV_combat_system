"""Tests for the map ECS component structures."""
from modules.maps.components import MapComponent, MapGrid, MapMeta
from modules.maps.terrain_types import TERRAIN_CATALOG, TerrainFlags


def test_map_component_entity_creation():
    grid = MapGrid(width=3, height=2, cell_size=1)
    meta = MapMeta(name="Test Map", biome="forest", seed=42)
    component = MapComponent(grid=grid, meta=meta)

    # Using the fallback ECS world from ECSManager ensures the component can
    # be attached to an entity without requiring external dependencies.
    from ecs.ecs_manager import ECSManager

    ecs_manager = ECSManager()
    entity_id = ecs_manager.world.create_entity(component)

    stored_component = ecs_manager.world.component_for_entity(entity_id, MapComponent)
    assert stored_component is component


def test_map_grid_set_and_get_cell_data():
    grid = MapGrid(width=2, height=2, cell_size=1)

    wall_descriptor = TERRAIN_CATALOG["wall"]
    floor_descriptor = TERRAIN_CATALOG["floor"]
    hazard_descriptor = TERRAIN_CATALOG["hazard"]

    # Coordinates beyond the grid should clamp to the closest valid cell.
    grid.set_cell(5, 5, wall_descriptor)
    assert grid.get_flags(5, 5) == wall_descriptor.flags
    assert grid.blocks_movement(5, 5) is True
    assert grid.blocks_los(5, 5) is True
    assert grid.get_move_cost(5, 5) == 0  # Impassable terrain

    grid.set_cell(0, 1, hazard_descriptor)
    assert grid.get_hazard_damage(0, 1) == hazard_descriptor.hazard_damage
    assert grid.blocks_movement(0, 1) is False

    grid.set_cell(-1, -1, floor_descriptor)
    assert grid.get_flags(-10, -10) == TerrainFlags(0)
    assert grid.blocks_movement(-10, -10) is False
    assert grid.blocks_los(-10, -10) is False
    assert grid.get_move_cost(-10, -10) == floor_descriptor.move_cost


def test_grid_initialises_from_existing_data_without_aliasing():
    flags = [[int(TerrainFlags.BLOCKS_MOVE)]]
    grid = MapGrid(width=1, height=1, cell_size=1, flags=flags)

    flags[0][0] = 0
    assert grid.get_flags(0, 0) == TerrainFlags.BLOCKS_MOVE
