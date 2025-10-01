"""Body footprint component.

This component describes the footprint occupied by an entity relative to its
anchor position.  It provides the data used by occupancy helpers to expand the
footprint into concrete grid coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Iterable, Iterator, Tuple

Offset = Tuple[int, int]


@dataclass(frozen=True)
class BodyFootprintComponent:
    """Relative offsets describing the occupied tiles for an entity."""

    cells: FrozenSet[Offset] = field(default_factory=lambda: frozenset({(0, 0)}))

    def __post_init__(self) -> None:
        """Validate offsets without mutating the frozen dataclass."""

        for offset in self.cells:
            if len(offset) != 2:
                raise ValueError("Each footprint offset must contain exactly two coordinates")
            x, y = offset
            if not isinstance(x, int) or not isinstance(y, int):
                raise TypeError("Footprint offsets must be integer coordinates")

    @classmethod
    def from_size(cls, width: int, height: int) -> "BodyFootprintComponent":
        """Construct a rectangular footprint covering ``width`` x ``height`` cells."""

        if width <= 0 or height <= 0:
            raise ValueError("Body footprint dimensions must be positive integers")
        return cls(
            frozenset((dx, dy) for dx in range(int(width)) for dy in range(int(height)))
        )

    def iter_offsets(self) -> Iterator[Offset]:
        """Yield the relative offsets for the occupied tiles."""

        return iter(self.cells)

    def expand(self, anchor_x: int, anchor_y: int) -> FrozenSet[Offset]:
        """Return absolute tile coordinates for the given anchor position."""

        return frozenset((anchor_x + dx, anchor_y + dy) for dx, dy in self.cells)


__all__ = ["BodyFootprintComponent", "Offset"]

