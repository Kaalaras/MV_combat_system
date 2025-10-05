"""Conventions partagées pour la lecture des cartes Tiled (TMX/TSX)."""
from __future__ import annotations

from typing import Any, Final, Mapping

from modules.maps.terrain_types import HazardTiming, TerrainFlags


TILED_KEYS: Final[dict[str, Mapping[str, str]]] = {
    "tile_layers": {
        "collision": "layer.collision",
        "terrain": "layer.terrain",
        "hazard": "layer.hazard",
        "cover": "layer.cover",
    },
    "object_layers": {
        "props": "objects.props",
        "walls": "objects.walls",
        "doors": "objects.doors",
    },
    "properties": {
        "move_cost": "move_cost",
        "blocks_move": "blocks_move",
        "blocks_los": "blocks_los",
        "cover": "cover",
        "hazard": "hazard",
        "hazard_timing": "hazard_timing",
    },
}

TILED_DEFAULTS: Final[dict[str, Any]] = {
    "move_cost": 1,
    "blocks_move": False,
    "blocks_los": False,
    "cover": "none",
    "hazard": "none",
    "hazard_timing": "on_enter",
}


_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}

_COVER_FLAGS: Final[dict[str, TerrainFlags]] = {
    "none": TerrainFlags(0),
    "light": TerrainFlags.COVER_LIGHT,
    "heavy": TerrainFlags.COVER_HEAVY,
    "fortification": TerrainFlags.COVER_HEAVY | TerrainFlags.FORTIFICATION,
}

_HAZARD_SPECS: Final[dict[str, tuple[TerrainFlags, int]]] = {
    "none": (TerrainFlags(0), 0),
    "dangerous": (TerrainFlags.HAZARDOUS, 5),
    "very_dangerous": (
        TerrainFlags.HAZARDOUS | TerrainFlags.VERY_HAZARDOUS,
        10,
    ),
}

_HAZARD_TIMINGS: Final[set[HazardTiming]] = {"on_enter", "end_of_turn", "per_tile"}


def parse_move_cost(value: Any, *, default: int | None = None) -> int:
    """Normalise la valeur ``move_cost`` en entier positif."""

    if value is None:
        if default is not None:
            return parse_move_cost(default, default=None)
        return TILED_DEFAULTS["move_cost"]

    if isinstance(value, bool):
        raise ValueError("move_cost ne peut pas être un booléen")

    if isinstance(value, (int, float)):
        cost = int(value)
    else:
        value_str = str(value).strip()
        if not value_str:
            return TILED_DEFAULTS["move_cost"]
        cost = int(value_str)

    if cost < 0:
        raise ValueError("move_cost doit être >= 0")
    return cost


def parse_bool_flag(value: Any, *, default: bool) -> bool:
    """Convertit une propriété booléenne Tiled en bool Python."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    value_str = str(value).strip().lower()
    if value_str in _BOOL_TRUE:
        return True
    if value_str in _BOOL_FALSE:
        return False
    raise ValueError(f"valeur booléenne invalide: {value!r}")


def parse_cover_str(value: Any) -> TerrainFlags:
    """Mappe la propriété ``cover`` vers les :class:`TerrainFlags` correspondants."""

    if value is None:
        key = "none"
    else:
        key = str(value).strip().lower()
        if not key:
            key = "none"
    try:
        return _COVER_FLAGS[key]
    except KeyError as exc:
        raise ValueError(f"cover inconnu: {value!r}") from exc


def parse_hazard_str(value: Any) -> tuple[TerrainFlags, int]:
    """Mappe la propriété ``hazard`` vers flags + dégâts."""

    if value is None:
        key = "none"
    else:
        key = str(value).strip().lower()
        if not key:
            key = "none"
    try:
        return _HAZARD_SPECS[key]
    except KeyError as exc:
        raise ValueError(f"hazard inconnu: {value!r}") from exc


def parse_hazard_timing(value: Any) -> HazardTiming:
    """Valide la propriété ``hazard_timing`` et retourne le libellé normalisé."""

    if value is None:
        return TILED_DEFAULTS["hazard_timing"]
    timing = str(value).strip().lower()
    if not timing:
        return TILED_DEFAULTS["hazard_timing"]
    if timing not in _HAZARD_TIMINGS:
        raise ValueError(f"hazard_timing inconnu: {value!r}")
    return timing  # type: ignore[return-value]


def apply_tile_defaults(properties: Mapping[str, Any]) -> dict[str, Any]:
    """Retourne un dict de propriétés complété avec les valeurs de repli."""

    resolved: dict[str, Any] = {}
    for key, default_value in TILED_DEFAULTS.items():
        resolved[key] = properties.get(key, default_value)
    return resolved


__all__ = [
    "TILED_KEYS",
    "TILED_DEFAULTS",
    "parse_move_cost",
    "parse_bool_flag",
    "parse_cover_str",
    "parse_hazard_str",
    "parse_hazard_timing",
    "apply_tile_defaults",
]
