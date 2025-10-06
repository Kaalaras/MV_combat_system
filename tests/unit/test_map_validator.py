from modules.maps.components import MapMeta
from modules.maps.gen.spawns import assign_spawn_zones
from modules.maps.gen.validate import MapValidator, ensure_valid_map
from modules.maps.spec import MapSpec


def _chokepoint_map() -> MapSpec:
    width, height = 9, 5
    cells = [["wall" for _ in range(width)] for _ in range(height)]
    # Carve left room
    for y in range(1, height - 1):
        for x in range(1, 3):
            cells[y][x] = "floor"
    # Carve right room
    for y in range(1, height - 1):
        for x in range(width - 3, width - 1):
            cells[y][x] = "floor"
    # Single tile corridor connecting rooms
    corridor_x = width // 2
    for y in range(1, height - 1):
        if y == height // 2:
            cells[y][corridor_x] = "floor"
        else:
            cells[y][corridor_x] = "wall"
    meta = MapMeta(name="chokepoint", biome="forest", seed=0)
    return MapSpec(width=width, height=height, cell_size=1, meta=meta, cells=cells)


def test_validator_widens_single_chokepoint():
    spec = _chokepoint_map()
    assign_spawn_zones(spec, enforce_fairness=False)
    validator = MapValidator(spec)
    assert not validator.is_valid()
    spec = ensure_valid_map(
        spec,
        reassign_spawns=lambda current: assign_spawn_zones(current, enforce_fairness=False),
    )
    validator = MapValidator(spec)
    assert validator.is_valid()
    # Ensure corridor widened: there should be at least two adjacent floor tiles across the choke.
    mid_y = spec.height // 2
    corridor_x = spec.width // 2
    assert spec.cells[mid_y][corridor_x] == "floor"
    assert (
        spec.cells[mid_y - 1][corridor_x] == "floor"
        or spec.cells[mid_y + 1][corridor_x] == "floor"
    )


def test_validator_detects_chokepoint_for_larger_footprints():
    spec = _chokepoint_map()
    assign_spawn_zones(spec, footprint=(2, 2), enforce_fairness=False)
    validator = MapValidator(spec)
    assert not validator.is_valid()
    spec = ensure_valid_map(
        spec,
        reassign_spawns=lambda current: assign_spawn_zones(
            current, footprint=(2, 2), enforce_fairness=False
        ),
    )
    validator = MapValidator(spec)
    assert validator.is_valid()
    mid_y = spec.height // 2
    corridor_x = spec.width // 2
    assert spec.cells[mid_y][corridor_x] == "floor"
    assert (
        spec.cells[mid_y - 1][corridor_x] == "floor"
        or spec.cells[mid_y + 1][corridor_x] == "floor"
    )
    assert any(
        spec.cells[row][corridor_x] == "floor" and spec.cells[row + 1][corridor_x] == "floor"
        for row in range(mid_y - 1, mid_y + 1)
        if 0 <= row < spec.height - 1
    )
