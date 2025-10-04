"""Terrain flag definitions and descriptors for map tiles."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag, auto
from typing import Dict, Iterable, Literal, Optional


class TerrainFlags(IntFlag):
    """Bitflags representing the various terrain effects."""

    BLOCKS_MOVE = auto()
    BLOCKS_LOS = auto()
    COVER_LIGHT = auto()
    COVER_HEAVY = auto()
    FORTIFICATION = auto()
    DIFFICULT = auto()
    VERY_DIFFICULT = auto()
    HAZARDOUS = auto()
    VERY_HAZARDOUS = auto()
    IMPASSABLE = auto()
    WALL = auto()
    VOID = auto()


HazardTiming = Literal["on_enter", "end_of_turn", "per_tile"]


@dataclass(frozen=True)
class TerrainDescriptor:
    """Describes the gameplay characteristics of a terrain type."""

    name: str
    flags: TerrainFlags
    move_cost: Optional[int]
    hazard_damage: int = 0
    hazard_timing: HazardTiming = "on_enter"

    def __post_init__(self) -> None:
        if self.move_cost is None and not (self.flags & TerrainFlags.IMPASSABLE):
            raise ValueError("move_cost must be specified unless terrain is impassable")
        if self.move_cost is not None and self.move_cost < 0:
            raise ValueError("move_cost must be non-negative or None")
        if self.hazard_damage < 0:
            raise ValueError("hazard_damage cannot be negative")


# Catalog of basic terrain descriptors available in the system.
TERRAIN_CATALOG: Dict[str, TerrainDescriptor] = {
    "floor": TerrainDescriptor(
        name="floor",
        flags=TerrainFlags(0),
        move_cost=1,
    ),
    "difficult": TerrainDescriptor(
        name="difficult",
        flags=TerrainFlags.DIFFICULT,
        move_cost=2,
    ),
    "very_difficult": TerrainDescriptor(
        name="very_difficult",
        flags=TerrainFlags.DIFFICULT | TerrainFlags.VERY_DIFFICULT,
        move_cost=3,
    ),
    "light_cover": TerrainDescriptor(
        name="light_cover",
        flags=TerrainFlags.COVER_LIGHT | TerrainFlags.BLOCKS_LOS,
        move_cost=1,
    ),
    "heavy_cover": TerrainDescriptor(
        name="heavy_cover",
        flags=TerrainFlags.COVER_HEAVY | TerrainFlags.BLOCKS_LOS,
        move_cost=1,
    ),
    "fortification": TerrainDescriptor(
        name="fortification",
        flags=(
            TerrainFlags.COVER_HEAVY
            | TerrainFlags.FORTIFICATION
            | TerrainFlags.BLOCKS_LOS
        ),
        move_cost=1,
    ),
    "hazard": TerrainDescriptor(
        name="hazard",
        flags=TerrainFlags.HAZARDOUS,
        move_cost=1,
        hazard_damage=5,
        hazard_timing="on_enter",
    ),
    "hazard_severe": TerrainDescriptor(
        name="hazard_severe",
        flags=TerrainFlags.VERY_HAZARDOUS | TerrainFlags.HAZARDOUS,
        move_cost=1,
        hazard_damage=10,
        hazard_timing="per_tile",
    ),
    "wall": TerrainDescriptor(
        name="wall",
        flags=(
            TerrainFlags.WALL
            | TerrainFlags.BLOCKS_MOVE
            | TerrainFlags.BLOCKS_LOS
            | TerrainFlags.IMPASSABLE
        ),
        move_cost=None,
    ),
    "void": TerrainDescriptor(
        name="void",
        flags=(
            TerrainFlags.VOID
            | TerrainFlags.BLOCKS_MOVE
            | TerrainFlags.BLOCKS_LOS
            | TerrainFlags.IMPASSABLE
        ),
        move_cost=None,
    ),
}


_HAZARD_TIMING_PRIORITY = {
    "on_enter": 0,
    "end_of_turn": 1,
    "per_tile": 2,
}


def _merge_hazard_timing(a: HazardTiming, b: HazardTiming) -> HazardTiming:
    if _HAZARD_TIMING_PRIORITY[a] >= _HAZARD_TIMING_PRIORITY[b]:
        return a
    return b


def combine(*names: str) -> TerrainDescriptor:
    """Combine multiple terrain descriptors by name into a new descriptor."""

    if not names:
        raise ValueError("at least one terrain name must be provided")

    descriptors: Iterable[TerrainDescriptor] = (
        TERRAIN_CATALOG[name] for name in names
    )

    combined_flags = TerrainFlags(0)
    move_cost: Optional[int] = None
    hazard_damage: int = 0
    hazard_timing: HazardTiming = "on_enter"

    for descriptor in descriptors:
        combined_flags |= descriptor.flags

        if descriptor.move_cost is None or combined_flags & TerrainFlags.IMPASSABLE:
            move_cost = None
        elif move_cost is None:
            move_cost = descriptor.move_cost
        else:
            move_cost = max(move_cost, descriptor.move_cost)

        hazard_damage = max(hazard_damage, descriptor.hazard_damage)
        hazard_timing = _merge_hazard_timing(hazard_timing, descriptor.hazard_timing)

    if combined_flags & TerrainFlags.IMPASSABLE:
        move_cost = None

    name = "+".join(names)
    return TerrainDescriptor(
        name=name,
        flags=combined_flags,
        move_cost=move_cost,
        hazard_damage=hazard_damage,
        hazard_timing=hazard_timing,
    )


__all__ = [
    "TerrainFlags",
    "TerrainDescriptor",
    "TERRAIN_CATALOG",
    "combine",
]
