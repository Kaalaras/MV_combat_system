"""Arcade Window Skeleton for Spectator View
==========================================

This module provides a minimal (optional) Arcade-based window integrating the new
UI stack and a SpectatorController. It is designed for manual debugging and is
NOT required for automated tests (tests avoid opening a graphical window).

Limitations
-----------
* The core GameSystem.run_game_loop is blocking. To allow the window to remain
  responsive, we run the simulation in a background thread.
* No attempt is made to gracefully pause/stop mid-loop; closing the window will
  simply exit the process (acceptable for debugging prototype).
* Drawing is placeholder text only; real rendering of grid/entities is future work.

Usage (external setup required)
-------------------------------
    from interface.arcade_app import SpectatorWindow, SimulationThread
    # External code must provide game_setup, spectator, ui_adapter, ui_manager
    window = SpectatorWindow(game_setup, spectator, ui_adapter, ui_manager)
    arcade.run()

Key Bindings
------------
TAB: Cycle spectator forward
SHIFT+TAB: Cycle spectator backward (not implemented yet)
0: Clear spectator viewpoint (free camera)
ESC: Close window
"""
from __future__ import annotations
import threading
import time
from typing import Optional

try:  # Arcade is optional for headless / CI
    import arcade  # type: ignore
except Exception:  # pragma: no cover
    arcade = None  # type: ignore

from interface.spectator import SpectatorController
from interface.ui_adapter import UIAdapter
from interface.ui_manager_v2 import UIManagerV2
from interface.event_constants import UIStateEvents, CoreEvents


class SimulationThread(threading.Thread):  # pragma: no cover - side effect oriented
    def __init__(self, game_system, max_rounds: int, *, event_bus=None, turn_delay: float = 0.6, action_delay: float = 0.25):
        super().__init__(daemon=True)
        self.game_system = game_system
        self.max_rounds = max_rounds
        self.turn_delay = turn_delay
        self.action_delay = action_delay
        self._event_bus = event_bus
        if event_bus:
            # Sleep briefly after turn start and action performed for visual pacing
            event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)
            event_bus.subscribe(CoreEvents.ACTION_PERFORMED, self._on_action)
            event_bus.subscribe(CoreEvents.ACTION_FAILED, self._on_action)

    def _on_turn_start(self, **_):
        if self.turn_delay > 0:
            time.sleep(self.turn_delay)

    def _on_action(self, **_):
        if self.action_delay > 0:
            time.sleep(self.action_delay)

    def run(self) -> None:  # blocking simulation
        self.game_system.run_game_loop(max_rounds=self.max_rounds)


