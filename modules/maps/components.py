"""Map-related ECS components and supporting data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, TypeVar, Union

from modules.maps.terrain_types import TerrainDescriptor, TerrainFlags


IntGrid = List[List[int]]
BoolGrid = List[List[bool]]
_GridValue = TypeVar("_GridValue", int, bool)


@dataclass(slots=True)
class MapGrid:
    """Holds the terrain information for a rectangular map."""

    width: int
    height: int
    cell_size: int
    flags: IntGrid | None = None
    move_cost: IntGrid | None = None
    hazard_damage: IntGrid | None = None
    blocks_move_mask: BoolGrid | None = None
    blocks_los_mask: BoolGrid | None = None

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.cell_size <= 0:
            raise ValueError("cell_size must be positive")

        self.flags = self._ensure_grid(self.flags, 0)
        self.move_cost = self._ensure_grid(self.move_cost, 1)
        self.hazard_damage = self._ensure_grid(self.hazard_damage, 0)
        self.blocks_move_mask = self._ensure_grid(self.blocks_move_mask, False)
        self.blocks_los_mask = self._ensure_grid(self.blocks_los_mask, False)

    def _ensure_grid(
        self,
        grid: Union[IntGrid, BoolGrid, None],
        default: _GridValue,
    ) -> Union[IntGrid, BoolGrid]:
        if grid is None:
            return [
                [default for _ in range(self.width)]
                for _ in range(self.height)
            ]

        if len(grid) != self.height or any(len(row) != self.width for row in grid):
            raise ValueError("grid dimensions do not match width and height")

        converter = bool if isinstance(default, bool) else int
        return [
            [converter(value) for value in row]
            for row in grid
        ]

    def _clamp_coords(self, x: int, y: int) -> tuple[int, int]:
        clamped_x = min(max(x, 0), self.width - 1)
        clamped_y = min(max(y, 0), self.height - 1)
        return clamped_x, clamped_y

    def in_bounds(self, x: int, y: int) -> bool:
        """Return ``True`` when ``(x, y)`` lies within the grid bounds."""

        return 0 <= x < self.width and 0 <= y < self.height

    def get_flags(self, x: int, y: int) -> TerrainFlags:
        """Return the terrain flags at the requested coordinates."""

        cx, cy = self._clamp_coords(x, y)
        return TerrainFlags(self.flags[cy][cx])

    def get_move_cost(self, x: int, y: int) -> int:
        """Retrieve the movement cost of a tile, clamping out-of-range indices."""

        cx, cy = self._clamp_coords(x, y)
        return self.move_cost[cy][cx]

    def get_hazard_damage(self, x: int, y: int) -> int:
        """Retrieve the hazard damage associated with a tile."""

        cx, cy = self._clamp_coords(x, y)
        return self.hazard_damage[cy][cx]

    def blocks_movement(self, x: int, y: int) -> bool:
        """Return whether the tile blocks movement."""

        cx, cy = self._clamp_coords(x, y)
        return self.blocks_move_mask[cy][cx]

    def blocks_los(self, x: int, y: int) -> bool:
        """Return whether the tile blocks line of sight."""

        cx, cy = self._clamp_coords(x, y)
        return self.blocks_los_mask[cy][cx]

    def set_cell(self, x: int, y: int, descriptor: TerrainDescriptor) -> None:
        """Write terrain data for the requested coordinates."""

        cx, cy = self._clamp_coords(x, y)
        flags_value = int(descriptor.flags)
        blocks_move = bool(
            descriptor.flags
            & (TerrainFlags.BLOCKS_MOVE | TerrainFlags.IMPASSABLE | TerrainFlags.VOID)
        )
        blocks_los = bool(descriptor.flags & TerrainFlags.BLOCKS_LOS)

        self.flags[cy][cx] = flags_value
        self.move_cost[cy][cx] = descriptor.move_cost or 0
        self.hazard_damage[cy][cx] = descriptor.hazard_damage
        self.blocks_move_mask[cy][cx] = blocks_move
        self.blocks_los_mask[cy][cx] = blocks_los


@dataclass(slots=True)
class SpawnZone:
    """Represents a deployment area used as a spawn location."""

    label: str
    position: Tuple[int, int]
    footprint: Tuple[int, int] = (1, 1)
    safe_radius: int = 1
    allow_decor: bool = False
    allow_hazard: bool = False

    def clone(self) -> "SpawnZone":
        """Return a shallow copy of the spawn zone."""

        return SpawnZone(
            label=self.label,
            position=self.position,
            footprint=self.footprint,
            safe_radius=self.safe_radius,
            allow_decor=self.allow_decor,
            allow_hazard=self.allow_hazard,
        )


@dataclass(slots=True)
class MapMeta:
    """Metadata describing a map instance."""

    name: str
    biome: str
    seed: int | None = None
    spawn_zones: Dict[str, SpawnZone] = field(default_factory=dict)


@dataclass(slots=True)
class MapComponent:
    """ECS component storing a map grid and its metadata."""

    grid: MapGrid
    meta: MapMeta


__all__ = ["MapGrid", "MapMeta", "MapComponent", "SpawnZone"]

