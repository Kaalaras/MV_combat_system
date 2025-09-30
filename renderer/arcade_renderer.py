"""Arcade renderer for the grid-based combat demo."""

from __future__ import annotations

from typing import Optional

import arcade

from core.game_state import GameState


class ArcadeRenderer:
    """Responsible for drawing the combat demo using :mod:`arcade`."""

    def __init__(self, game_state: GameState):
        self._game_state = game_state

    def draw(self) -> None:
        """Render the current terrain, walls, and entities."""

        terrain = getattr(self._game_state, "terrain", None)
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
        for entity_id in self._game_state.entities:
            pos = terrain.get_entity_position(entity_id)
            if not pos:
                continue

            team = self._resolve_entity_team(entity_id)
            if team == "coterie":
                color = arcade.color.BLUE
            elif team == "rivals":
                color = arcade.color.RED
            else:
                color = arcade.color.LIGHT_GRAY

            arcade.draw_rectangle_filled(
                (pos[0] + 0.5) * terrain.cell_size,
                (pos[1] + 0.5) * terrain.cell_size,
                terrain.cell_size * 0.7,
                terrain.cell_size * 0.7,
                color,
            )

    def _resolve_entity_team(self, entity_id: str) -> Optional[str]:
        components = self._game_state.entities.get(entity_id, {})
        char_ref = components.get("character_ref")
        character = getattr(char_ref, "character", None) if char_ref else None
        return getattr(character, "team", None) if character else None