class SpectatorWindow(arcade.Window):  # pragma: no cover - GUI
    """Minimal Arcade window focused solely on rendering and input delegation.

    Responsibilities:
    - Capture raw input events (keyboard, mouse)
    - Delegate input to InputManager for semantic processing
    - Render visual elements based on UIState snapshots
    - Handle window lifecycle (resize, update loop)

    Non-Responsibilities (delegated to other components):
    - Action validation (ActionSystem's job)
    - Game state modification (core systems' job)
    - UI state management (UIManagerV2's job)
    - Input interpretation (InputManager's job)
    """

    def __init__(self, game_setup: dict, spectator: SpectatorController, ui_adapter: UIAdapter, ui_manager: UIManagerV2):
        super().__init__(800, 600, "Combat System Spectator")

        # Core dependencies - only what we need for rendering and delegation
        self.game_setup = game_setup
        self.spectator = spectator
        self.ui_adapter = ui_adapter
        self.ui_manager = ui_manager

        # Create input manager for proper input handling
        from interface.input_manager import InputManager
        self.input_manager = InputManager(game_setup["event_bus"])

        # Rendering configuration
        self.cell_size = 32
        self.grid_origin_x = 10
        self.grid_origin_y = 130
        self.action_bar_height = 110

        # UX Point 5: Enhanced Camera system
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.camera_speed = 200.0
        self.camera_locked = True  # Camera lock on active character
        self.camera_follow_entity_id: Optional[str] = None  # Entity to follow when locked
        self.keys_pressed = set()

        # UX: Mouse edge scrolling
        self.edge_scroll_margin = 20  # Pixels from edge to trigger scroll
        self.edge_scroll_speed = 150.0
        self.mouse_at_edge = False

        # UX: Terrain centering
        self.terrain_centered_by_default = True
        self.free_camera_mode = False  # True when using key "0" for free camera

        # UI rendering state (not game logic state)
        self.text_objects = {}
        self.elapsed_time = 0.0
        # Cached text objects (avoid slow draw_text each frame)
        self._status_text_obj = None
        self._notification_text_objs = []  # list[arcade.Text]
        self._last_status_text = None
        self._last_notifications = []

        # Tooltip state
        self.hover_entity_id: Optional[str] = None
        self._hover_time: float = 0.0
        self._last_mouse: tuple[float, float] = (0.0, 0.0)
        self._force_tooltip: bool = False  # set by TAB for instant tooltip per spec

        # Texture cache for entity sprites
        self._texture_cache = {}

        # Subscribe only to state updates for rendering
        event_bus = game_setup["event_bus"]
        event_bus.subscribe(UIStateEvents.STATE_UPDATE, self._on_ui_state_update)

        self._center_camera_on_terrain()

    def _on_ui_state_update(self, state, **_):
        """React to UI state changes - rendering only."""
        # Update input manager context
        if state.active_entity_id:
            self.input_manager.set_active_entity(state.active_entity_id)

        # UI manager handles the heavy lifting
        self.ui_manager.update_state(state)

    # --- Input Delegation (no game logic here) ---
    def on_key_press(self, key, modifiers):
        """Delegate keyboard input to appropriate handlers."""
        # Window control
        if key == arcade.key.ESCAPE:
            arcade.close_window()
            return

        # Spectator controls
        if key == arcade.key.TAB:
            if modifiers & arcade.key.MOD_SHIFT:
                self.spectator.cycle_backward()
            else:
                # Also trigger instant tooltip display on current hover per UX spec
                self.spectator.cycle_forward()
                self._force_tooltip = True
            return

        if key == arcade.key.KEY_0:
            # UX Specification: Free camera mode
            self.spectator.clear_view()
            self.free_camera_mode = True
            self.camera_locked = False
            return

        if key == arcade.key.L:
            # UX Specification: Camera lock/unlock toggle
            self.camera_locked = not self.camera_locked
            if self.camera_locked and self.ui_manager.state.active_entity_id:
                # Lock onto active character
                self.camera_follow_entity_id = self.ui_manager.state.active_entity_id
            return

        # Action hotkeys - delegate to InputManager
        action_hotkeys = {
            arcade.key.M: "Standard Move",
            arcade.key.A: "Registered Attack",
            arcade.key.S: "Sprint",
            arcade.key.E: "End Turn"
        }

        if key in action_hotkeys:
            action_name = action_hotkeys[key]
            requires_target = action_name not in ("End Turn",)
            self.input_manager.handle_action_hotkey(action_name, requires_target=requires_target)
            return

        # UX: Enhanced camera controls - Arrow keys or WASD for panning
        camera_keys = {
            arcade.key.LEFT: arcade.key.LEFT,
            arcade.key.RIGHT: arcade.key.RIGHT,
            arcade.key.UP: arcade.key.UP,
            arcade.key.DOWN: arcade.key.DOWN,
            arcade.key.W: arcade.key.UP,
            arcade.key.A: arcade.key.LEFT,
            arcade.key.S: arcade.key.DOWN,
            arcade.key.D: arcade.key.RIGHT
        }

        if key in camera_keys:
            self.keys_pressed.add(camera_keys[key])
            # UX: Manual camera movement unlocks camera
            self.camera_locked = False
            self.free_camera_mode = True

    def on_key_release(self, key, modifiers):
        """Handle key releases for camera movement."""
        release_map = {
            arcade.key.LEFT: arcade.key.LEFT,
            arcade.key.RIGHT: arcade.key.RIGHT,
            arcade.key.UP: arcade.key.UP,
            arcade.key.DOWN: arcade.key.DOWN,
            arcade.key.W: arcade.key.UP,
            arcade.key.A: arcade.key.LEFT,
            arcade.key.S: arcade.key.DOWN,
            arcade.key.D: arcade.key.RIGHT
        }

        if key in release_map:
            self.keys_pressed.discard(release_map[key])

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Enhanced mouse motion handling with edge scrolling support."""
        self._last_mouse = (x, y)

        # UX Point 5: Mouse edge scrolling for free camera
        if not self.camera_locked and not self.free_camera_mode:
            self._handle_mouse_edge_detection(x, y)

        # Determine hovered entity (with automatic dead entity removal)
        cell = self._screen_to_grid(x, y)
        hovered = None
        if cell:
            cx, cy = cell
            game_state = self.game_setup["game_state"]

            # UX Point 5: Entity removal - dead entities automatically removed from map
            alive_entities = self._get_alive_entities_at_position(cx, cy, game_state)
            if alive_entities:
                hovered = alive_entities[0]  # Take first alive entity at position

        if hovered != self.hover_entity_id:
            self.hover_entity_id = hovered
            self._hover_time = 0.0
            self.ui_manager.set_hover_tooltip(None, 0, 0)
            self._force_tooltip = False

    def _handle_mouse_edge_detection(self, x: float, y: float) -> None:
        """Handle mouse edge detection for camera scrolling."""
        margin = self.edge_scroll_margin
        self.mouse_at_edge = (
            x < margin or x > self.width - margin or
            y < margin or y > self.height - margin
        )

    def _get_alive_entities_at_position(self, cx: int, cy: int, game_state) -> list[str]:
        """UX Point 5: Get only alive entities at a position (dead entities are filtered out)."""
        alive_entities = []

        for eid, ent in list(game_state.entities.items()):
            pos = ent.get("position")
            if not pos:
                continue

            # Get position coordinates
            if hasattr(pos, 'x') and hasattr(pos, 'y'):
                px, py = pos.x, pos.y
            else:
                try:
                    px, py = pos
                except Exception:
                    continue

            if px == cx and py == cy:
                # UX Specification: Dead entities automatically removed from the map
                cref = ent.get('character_ref')
                if cref and hasattr(cref, 'character'):
                    char = cref.character
                    if not getattr(char, 'is_dead', False):
                        alive_entities.append(eid)

        return alive_entities

    def _update_tooltip(self, dt: float):
        if not self.hover_entity_id:
            return
        self._hover_time += dt
        if self._hover_time >= 1.5 or self._force_tooltip:
            # Build tooltip lines
            game_state = self.game_setup["game_state"]
            ent = game_state.get_entity(self.hover_entity_id)
            lines = [self.hover_entity_id]
            if ent and 'character_ref' in ent:
                char = ent['character_ref'].character
                # Health
                max_h = getattr(char, 'max_health', None)
                dmg = getattr(char, '_health_damage', {}) if hasattr(char, '_health_damage') else {}
                if max_h is not None and isinstance(dmg, dict):
                    sup = dmg.get('superficial', 0)
                    agg = dmg.get('aggravated', 0)
                    cur = max_h - (sup + agg)
                    lines.append(f"Health {cur}/{max_h}")
                # Sprint / movement
                if hasattr(char, 'sprint_distance'):
                    try:
                        lines.append(f"Sprint Max {char.calculate_sprint_distance()}")
                    except Exception:
                        pass
            mx, my = self._last_mouse
            self.ui_manager.set_hover_tooltip(lines, int(mx + 16), int(my + 16))
            self._force_tooltip = False

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # First, UI button hit detection (action buttons / end turn)
        if button == arcade.MOUSE_BUTTON_LEFT:
            # End Turn button
            region = self.ui_manager.end_turn_region
            if region:
                x1, y1, x2, y2 = region
                if x1 <= x <= x2 and y1 <= y <= y2:
                    self.input_manager.handle_end_turn()
                    return
            # Action buttons
            for name, (x1, y1, x2, y2) in self.ui_manager.action_button_regions:
                if x1 <= x <= x2 and y1 <= y <= y2:
                    requires_target = name not in ("End Turn",)
                    if name == "End Turn":
                        self.input_manager.handle_end_turn()
                    else:
                        self.input_manager.handle_action_hotkey(name, requires_target=requires_target)
                    return
        # ...existing code for right/left click map targeting...
        if button == arcade.MOUSE_BUTTON_RIGHT:
            self.input_manager.handle_cancel()
            return
        if button == arcade.MOUSE_BUTTON_LEFT:
            cell = self._screen_to_grid(x, y)
            if cell:
                self.input_manager.handle_tile_click(cell[0], cell[1])

    # --- Rendering (simplified - delegate complex logic to UIManager) ---
    def on_draw(self):
        """Main rendering entry point."""
        self.clear()

        # Let UIManagerV2 handle the actual drawing logic
        self.ui_manager.tick(0.016)  # Assume ~60 FPS for timing
        self.ui_manager.draw()

        # Simple placeholder rendering until UIManagerV2 is fully implemented
        self._draw_placeholder_scene()

    def _draw_placeholder_scene(self):
        """Temporary placeholder rendering until UIManagerV2 is complete."""
        state = self.ui_manager.state
        self._draw_simple_grid()
        self._draw_entities(state)
        self._draw_status_and_notifications(state)

    def _draw_status_and_notifications(self, state):
        """Draw (and cache) status line & recent notifications using arcade.Text if available."""
        if not arcade:
            return
        # Status line
        status_text = None
        if state.active_entity_id:
            status_text = f"Active: {state.active_entity_id} | Round: {state.round_number}"
        if status_text != self._last_status_text:
            self._last_status_text = status_text
            if hasattr(arcade, 'Text'):
                if status_text:
                    if self._status_text_obj is None:
                        try:
                            self._status_text_obj = arcade.Text(status_text, 10, self.height - 30, arcade.color.WHITE, 14)
                        except Exception:
                            self._status_text_obj = None
                    else:
                        # Update existing
                        try:
                            self._status_text_obj.text = status_text
                            self._status_text_obj.x = 10
                            self._status_text_obj.y = self.height - 30
                        except Exception:
                            pass
                else:
                    self._status_text_obj = None
        # Draw status
        if self._status_text_obj is not None:
            try:
                self._status_text_obj.draw()
            except Exception:
                pass
        elif status_text:  # fallback
            arcade.draw_text(status_text, 10, self.height - 30, arcade.color.WHITE, 14)
        # Notifications (last 3)
        notifications = list(state.notifications[-3:]) if state.notifications else []
        if notifications != self._last_notifications:
            self._last_notifications = notifications
            self._notification_text_objs = []
            if hasattr(arcade, 'Text'):
                base_y = self.height - 60
                for i, note in enumerate(notifications):
                    try:
                        txt = arcade.Text(note, 10, base_y - i * 20, arcade.color.YELLOW, 12)
                        self._notification_text_objs.append(txt)
                    except Exception:
                        pass
        # Draw notifications
        if self._notification_text_objs:
            for txt in self._notification_text_objs:
                try:
                    txt.draw()
                except Exception:
                    pass
        elif notifications:  # fallback for any missing
            for i, note in enumerate(notifications):
                arcade.draw_text(note, 10, self.height - 60 - (i * 20), arcade.color.YELLOW, 12)

    def _draw_entities(self, state):
        """Render entities with custom images or fallback colored tokens."""
        game_state = self.game_setup["game_state"]
        terrain = self.game_setup["terrain"]
        offset_x = self._get_camera_offset_x()
        offset_y = self._get_camera_offset_y()
        cell = self.cell_size

        for eid, entity in list(game_state.entities.items()):
            pos = entity.get("position")
            cref = entity.get("character_ref")
            if not pos or not cref:
                continue
            char = getattr(cref, "character", None)
            if not char or getattr(char, "is_dead", False):
                continue

            team = getattr(char, "team", "?")
            x = offset_x + pos.x * cell + cell / 2
            y = offset_y + pos.y * cell + cell / 2

            # UX Point 6: Graphics & Customization - Assign images to characters/entities
            sprite_drawn = self._draw_entity_sprite(char, x, y, cell)

            # UX Point 6: Fallback visuals - generic colored token if no image assigned
            if not sprite_drawn:
                self._draw_fallback_token(team, x, y, cell)

            # Draw facing indicator and active highlight
            self._draw_entity_indicators(char, eid, state, x, y, cell)

    def _draw_entity_sprite(self, char, x: float, y: float, cell_size: int) -> bool:
        """Load and draw custom character sprites with adaptive API probing.
        Tries several Arcade texture draw variants until one succeeds, then caches it.
        """
        sprite_path = getattr(char, 'sprite_path', None)
        if not sprite_path:
            return False
        tex = self._texture_cache.get(sprite_path)
        if tex is None:
            try:
                tex = arcade.load_texture(sprite_path)
                self._texture_cache[sprite_path] = tex
                print(f"[Graphics] Loaded sprite: {sprite_path} ({tex.width}x{tex.height})")
            except Exception as e:
                print(f"[Graphics] Failed to load sprite {sprite_path}: {e}")
                self._texture_cache[sprite_path] = None
                return False
        if not tex:
            return False

        scale = (cell_size / max(tex.width, tex.height)) * 0.8
        draw_w = tex.width * scale
        draw_h = tex.height * scale
        left = x - draw_w / 2
        bottom = y - draw_h / 2

        # Fast path if we've already discovered a working variant
        variant = getattr(self, '_tex_draw_variant', None)
        if variant is not None:
            try:
                self._execute_draw_variant(variant, tex, x, y, draw_w, draw_h, left, bottom, scale)
                return True
            except Exception as e:  # Fallback to re-probe if it suddenly fails
                print(f"[Graphics] Cached draw variant failed, re-probing: {e}")
                self._tex_draw_variant = None

        # Probe available methods in a conservative order (most explicit geometry first)
        variants = []
        if hasattr(arcade, 'draw_lrwh_rectangle_textured'):
            variants.append(('lrwh',))
        if hasattr(arcade, 'draw_scaled_texture_rectangle'):
            variants.append(('scaled',))
        if hasattr(arcade, 'draw_texture_rectangle'):
            variants.append(('legacy',))
        if hasattr(arcade, 'draw_texture_rect'):
            # Try multiple plausible signatures for unknown version
            variants.extend([
                ('rect_xy_wh_tex_pos',),      # arcade.draw_texture_rect(x, y, w, h, tex)
                ('rect_tex_xy',),              # arcade.draw_texture_rect(tex, x, y)
                ('rect_tex_xy_wh',),           # arcade.draw_texture_rect(tex, x, y, w, h)
                ('rect_xy_tex',),              # arcade.draw_texture_rect(x, y, tex)
                ('rect_tex',),                 # arcade.draw_texture_rect(tex)  (unlikely but safe)
            ])

        for v in variants:
            try:
                self._execute_draw_variant(v, tex, x, y, draw_w, draw_h, left, bottom, scale)
                self._tex_draw_variant = v
                print(f"[Graphics] Texture draw variant selected: {v}")
                return True
            except Exception:
                continue

        # All attempts failed
        return False

    def _execute_draw_variant(self, variant, tex, x, y, w, h, left, bottom, scale):
        """Execute one of the probed draw variants."""
        name = variant[0]
        if name == 'lrwh':
            arcade.draw_lrwh_rectangle_textured(left, bottom, w, h, tex)
        elif name == 'scaled':
            arcade.draw_scaled_texture_rectangle(x, y, tex, scale, scale)
        elif name == 'legacy':
            arcade.draw_texture_rectangle(x, y, w, h, tex)
        elif name == 'rect_xy_wh_tex_pos':
            arcade.draw_texture_rect(x, y, w, h, tex)
        elif name == 'rect_tex_xy':
            arcade.draw_texture_rect(tex, x, y)
        elif name == 'rect_tex_xy_wh':
            arcade.draw_texture_rect(tex, x, y, w, h)
        elif name == 'rect_xy_tex':
            arcade.draw_texture_rect(x, y, tex)
        elif name == 'rect_tex':
            arcade.draw_texture_rect(tex)
        else:
            raise RuntimeError(f"Unknown draw variant {variant}")

    def _draw_fallback_token(self, team: str, x: float, y: float, cell_size: int):
        """UX Point 6: Fallback visuals - generic colored token if no image assigned."""
        # Team-based color mapping for visual distinction
        color_map = {
            'A': arcade.color.SKY_BLUE,      # Player team (bright blue)
            'B': arcade.color.ORANGE_RED,    # AI team 1 (red-orange)
            'C': arcade.color.AMAZON,        # AI team 2 (green)
            'D': arcade.color.GOLD,          # AI team 3 (yellow/gold)
        }
        color = color_map.get(team, arcade.color.LIGHT_GRAY)

        # Draw circular token with team letter
        radius = max(8, int(cell_size * 0.35))
        arcade.draw_circle_filled(x, y, radius, color)
        arcade.draw_circle_outline(x, y, radius, arcade.color.BLACK, 2)

        # Team identifier text
        arcade.draw_text(team, x - 8, y - 8, arcade.color.BLACK, 14,
                        anchor_x="center", anchor_y="center")

    def _draw_entity_indicators(self, char, entity_id: str, state, x: float, y: float, cell_size: int):
        """Draw facing arrow and active entity highlight."""
        orient = getattr(char, 'orientation', 'up')
        arrow_len = cell_size * 0.4
        arrow_w = cell_size * 0.25
        # Orientation arrow points
        if orient == 'up':
            pts = [(x, y + arrow_len), (x - arrow_w/2, y + arrow_len - arrow_w), (x + arrow_w/2, y + arrow_len - arrow_w)]
        elif orient == 'down':
            pts = [(x, y - arrow_len), (x - arrow_w/2, y - arrow_len + arrow_w), (x + arrow_w/2, y - arrow_len + arrow_w)]
        elif orient == 'left':
            pts = [(x - arrow_len, y), (x - arrow_len + arrow_w, y - arrow_w/2), (x - arrow_len + arrow_w, y + arrow_w/2)]
        else:  # right
            pts = [(x + arrow_len, y), (x + arrow_len - arrow_w, y - arrow_w/2), (x + arrow_len - arrow_w, y + arrow_w/2)]
        arcade.draw_polygon_filled(pts, arcade.color.WHITE)
        arcade.draw_polygon_outline(pts, arcade.color.BLACK, 1)
        if entity_id == state.active_entity_id:
            arcade.draw_circle_outline(x, y, cell_size * 0.6, arcade.color.WHITE, 3)
            pulse = abs(self.elapsed_time * 2) % 2.0 - 1.0
            alpha = max(0, min(255, int(100 + 50 * pulse)))
            base_white = arcade.color.WHITE
            color = (*base_white[:3], alpha) if len(base_white) >= 3 else (255, 255, 255, alpha)
            try:
                arcade.draw_circle_filled(x, y, cell_size * 0.7, color)
            except Exception as e:
                print(f"[Graphics] Failed highlight draw: {e}")

    def _draw_simple_grid(self):
        """Draw a basic grid for the placeholder."""
        terrain = self.game_setup["terrain"]
        offset_x = self._get_camera_offset_x()
        offset_y = self._get_camera_offset_y()

        # Draw grid lines
        for x in range(terrain.width + 1):
            x_pos = offset_x + x * self.cell_size
            arcade.draw_line(x_pos, offset_y,
                           x_pos, offset_y + terrain.height * self.cell_size,
                           arcade.color.DARK_GRAY, 1)

        for y in range(terrain.height + 1):
            y_pos = offset_y + y * self.cell_size
            arcade.draw_line(offset_x, y_pos,
                           offset_x + terrain.width * self.cell_size, y_pos,
                           arcade.color.DARK_GRAY, 1)

    # --- Camera Utilities (rendering concern) ---
    def _screen_to_grid(self, screen_x: float, screen_y: float) -> Optional[tuple[int, int]]:
        """Convert screen coordinates to grid coordinates."""
        offset_x = self._get_camera_offset_x()
        offset_y = self._get_camera_offset_y()

        grid_x = screen_x - offset_x
        grid_y = screen_y - offset_y

        if grid_x < 0 or grid_y < 0:
            return None

        cell_x = int(grid_x // self.cell_size)
        cell_y = int(grid_y // self.cell_size)

        terrain = self.game_setup["terrain"]
        if 0 <= cell_x < terrain.width and 0 <= cell_y < terrain.height:
            return (cell_x, cell_y)
        return None

    def _get_camera_offset_x(self) -> float:
        return self.grid_origin_x - self.camera_x

    def _get_camera_offset_y(self) -> float:
        return self.grid_origin_y - self.camera_y

    def _center_camera_on_terrain(self):
        """Center camera on terrain initially."""
        terrain = self.game_setup["terrain"]
        terrain_width = terrain.width * self.cell_size
        terrain_height = terrain.height * self.cell_size
        self.camera_x = (terrain_width - self.width) / 2
        self.camera_y = (terrain_height - self.height) / 2

    def on_update(self, delta_time: float):
        """Handle frame updates."""
        self.elapsed_time += delta_time
        self._update_camera(delta_time)
        self._update_tooltip(delta_time)
        self._edge_scroll_camera(delta_time)

    def _update_camera(self, delta_time: float):
        """Update camera position based on input or follow target."""
        if self.camera_locked and self.spectator.current_view:
            # Follow selected entity
            game_state = self.game_setup["game_state"]
            ent = game_state.get_entity(self.spectator.current_view)
            if ent and ent.get("position"):
                pos = ent["position"]
                cell = self.cell_size
                target_x = pos.x * cell - (self.width / 2) + cell / 2
                target_y = pos.y * cell - (self.height / 2) + cell / 2
                # Direct snap (could smooth later)
                self.camera_x = max(0, target_x)
                self.camera_y = max(0, target_y)
            return
        if self.camera_locked:
            return
        # Free camera movement
        if self.keys_pressed:
            dx = dy = 0
            if arcade.key.LEFT in self.keys_pressed:
                dx = -self.camera_speed * delta_time
            if arcade.key.RIGHT in self.keys_pressed:
                dx = self.camera_speed * delta_time
            if arcade.key.UP in self.keys_pressed:
                dy = self.camera_speed * delta_time
            if arcade.key.DOWN in self.keys_pressed:
                dy = -self.camera_speed * delta_time
            self.camera_x = max(0, self.camera_x + dx)
            self.camera_y = max(0, self.camera_y + dy)

    def _edge_scroll_camera(self, dt: float):
        # Mouse edge scroll when unlocked
        if self.camera_locked:
            return
        x, y = self._last_mouse
        speed = self.camera_speed * dt
        margin = 8
        moved = False
        if x < margin:
            self.camera_x = max(0, self.camera_x - speed)
            moved = True
        elif x > self.width - margin:
            self.camera_x = max(0, self.camera_x + speed)
            moved = True
        if y < margin:
            self.camera_y = max(0, self.camera_y - speed)
            moved = True
        elif y > self.height - margin:
            self.camera_y = max(0, self.camera_y + speed)
            moved = True
        if moved:
            pass  # future clamp to terrain bounds
