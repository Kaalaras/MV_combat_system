"""Biome-specific decoration profiles used by the map decorator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

from modules.maps.gen.params import DecorDensity, MapBiome
from modules.maps.terrain_types import HazardTiming


CoverZone = str


@dataclass(frozen=True)
class BiomeDecorRules:
    """Configuration bundle describing decoration behaviour for a biome."""

    #: Relative importance of each cover placement zone per density level.
    cover_zone_weights: Mapping[DecorDensity, Mapping[CoverZone, float]]
    #: Cover type weights for each zone (e.g. edge, corridor, open).
    cover_type_weights: Mapping[CoverZone, Mapping[str, float]]
    #: Preferred zones when converting ground to difficult terrain.
    difficult_zone_weights: Mapping[DecorDensity, Mapping[str, float]]
    #: Relative weights for difficult vs. very difficult terrain selections.
    difficult_type_weights: Mapping[str, float]
    #: Relative weights for the available hazard descriptors.
    hazard_type_weights: Mapping[str, float]
    #: Inclusive range for the size of hazard pockets depending on density.
    hazard_cluster_size: Mapping[DecorDensity, tuple[int, int]]
    #: Preferred timing for hazards associated with the biome.
    hazard_timing: HazardTiming


def _normalise(weights: Mapping[str, float]) -> dict[str, float]:
    """Return a new dictionary with all weights coerced to ``float`` values."""

    normalised: MutableMapping[str, float] = {}
    for key, value in weights.items():
        weight = float(value)
        if weight < 0:
            raise ValueError("weights must be non-negative")
        normalised[key] = weight
    return dict(normalised)


# Biome-specific decoration rules.  These weights were tuned manually to provide
# a distinct flavour to each biome while keeping the logic reasonably simple.
_BIOME_RULES: Mapping[MapBiome, BiomeDecorRules] = {
    "building": BiomeDecorRules(
        cover_zone_weights={
            "low": _normalise({"edge": 0.85, "corridor": 0.05, "open": 0.10}),
            "mid": _normalise({"edge": 0.7, "corridor": 0.15, "open": 0.15}),
            "high": _normalise({"edge": 0.55, "corridor": 0.2, "open": 0.25}),
        },
        cover_type_weights={
            "edge": _normalise({"light_cover": 0.55, "heavy_cover": 0.3, "fortification": 0.15}),
            "corridor": _normalise({"light_cover": 0.75, "heavy_cover": 0.2, "fortification": 0.05}),
            "open": _normalise({"light_cover": 0.65, "heavy_cover": 0.25, "fortification": 0.10}),
        },
        difficult_zone_weights={
            "low": _normalise({"secondary": 0.7, "corridor": 0.2, "room": 0.1}),
            "mid": _normalise({"secondary": 0.6, "corridor": 0.25, "room": 0.15}),
            "high": _normalise({"secondary": 0.5, "corridor": 0.3, "room": 0.2}),
        },
        difficult_type_weights=_normalise({"difficult": 0.8, "very_difficult": 0.2}),
        hazard_type_weights=_normalise({"hazard": 0.75, "hazard_severe": 0.25}),
        hazard_cluster_size={
            "low": (2, 3),
            "mid": (3, 4),
            "high": (3, 5),
        },
        hazard_timing="on_enter",
    ),
    "forest": BiomeDecorRules(
        cover_zone_weights={
            "low": _normalise({"edge": 0.6, "corridor": 0.1, "open": 0.3}),
            "mid": _normalise({"edge": 0.5, "corridor": 0.15, "open": 0.35}),
            "high": _normalise({"edge": 0.4, "corridor": 0.2, "open": 0.4}),
        },
        cover_type_weights={
            "edge": _normalise({"light_cover": 0.7, "heavy_cover": 0.2, "fortification": 0.1}),
            "corridor": _normalise({"light_cover": 0.8, "heavy_cover": 0.15, "fortification": 0.05}),
            "open": _normalise({"light_cover": 0.75, "heavy_cover": 0.2, "fortification": 0.05}),
        },
        difficult_zone_weights={
            "low": _normalise({"secondary": 0.65, "corridor": 0.2, "room": 0.15}),
            "mid": _normalise({"secondary": 0.55, "corridor": 0.25, "room": 0.2}),
            "high": _normalise({"secondary": 0.45, "corridor": 0.3, "room": 0.25}),
        },
        difficult_type_weights=_normalise({"difficult": 0.6, "very_difficult": 0.4}),
        hazard_type_weights=_normalise({"hazard": 0.65, "hazard_severe": 0.35}),
        hazard_cluster_size={
            "low": (2, 4),
            "mid": (3, 5),
            "high": (4, 6),
        },
        hazard_timing="on_enter",
    ),
    "junkyard": BiomeDecorRules(
        cover_zone_weights={
            "low": _normalise({"edge": 0.7, "corridor": 0.1, "open": 0.2}),
            "mid": _normalise({"edge": 0.55, "corridor": 0.2, "open": 0.25}),
            "high": _normalise({"edge": 0.45, "corridor": 0.25, "open": 0.3}),
        },
        cover_type_weights={
            "edge": _normalise({"light_cover": 0.4, "heavy_cover": 0.4, "fortification": 0.2}),
            "corridor": _normalise({"light_cover": 0.55, "heavy_cover": 0.35, "fortification": 0.1}),
            "open": _normalise({"light_cover": 0.5, "heavy_cover": 0.35, "fortification": 0.15}),
        },
        difficult_zone_weights={
            "low": _normalise({"secondary": 0.6, "corridor": 0.25, "room": 0.15}),
            "mid": _normalise({"secondary": 0.5, "corridor": 0.3, "room": 0.2}),
            "high": _normalise({"secondary": 0.4, "corridor": 0.35, "room": 0.25}),
        },
        difficult_type_weights=_normalise({"difficult": 0.7, "very_difficult": 0.3}),
        hazard_type_weights=_normalise({"hazard": 0.55, "hazard_severe": 0.45}),
        hazard_cluster_size={
            "low": (2, 3),
            "mid": (3, 4),
            "high": (4, 5),
        },
        hazard_timing="end_of_turn",
    ),
    "construction": BiomeDecorRules(
        cover_zone_weights={
            "low": _normalise({"edge": 0.65, "corridor": 0.15, "open": 0.2}),
            "mid": _normalise({"edge": 0.55, "corridor": 0.2, "open": 0.25}),
            "high": _normalise({"edge": 0.45, "corridor": 0.25, "open": 0.3}),
        },
        cover_type_weights={
            "edge": _normalise({"light_cover": 0.45, "heavy_cover": 0.35, "fortification": 0.2}),
            "corridor": _normalise({"light_cover": 0.55, "heavy_cover": 0.3, "fortification": 0.15}),
            "open": _normalise({"light_cover": 0.5, "heavy_cover": 0.3, "fortification": 0.2}),
        },
        difficult_zone_weights={
            "low": _normalise({"secondary": 0.55, "corridor": 0.3, "room": 0.15}),
            "mid": _normalise({"secondary": 0.45, "corridor": 0.35, "room": 0.2}),
            "high": _normalise({"secondary": 0.35, "corridor": 0.4, "room": 0.25}),
        },
        difficult_type_weights=_normalise({"difficult": 0.65, "very_difficult": 0.35}),
        hazard_type_weights=_normalise({"hazard": 0.6, "hazard_severe": 0.4}),
        hazard_cluster_size={
            "low": (2, 3),
            "mid": (3, 4),
            "high": (4, 6),
        },
        hazard_timing="end_of_turn",
    ),
    "urban_dense": BiomeDecorRules(
        cover_zone_weights={
            "low": _normalise({"edge": 0.8, "corridor": 0.1, "open": 0.1}),
            "mid": _normalise({"edge": 0.65, "corridor": 0.2, "open": 0.15}),
            "high": _normalise({"edge": 0.5, "corridor": 0.25, "open": 0.25}),
        },
        cover_type_weights={
            "edge": _normalise({"light_cover": 0.35, "heavy_cover": 0.4, "fortification": 0.25}),
            "corridor": _normalise({"light_cover": 0.45, "heavy_cover": 0.35, "fortification": 0.2}),
            "open": _normalise({"light_cover": 0.4, "heavy_cover": 0.35, "fortification": 0.25}),
        },
        difficult_zone_weights={
            "low": _normalise({"secondary": 0.5, "corridor": 0.3, "room": 0.2}),
            "mid": _normalise({"secondary": 0.45, "corridor": 0.35, "room": 0.2}),
            "high": _normalise({"secondary": 0.35, "corridor": 0.4, "room": 0.25}),
        },
        difficult_type_weights=_normalise({"difficult": 0.55, "very_difficult": 0.45}),
        hazard_type_weights=_normalise({"hazard": 0.5, "hazard_severe": 0.5}),
        hazard_cluster_size={
            "low": (2, 3),
            "mid": (3, 4),
            "high": (4, 5),
        },
        hazard_timing="per_tile",
    ),
    "urban_sparse": BiomeDecorRules(
        cover_zone_weights={
            "low": _normalise({"edge": 0.75, "corridor": 0.1, "open": 0.15}),
            "mid": _normalise({"edge": 0.65, "corridor": 0.15, "open": 0.2}),
            "high": _normalise({"edge": 0.55, "corridor": 0.2, "open": 0.25}),
        },
        cover_type_weights={
            "edge": _normalise({"light_cover": 0.6, "heavy_cover": 0.3, "fortification": 0.1}),
            "corridor": _normalise({"light_cover": 0.7, "heavy_cover": 0.2, "fortification": 0.1}),
            "open": _normalise({"light_cover": 0.65, "heavy_cover": 0.25, "fortification": 0.1}),
        },
        difficult_zone_weights={
            "low": _normalise({"secondary": 0.65, "corridor": 0.25, "room": 0.1}),
            "mid": _normalise({"secondary": 0.55, "corridor": 0.3, "room": 0.15}),
            "high": _normalise({"secondary": 0.45, "corridor": 0.35, "room": 0.2}),
        },
        difficult_type_weights=_normalise({"difficult": 0.85, "very_difficult": 0.15}),
        hazard_type_weights=_normalise({"hazard": 0.7, "hazard_severe": 0.3}),
        hazard_cluster_size={
            "low": (2, 3),
            "mid": (3, 4),
            "high": (3, 5),
        },
        hazard_timing="on_enter",
    ),
}


def get_biome_rules(biome: MapBiome) -> BiomeDecorRules:
    """Return the decoration rules associated with ``biome``.

    Parameters
    ----------
    biome:
        Identifier of the biome as provided by :class:`MapGenParams`.
    """

    try:
        return _BIOME_RULES[biome]
    except KeyError as exc:  # pragma: no cover - guarded by type checking in params
        raise ValueError(f"unknown biome '{biome}'") from exc


__all__ = ["BiomeDecorRules", "get_biome_rules"]

