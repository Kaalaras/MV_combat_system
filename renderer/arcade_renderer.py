"""Arcade renderer for the grid-based combat demo."""

from __future__ import annotations

from typing import Dict, Iterator, Optional, Set, Tuple, TYPE_CHECKING, Union

import arcade

from core.game_state import GameState
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.position import PositionComponent

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from core.terrain_manager import Terrain
    from ecs.ecs_manager import ECSManager


class _LegacyPosition:
    """Lightweight shim providing ``PositionComponent``-like attributes."""

    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x: int, y: int, width: int = 1, height: int = 1) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class ArcadeRenderer:
    """Responsible for drawing the combat demo using :mod:`arcade`."""

    def __init__(
        self,
        game_state: GameState,
        *,
        ecs_manager: Optional["ECSManager"] = None,
    ) -> None:
        self._game_state = game_state
        self._ecs_manager = ecs_manager or getattr(game_state, "ecs_manager", None)

    def draw(self) -> None:
        """Render the current terrain, walls, and entities."""

        terrain = self._game_state.terrain
        if terrain is None:
            return

        self._draw_grid()
        self._draw_walls()
        self._draw_entities()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _draw_grid(self) -> None:
        terrain = self._game_state.terrain
        cell = terrain.cell_size
        width_px = terrain.width * cell
        height_px = terrain.height * cell

        arcade.draw_lrtb_rectangle_filled(0, width_px, height_px, 0, arcade.color.ASH_GREY)

        for x in range(terrain.width + 1):
            px = x * cell
            arcade.draw_line(px, 0, px, height_px, arcade.color.DARK_SLATE_BLUE, 1)
        for y in range(terrain.height + 1):
            py = y * cell
            arcade.draw_line(0, py, width_px, py, arcade.color.DARK_SLATE_BLUE, 1)

    def _draw_walls(self) -> None:
        terrain = self._game_state.terrain
        for wall_x, wall_y in terrain.walls:
            arcade.draw_rectangle_filled(
                (wall_x + 0.5) * terrain.cell_size,
                (wall_y + 0.5) * terrain.cell_size,
                terrain.cell_size * 0.9,
                terrain.cell_size * 0.9,
                arcade.color.DARK_BROWN,
            )

    def _draw_entities(self) -> None:
        terrain = self._game_state.terrain
        if terrain is None:
            return

        cell = terrain.cell_size
        for _, position, team_id in self._iter_render_snapshots():
            width_cells = self._dimension_with_fallback(position, "width")
            height_cells = self._dimension_with_fallback(position, "height")

            center_x = (self._position_coord(position, "x") + width_cells / 2) * cell
            center_y = (self._position_coord(position, "y") + height_cells / 2) * cell
            width_px = width_cells * cell * 0.7
            height_px = height_cells * cell * 0.7

            arcade.draw_rectangle_filled(
                center_x,
                center_y,
                width_px,
                height_px,
                self._team_color(team_id),
            )

    def _resolve_entity_team(self, entity_id: str) -> Optional[str]:
        if self._ecs_manager:
            internal_id = self._ecs_manager.resolve_entity(entity_id)
            if internal_id is not None:
                char_ref = self._ecs_manager.try_get_component(
                    internal_id, CharacterRefComponent
                )
                character = getattr(char_ref, "character", None) if char_ref else None
                team = getattr(character, "team", None) if character else None
                if team is not None:
                    return str(team)

        components = self._game_state.entities.get(entity_id, {})
        char_ref = components.get("character_ref")
        character = getattr(char_ref, "character", None) if char_ref else None
        return getattr(character, "team", None) if character else None

    def _iter_render_snapshots(
        self,
    ) -> Iterator[Tuple[str, Union["PositionComponent", _LegacyPosition], Optional[str]]]:
        terrain = self._game_state.terrain
        if terrain is None:
            return iter(())

        return self._iter_render_snapshots_for_terrain(terrain)

    def _iter_render_snapshots_for_terrain(
        self,
        terrain: "Terrain",
    ) -> Iterator[Tuple[str, Union["PositionComponent", _LegacyPosition], Optional[str]]]:
        yielded: Set[str] = set()
        team_cache: Dict[str, Optional[str]] = {}

        if self._ecs_manager is not None:
            for entity_id, position in self._ecs_manager.iter_with_id(PositionComponent):
                if position is None:
                    continue
                team_id = self._get_cached_team_id(entity_id, team_cache)
                yielded.add(entity_id)
                yield entity_id, position, team_id

        for entity_id in self._game_state.entities:
            if entity_id in yielded:
                continue
            pos = terrain.get_entity_position(entity_id)
            if not pos:
                continue
            team_id = self._get_cached_team_id(entity_id, team_cache)
            yield entity_id, _LegacyPosition(pos[0], pos[1]), team_id

    def _team_color(self, team_id: Optional[str]) -> arcade.Color:
        if team_id == "coterie":
            return arcade.color.BLUE
        if team_id == "rivals":
            return arcade.color.RED
        return arcade.color.LIGHT_GRAY

    def _get_cached_team_id(
        self, entity_id: str, team_cache: Dict[str, Optional[str]]
    ) -> Optional[str]:
        team_id = team_cache.get(entity_id)
        if entity_id not in team_cache:
            team_id = self._resolve_entity_team(entity_id)
            team_cache[entity_id] = team_id
        return team_id

    @staticmethod
    def _dimension_with_fallback(
        position: Union["PositionComponent", _LegacyPosition], attr_name: str
    ) -> int:
        raw_value = getattr(position, attr_name, 1)
        if raw_value in (None, 0):
            return 1
        try:
            return max(int(raw_value), 1)
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _position_coord(
        position: Union["PositionComponent", _LegacyPosition], attr_name: str
    ) -> float:
        raw_value = getattr(position, attr_name, 0)
        if raw_value is None:
            return 0.0
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return 0.0
