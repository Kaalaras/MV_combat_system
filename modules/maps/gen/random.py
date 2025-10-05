"""Deterministic random utilities dedicated to map generation."""
from __future__ import annotations

import random
from typing import MutableSequence, Sequence, TypeVar

_T = TypeVar("_T")


def get_rng(seed: int | None = None) -> random.Random:
    """Return a :class:`random.Random` instance optionally seeded."""

    rng = random.Random()
    if seed is not None:
        rng.seed(seed)
    return rng


def rand_choice(rng: random.Random, sequence: Sequence[_T]) -> _T:
    """Return a random element from ``sequence`` using ``rng``."""

    if not sequence:
        raise IndexError("cannot choose from an empty sequence")
    return rng.choice(sequence)


def rand_int(rng: random.Random, start: int, stop: int) -> int:
    """Return a random integer ``N`` such that ``start <= N <= stop``."""

    return rng.randint(start, stop)


def shuffle(rng: random.Random, sequence: MutableSequence[_T]) -> None:
    """Shuffle ``sequence`` in-place using ``rng``."""

    rng.shuffle(sequence)
