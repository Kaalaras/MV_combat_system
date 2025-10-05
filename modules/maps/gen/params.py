"""User-facing parameters for procedural map generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Literal

MapSize = Literal["xs", "s", "m", "l", "xl"]
MapBiome = Literal[
    "building",
    "forest",
    "junkyard",
    "construction",
    "urban_dense",
    "urban_sparse",
]
DecorDensity = Literal["low", "mid", "high"]
MapSymmetry = Literal["none", "mirror_x", "mirror_y", "rot_180"]


@dataclass(slots=True)
class MapGenParams:
    """Configuration bundle describing the desired characteristics of a map."""

    #: Mapping from size labels to concrete ``(width, height)`` dimensions.
    SIZE_DIMENSIONS: ClassVar[dict[MapSize, tuple[int, int]]] = {
        "xs": (16, 16),
        "s": (24, 24),
        "m": (32, 32),
        "l": (40, 40),
        "xl": (48, 48),
    }

    size: MapSize
    biome: MapBiome
    decor_density: DecorDensity
    cover_ratio: float
    hazard_ratio: float
    difficult_ratio: float
    chokepoint_limit: float
    room_count: int | None
    corridor_width: tuple[int, int]
    symmetry: MapSymmetry
    seed: int | None = None
    dimensions: tuple[int, int] = field(init=False)

    def __post_init__(self) -> None:
        try:
            dimensions = self.SIZE_DIMENSIONS[self.size]
        except KeyError as exc:  # pragma: no cover - invalid size should be caught by type system
            raise ValueError(f"unknown map size '{self.size}'") from exc

        min_corridor, max_corridor = self.corridor_width
        if min_corridor <= 0 or max_corridor <= 0:
            raise ValueError("corridor widths must be positive")
        if min_corridor > max_corridor:
            raise ValueError("corridor width range must be increasing")

        for field_name, value in (
            ("cover_ratio", self.cover_ratio),
            ("hazard_ratio", self.hazard_ratio),
            ("difficult_ratio", self.difficult_ratio),
            ("chokepoint_limit", self.chokepoint_limit),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must lie between 0 and 1")

        if self.room_count is not None and self.room_count <= 0:
            raise ValueError("room_count must be positive when provided")

        object.__setattr__(self, "dimensions", dimensions)

    @property
    def width(self) -> int:
        """Return the generated map width derived from :attr:`size`."""

        return self.dimensions[0]

    @property
    def height(self) -> int:
        """Return the generated map height derived from :attr:`size`."""

        return self.dimensions[1]
