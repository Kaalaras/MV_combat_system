"""UI Manager v2 (Enhanced Implementation)
==========================================

This version provides actual rendering capabilities while maintaining proper
separation of concerns from game logic.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, Tuple

from interface.ui_state import UiState

# Safe rectangle helpers (Arcade version agnostic)
def _safe_rect_filled(l, r, t, b, color):
    try:
        import arcade
    except ImportError:
        return
    if hasattr(arcade, 'draw_lrtb_rectangle_filled'):
        arcade.draw_lrtb_rectangle_filled(l, r, t, b, color)
    else:
        # Fallback: compute center/size
        w = r - l
        h = t - b
        cx = l + w / 2
        cy = b + h / 2
        if hasattr(arcade, 'draw_rectangle_filled'):
            arcade.draw_rectangle_filled(cx, cy, w, h, color)

def _safe_rect_outline(l, r, t, b, color, border=1):
    try:
        import arcade
    except ImportError:
        return
    if hasattr(arcade, 'draw_lrtb_rectangle_outline'):
        arcade.draw_lrtb_rectangle_outline(l, r, t, b, color, border)
    else:
        w = r - l
        h = t - b
        cx = l + w / 2
        cy = b + h / 2
        if hasattr(arcade, 'draw_rectangle_outline'):
            arcade.draw_rectangle_outline(cx, cy, w, h, color, border)


@dataclass
class _AnimationTimers:
    """Holds transient timers used only for visual fade / progress bars."""
    turn_banner_time: float = 0.0
    transient_message_time: float = 0.0
    notification_timers: Dict[str, float] = None

    def __post_init__(self):
        if self.notification_timers is None:
            self.notification_timers = {}


class UIManagerV2:
    """Enhanced UI orchestrator with actual rendering capabilities.

    Responsibilities:
    - Store latest UiState provided by adapter
    - Maintain purely visual timers for fades
    - Provide comprehensive draw() implementation
    - Handle visual effects and animations

    Non-Responsibilities:
    - Deciding turn order or game logic
    - Validating or issuing game actions
    - Modifying GameState / ECS directly
    """

    def __init__(self, *, on_log: Optional[Callable[[str], None]] = None,
                 render_backend: Optional[Any] = None) -> None:
        self._state: UiState = UiState.empty()
        self._timers = _AnimationTimers()
        self._on_log = on_log or (lambda msg: None)
        self._render_backend = render_backend  # For future abstraction

        # UI layout configuration
        self.action_bar_height = 110
        self.cell_size = 32

        # Performance: cache frequently used colors
        self._colors = {
            'background': (20, 20, 30),
            'active_entity': (135, 206, 235),  # SKY_BLUE
            'ally': (34, 139, 34),  # FOREST_GREEN
            'enemy': (205, 92, 92),  # INDIAN_RED
            'highlight_move': (50, 120, 255, 60),
            'highlight_attack': (255, 100, 100, 80),
            'health_good': (50, 200, 50),
            'health_medium': (200, 200, 50),
            'health_low': (200, 50, 50),
            'text_primary': (255, 255, 255),
            'text_notification': (255, 255, 200)
        }
        self._action_button_regions = []  # (name, (x1,y1,x2,y2)) for click detection
        self._end_turn_region = None
        self._action_menu_scroll = 0.0
        self._hover_tooltip: Optional[Dict[str, Any]] = None  # external may set

        self._colors.update({
            'health_fill': (200, 40, 40),
            'health_bg': (10, 10, 10),
            'move_used': (100, 100, 100),
            'move_standard': (255, 215, 0),  # yellow section
            'move_extra': (60, 200, 60),
            'primary_action': (10, 50, 140),
            'secondary_action': (80, 140, 220),
            'end_turn_bg': (60, 20, 20),
            'end_turn_text': (240, 200, 200),
            'tooltip_bg': (30, 30, 40, 220),
        })
        self._text_cache: Dict[str, Any] = {}
        self._initiative_layout_sig: Optional[tuple] = None

        # NEW: Tooltip and feedback management
        self._tooltip_timer: float = 0.0
        self._tooltip_visible: bool = False
        self._current_hover_entity: Optional[str] = None
        self._turn_start_timer: float = 0.0
        self._error_feedback_timer: float = 0.0
        self._last_mouse_pos: Tuple[int, int] = (0, 0)

    # --- State & timing lifecycle ---
    def update_state(self, state: UiState) -> None:
        """Replace the current snapshot and handle state transitions."""
        prev = self._state
        self._state = state

        # Handle state transition effects
        if state.active_entity_id != prev.active_entity_id and state.is_player_turn:
            self._timers.turn_banner_time = 2.5

        # Track new notifications
        for notification in state.notifications:
            if notification not in prev.notifications:
                self._timers.notification_timers[notification] = 3.0

    def tick(self, dt: float) -> None:
        """Advance animation timers."""
        self._timers.turn_banner_time = max(0.0, self._timers.turn_banner_time - dt)
        self._timers.transient_message_time = max(0.0, self._timers.transient_message_time - dt)

        # NEW: Update tooltip, turn start, and error feedback timers
        self._tooltip_timer = max(0.0, self._tooltip_timer - dt)
        self._turn_start_timer = max(0.0, self._turn_start_timer - dt)
        self._error_feedback_timer = max(0.0, self._error_feedback_timer - dt)

        # Update notification timers
        expired = []
        for notif, timer in self._timers.notification_timers.items():
            new_time = max(0.0, timer - dt)
            if new_time <= 0:
                expired.append(notif)
            else:
                self._timers.notification_timers[notif] = new_time

        for notif in expired:
            del self._timers.notification_timers[notif]

    def draw(self) -> None:
        """Render the full UI frame with proper visual hierarchy."""
        try:
            import arcade
        except ImportError:
            self._draw_text_mode()
            return
        self._action_button_regions = []
        self._end_turn_region = None
        self._draw_action_bar()
        self._draw_gauges()
        self._draw_action_menu()
        self._draw_reactive_actions()
        self._draw_initiative_display()
        self._draw_notifications()
        self._draw_turn_banner()
        self._draw_status_overlay()
        self._draw_tooltip()

    def _draw_text_mode(self) -> None:
        """Fallback rendering for when arcade is not available."""
        s = self._state
        self._on_log(f"[UI] Round={s.round_number} Active={s.active_entity_id}")
        if s.actions_remaining is not None:
            self._on_log(f"[UI] Actions remaining: {s.actions_remaining}")
        if s.notifications:
            self._on_log(f"[UI] Notifications: {list(s.notifications[-2:])}")
        if self._timers.turn_banner_time > 0:
            self._on_log("[UI] 🎯 PLAYER TURN")

    def _draw_action_bar(self) -> None:
        """Draw the bottom action bar with controls and status."""
        import arcade
        self._draw_rect_centered(400, self.action_bar_height // 2, 800, self.action_bar_height, self._colors['background'])
        if self._state.active_entity_id:
            self._draw_action_economy()
        status_parts = []
        if self._state.round_number > 0:
            status_parts.append(f"Round {self._state.round_number}")
        if self._state.active_entity_id:
            status_parts.append(f"Active: {self._state.active_entity_id[:8]}")
        if status_parts:
            status_text = " | ".join(status_parts)
            self._cache_text('status_bar', status_text, 10, self.action_bar_height - 25, self._colors['text_primary'], 12)
            self._draw_cached_text('status_bar')

    # NEW helper for rectangle drawing compatibility
    def _draw_rect_centered(self, cx: float, cy: float, w: float, h: float, color):
        try:
            import arcade
        except ImportError:
            return
        if hasattr(arcade, 'draw_rectangle_filled'):
            arcade.draw_rectangle_filled(cx, cy, w, h, color)
            return
        # Fallbacks for versions where draw_rectangle_filled is absent
        if hasattr(arcade, 'draw_xywh_rectangle_filled'):
            arcade.draw_xywh_rectangle_filled(cx - w/2, cy - h/2, w, h, color)
            return
        if hasattr(arcade, 'draw_lrtb_rectangle_filled'):
            arcade.draw_lrtb_rectangle_filled(cx - w/2, cx + w/2, cy + h/2, cy - h/2, color)
            return

    def _draw_gauges(self) -> None:
        """Health circle (bottom left) and movement bar with standard/yellow section."""
        import arcade
        s = self._state

        # Health gauge - circle at bottom left
        center_x = 50
        center_y = 55
        radius = 40

        # Draw background circle (black)
        arcade.draw_circle_filled(center_x, center_y, radius, (0, 0, 0))

        # Get health values
        cur = s.extras.get('active_health') if s.extras else None
        mx = s.extras.get('active_max_health') if s.extras else None

        if cur is not None and mx and mx > 0:
            # Calculate health percentage
            pct = max(0.0, min(1.0, cur / mx))

            # Draw health as filled red circle that empties progressively
            if pct > 0:
                inner_r = max(1, int(radius * pct))
                arcade.draw_circle_filled(center_x, center_y, inner_r, (255, 0, 0))  # Fully red

            # Health text label
            label = f"{cur}/{mx}"
            arcade.draw_text(label, center_x, center_y - 8, self._colors['text_primary'], 11, anchor_x="center")
        else:
            # Fallback when no health data
            arcade.draw_text("HP", center_x, center_y - 8, self._colors['text_primary'], 11, anchor_x="center")

        # Movement gauge - green bar with yellow section
        move_used = s.extras.get('movement_used', 0) if s.extras else 0
        move_max = s.extras.get('movement_max', 10) if s.extras else 10
        standard_movement = s.extras.get('standard_movement', 7) if s.extras else 7

        bar_x = 100
        bar_y = 20
        bar_w = 300
        bar_h = 14

        # Draw background bar (dark)
        _safe_rect_filled(bar_x, bar_x + bar_w, bar_y + bar_h, bar_y, (25, 25, 30))

        # Draw full bar as green (standard movement)
        std_w = int(bar_w * (standard_movement / max(move_max, 1)))
        _safe_rect_filled(bar_x, bar_x + std_w, bar_y + bar_h, bar_y, (0, 255, 0))  # Green

        # Draw yellow section for extra movement beyond standard
        if move_max > standard_movement:
            extra_start = std_w
            extra_w = int(bar_w * ((move_max - standard_movement) / max(move_max, 1)))
            _safe_rect_filled(bar_x + extra_start, bar_x + extra_start + extra_w,
                             bar_y + bar_h, bar_y, (255, 255, 0))  # Yellow

        # Draw used movement as grey overlay
        used_w = int(bar_w * (min(move_used, move_max) / max(move_max, 1)))
        if used_w > 0:
            _safe_rect_filled(bar_x, bar_x + used_w, bar_y + bar_h, bar_y, (100, 100, 100))  # Grey

        # Draw border
        _safe_rect_outline(bar_x, bar_x + bar_w, bar_y + bar_h, bar_y, (160, 160, 160), 1)

        # Movement text label
        arcade.draw_text(f"Move {move_used}/{move_max}", bar_x + bar_w + 8, bar_y + 1,
                        self._colors['text_primary'], 10)

        # Reset indicator - resets at start of each turn
        if s.extras.get('movement_reset_this_turn', False):
            arcade.draw_text("↻", bar_x - 15, bar_y + 2, (100, 255, 100), 12)

    def _draw_action_economy(self) -> None:
        """Draw action point indicators (primary dark blue discs, secondary light blue squares)."""
        import arcade
        s = self._state
        x_base = 450
        y_pos = self.action_bar_height // 2 + 10
        if s.primary_actions_remaining is not None:
            for i in range(max(1, s.primary_actions_remaining)):
                filled = i < s.primary_actions_remaining
                color = self._colors['primary_action'] if filled else (60, 60, 70)
                arcade.draw_circle_filled(x_base + i * 26, y_pos, 10, color)
        if s.secondary_actions_remaining is not None:
            y2 = y_pos - 28
            for i in range(max(1, s.secondary_actions_remaining)):
                filled = i < s.secondary_actions_remaining
                color = self._colors['secondary_action'] if filled else (60, 60, 70)
                size = 18
                # use safe rect for square
                left = x_base + i * 26 - size/2
                right = left + size
                bottom = y2 - size/2
                top = bottom + size
                _safe_rect_filled(left, right, top, bottom, color)
                _safe_rect_outline(left, right, top, bottom, (30,30,40), 1)
        if s.free_move_available:
            arcade.draw_text("Free Move", x_base, y_pos - 60, self._colors['health_medium'], 10)

    def _draw_action_menu(self) -> None:
        """Draw scrollable action buttons list with size constraints (max 20% height, 65% width)."""
        import arcade
        s = self._state
        actions = (s.extras.get('available_actions') if s.extras else []) or []
        if not actions:
            return

        # UX Specification: Max dimensions = 20% screen height, 65% width
        max_h = int(600 * 0.20)  # 20% of screen height
        max_w = int(800 * 0.65)  # 65% of screen width
        menu_x = 150
        menu_y = 5
        menu_w = max_w
        menu_h = max_h

        # Draw main menu background
        _safe_rect_filled(menu_x, menu_x + menu_w, menu_y + menu_h, menu_y, (35, 35, 50, 200))
        _safe_rect_outline(menu_x, menu_x + menu_w, menu_y + menu_h, menu_y, (150, 150, 170), 2)

        # UX: Reduced button size, multiple lines if needed
        btn_h = 20  # Reduced from 24
        btn_w = 110  # Reduced from 120
        padding = 3  # Reduced padding
        col_spacing = 8
        row_spacing = 2

        x_cursor = menu_x + padding
        y_cursor = menu_y + menu_h - padding - btn_h
        regions = []
        visible_area_top = menu_y + menu_h - padding
        visible_area_bottom = menu_y + padding

        # UX: Scroll cursor if overloaded
        scroll_offset = int(self._action_menu_scroll)
        overloaded = False

        for idx, name in enumerate(actions):
            # Apply scroll (vertical)
            btn_top = y_cursor - scroll_offset
            btn_bottom = btn_top - btn_h

            # Check if we need to wrap to new column
            if x_cursor + btn_w > menu_x + menu_w - padding:
                x_cursor = menu_x + padding
                y_cursor -= (btn_h + row_spacing)
                btn_top = y_cursor - scroll_offset
                btn_bottom = btn_top - btn_h

            # Check if content exceeds visible area
            if btn_bottom < visible_area_bottom:
                overloaded = True
                # Don't draw but continue for layout calculation
            elif btn_top <= visible_area_top:
                # Draw button within visible area
                _safe_rect_filled(x_cursor, x_cursor + btn_w, btn_top, btn_bottom, (60, 60, 90))
                _safe_rect_outline(x_cursor, x_cursor + btn_w, btn_top, btn_bottom, (120, 150, 180), 1)

                # UX: Multiple lines if needed - split long action names
                display_name = name[:15] + "..." if len(name) > 15 else name
                lines = [display_name[i:i+10] for i in range(0, len(display_name), 10)]

                # Draw text (up to 2 lines)
                for line_idx, line in enumerate(lines[:2]):
                    text_y = btn_bottom + 4 + (btn_h // 2) - (line_idx * 10)
                    key = f"act_btn_{name}_{line_idx}_{x_cursor}_{btn_bottom}"
                    self._cache_text(key, line, x_cursor + 4, text_y, self._colors['text_primary'], 9)
                    self._draw_cached_text(key)

                regions.append((name, (x_cursor, btn_bottom, x_cursor + btn_w, btn_top)))

            # Advance horizontally
            x_cursor += btn_w + col_spacing

        self._action_button_regions = regions

        # UX: Scroll cursor if overloaded
        if overloaded:
            # Draw scroll indicators
            scroll_up_y = menu_y + menu_h - 15
            scroll_down_y = menu_y + 15
            scroll_x = menu_x + menu_w - 25

            # Up arrow
            if scroll_offset < 0:  # Can scroll up
                arcade.draw_text("▲", scroll_x, scroll_up_y, (150, 200, 255), 12)

            # Down arrow
            if scroll_offset > -(y_cursor - visible_area_bottom):  # Can scroll down
                arcade.draw_text("▼", scroll_x, scroll_down_y, (150, 200, 255), 12)

            # Scroll hint
            self._cache_text('action_scroll_hint', '↕ Scroll', menu_x + menu_w - 60, menu_y + menu_h - 35,
                           (200, 200, 220), 9)
            self._draw_cached_text('action_scroll_hint')

        # UX: End Turn button - placed alone in mini-menu on the left
        if s.is_player_turn:
            self._draw_end_turn_mini_menu(menu_y, menu_h)

    def _draw_end_turn_mini_menu(self, main_menu_y: int, main_menu_h: int) -> None:
        """Draw End Turn button in separate mini-menu on the left, between health gauge and actions menu."""
        import arcade

        # Position between health gauge (x=50+40=90) and main menu (x=150)
        end_x1 = 5
        end_x2 = 130
        end_y1 = main_menu_y + main_menu_h + 10  # Slightly above main menu
        end_y2 = end_y1 - 45  # Compact height

        # Draw mini-menu background
        _safe_rect_filled(end_x1, end_x2, end_y1, end_y2, (60, 30, 30, 180))
        _safe_rect_outline(end_x1, end_x2, end_y1, end_y2, (150, 100, 100), 2)

        # Draw End Turn button
        btn_padding = 5
        btn_x1 = end_x1 + btn_padding
        btn_x2 = end_x2 - btn_padding
        btn_y1 = end_y1 - btn_padding
        btn_y2 = end_y2 + btn_padding

        _safe_rect_filled(btn_x1, btn_x2, btn_y1, btn_y2, (80, 40, 40))
        _safe_rect_outline(btn_x1, btn_x2, btn_y1, btn_y2, (180, 120, 120), 1)

        # End Turn text
        center_x = (btn_x1 + btn_x2) // 2
        center_y = (btn_y1 + btn_y2) // 2
        self._cache_text('end_turn_label', 'End Turn', center_x, center_y - 5,
                        (255, 200, 200), 14, anchor_x='center')
        self._draw_cached_text('end_turn_label')

        # Store region for click detection
        self._end_turn_region = (btn_x1, btn_y2, btn_x2, btn_y1)

    def _draw_initiative_display(self) -> None:
        """Draw initiative order at top of screen with grey translucent separators between rounds."""
        import arcade

        if not self._state.initiative:
            return

        y_pos = 580  # Near top
        x_start = 50

        # Cache header
        self._cache_text('initiative_header', 'Initiative:', x_start, y_pos, self._colors['text_primary'], 14)
        self._draw_cached_text('initiative_header')

        x_pos = x_start + 110
        radius = 10

        # UX Specification: Grey translucent separators between rounds
        wrap_index = self._state.extras.get('initiative_wrap_index') if self._state.extras else None
        round_separators = self._state.extras.get('round_separators', []) if self._state.extras else []

        # Build layout signature for caching
        ids = tuple(e.entity_id for e in self._state.initiative[:16])
        layout_changed = ids != self._initiative_layout_sig
        if layout_changed:
            # Invalidate old per-entity texts when layout changes
            for k in list(self._text_cache.keys()):
                if k.startswith('init_ent_'):
                    self._text_cache.pop(k, None)
            self._initiative_layout_sig = ids

        # Draw initiative entries with round separators
        for idx, entry in enumerate(self._state.initiative[:16]):
            # Determine entity color based on state
            if entry.is_active:
                color = self._colors['active_entity']  # Sky blue for active
            elif entry.is_player_controlled:
                color = self._colors['ally']  # Green for player-controlled
            else:
                color = self._colors['enemy']  # Red for AI-controlled

            # Draw entity circle
            arcade.draw_circle_filled(x_pos, y_pos, radius, color)

            # Draw entity identifier text
            tag = entry.entity_id[:4]
            key = f"init_ent_{idx}_{tag}"
            self._cache_text(key, tag, x_pos - 12, y_pos - 20, self._colors['text_primary'], 8)
            self._draw_cached_text(key)

            # UX: Draw grey translucent separator between rounds
            if idx in round_separators:
                # Draw vertical separator line after this entity
                separator_x = x_pos + radius + 5
                _safe_rect_filled(separator_x, separator_x + 2, y_pos + 20, y_pos - 20,
                                (120, 120, 130, 180))  # Grey with transparency

                # Optional: Add round number indicator
                round_num = self._state.extras.get(f'round_after_{idx}', '') if self._state.extras else ''
                if round_num:
                    arcade.draw_text(f"R{round_num}", separator_x - 8, y_pos - 35,
                                   (150, 150, 160), 8, anchor_x="center")

            # Legacy support: Basic wrap index separator (fallback)
            elif wrap_index is not None and idx + 1 == wrap_index:
                _safe_rect_filled(x_pos + 15, x_pos + 19, y_pos + 15, y_pos - 15, (120, 120, 130, 120))

            x_pos += 40

        # Draw current round indicator
        current_round = self._state.round_number
        if current_round > 0:
            self._cache_text('current_round', f"Current Round: {current_round}",
                           x_start, y_pos - 50, (200, 200, 255), 12)
            self._draw_cached_text('current_round')

    def _draw_turn_banner(self) -> None:
        """Draw turn start banner if active."""
        import arcade

        if self._timers.turn_banner_time <= 0 or not self._state.is_player_turn:
            return

        # Calculate fade
        fade_progress = self._timers.turn_banner_time / 2.0
        alpha = int(255 * fade_progress)

        banner_text = "Your Turn's beginning"
        arcade.draw_text(banner_text, 400, 350, (180, 180, 180, alpha), 28,
                       anchor_x="center", anchor_y="center")

    def _draw_tooltip(self) -> None:
        """Render a tooltip if _hover_tooltip dict provided externally."""
        if not self._hover_tooltip:
            return
        try:
            import arcade
        except ImportError:
            return
        data = self._hover_tooltip
        text_lines = data.get('lines', [])
        if not text_lines:
            return
        x = data.get('x', 0)
        y = data.get('y', 0)
        padding = 6
        max_w = max((len(line) * 7 for line in text_lines), default=0)
        box_w = max_w + padding * 2
        box_h = len(text_lines) * 14 + padding * 2
        _safe_rect_filled(x, x + box_w, y + box_h, y, self._colors['tooltip_bg'])
        _safe_rect_outline(x, x + box_w, y + box_h, y, (160, 160, 190), 1)
        for i, line in enumerate(text_lines):
            arcade.draw_text(line, x + padding, y + box_h - padding - 14 * (i + 1) + 4, self._colors['text_primary'], 10)

    def _draw_reactive_actions(self) -> None:
        """Temporary context window above action menu for defensive/reactive actions."""
        import arcade
        s = self._state
        reactive = (s.extras.get('reactive_actions') if s.extras else []) or []
        if not reactive:
            return
        x1 = 160
        x2 = min(780, x1 + 400)
        y_bottom = 110 + int(600 * 0.20) + 8
        y_top = y_bottom + 60
        _safe_rect_filled(x1, x2, y_top, y_bottom, (50, 40, 60, 200))
        _safe_rect_outline(x1, x2, y_top, y_bottom, (180, 170, 200), 1)
        arcade.draw_text("Reactive Actions", x1 + 10, y_top - 20, self._colors['text_primary'], 12)
        for i, name in enumerate(reactive[:4]):
            arcade.draw_text(name, x1 + 10, y_top - 40 - i * 14, self._colors['text_primary'], 10)

    def _draw_notifications(self) -> None:
        import arcade
        notes = self._state.notifications
        if not notes:
            return
        y_base = 450
        for i, notif in enumerate(notes[-5:]):
            alpha = int(255 * self.get_notification_alpha(notif))
            color = (*self._colors['text_notification'][:3], alpha)
            arcade.draw_text(notif, 10, y_base - i * 22, color, 11)

    def _draw_status_overlay(self) -> None:
        import arcade
        s = self._state
        # Pending action indicator
        if s.pending_action:
            txt = f"Selected: {s.pending_action.action_name}"
            if s.pending_action.requires_target:
                txt += " (choose target)"
            arcade.draw_text(txt, 10, 500, self._colors['active_entity'], 14)
        # Last action result
        if s.last_action_name and s.last_action_result:
            arcade.draw_text(f"Last: {s.last_action_name} -> {s.last_action_result}", 10, 480, self._colors['text_primary'], 12)

    # --- Accessors ---
    @property
    def state(self) -> UiState:
        return self._state

    def has_active_banner(self) -> bool:
        return self._timers.turn_banner_time > 0

    def get_notification_alpha(self, notification: str) -> float:
        """Get current alpha for a notification (0.0 to 1.0)."""
        if notification not in self._timers.notification_timers:
            return 1.0
        return self._timers.notification_timers[notification] / 3.0

    # Public helpers for external layer
    @property
    def action_button_regions(self):
        return list(self._action_button_regions)

    @property
    def end_turn_region(self):
        return self._end_turn_region

    def set_hover_tooltip(self, lines: Optional[list], x: int, y: int):
        if not lines:
            self._hover_tooltip = None
        else:
            self._hover_tooltip = {'lines': lines, 'x': x, 'y': y}

    # NEW: Enhanced tooltip and feedback methods
    def handle_mouse_hover(self, x: int, y: int, entity_id: Optional[str] = None) -> None:
        """Handle mouse hover for tooltip system (1.5s delay or instant with TAB)."""
        self._last_mouse_pos = (x, y)

        if entity_id != self._current_hover_entity:
            self._current_hover_entity = entity_id
            self._tooltip_timer = 1.5  # Reset timer for new entity
            self._tooltip_visible = False

        # Check if tooltip should become visible
        if self._tooltip_timer <= 0 and entity_id and not self._tooltip_visible:
            self._show_entity_tooltip(entity_id, x, y)

    def handle_tab_tooltip(self, entity_id: Optional[str] = None) -> None:
        """Show tooltip instantly when TAB is pressed."""
        if entity_id:
            x, y = self._last_mouse_pos
            self._show_entity_tooltip(entity_id, x, y)
            self._tooltip_visible = True

    def _show_entity_tooltip(self, entity_id: str, x: int, y: int) -> None:
        """Display tooltip with entity information."""
        # Get entity data from state extras
        entity_data = self._state.extras.get('entity_tooltips', {}).get(entity_id, {})

        if not entity_data:
            return

        lines = []
        name = entity_data.get('name', entity_id[:8])
        lines.append(name)

        # Main values like "Health – 5/7", "Attack – Range 2"
        health = entity_data.get('health')
        max_health = entity_data.get('max_health')
        if health is not None and max_health is not None:
            lines.append(f"Health - {health}/{max_health}")

        attack_range = entity_data.get('attack_range')
        if attack_range is not None:
            lines.append(f"Attack - Range {attack_range}")

        # Add other main values
        for key, value in entity_data.get('main_values', {}).items():
            lines.append(f"{key} - {value}")

        self.set_hover_tooltip(lines, x + 10, y + 10)
        self._tooltip_visible = True

    def show_turn_start_notification(self, message: str = "Your Turn's beginning") -> None:
        """Trigger turn start notification (2s display)."""
        self._turn_start_timer = 2.0
        # This will be handled by the existing _draw_turn_banner method

    def show_error_feedback(self, message: str, duration: float = 3.0) -> None:
        """Display error feedback for invalid actions."""
        self._error_feedback_timer = duration
        # Store error message in hover tooltip temporarily for display
        lines = [f"❌ {message}"]
        x, y = self._last_mouse_pos
        self.set_hover_tooltip(lines, max(10, x - 50), max(50, y + 20))

    def _cache_text(self, key: str, text: str, x: float, y: float, color, size: int = 12, anchor_x: str = "left", anchor_y: str = "baseline") -> Any:
        """Create or update a cached arcade.Text object if available.
        Compatibility: Some arcade versions want font_size, others size.
        If creation fails, fall back to tuple spec so we at least render via draw_text.
        """
        try:
            import arcade
        except ImportError:
            self._text_cache[key] = (text, x, y, color, size, anchor_x, anchor_y)
            return self._text_cache[key]
        txt_obj = self._text_cache.get(key)
        if txt_obj and hasattr(txt_obj, 'text'):
            # Update in-place if only text or position changed
            changed = False
            if txt_obj.text != text:
                txt_obj.text = text
                changed = True
            if getattr(txt_obj, 'x', None) != x:
                txt_obj.x = x
                changed = True
            if getattr(txt_obj, 'y', None) != y:
                txt_obj.y = y
                changed = True
            return txt_obj
        # Attempt to create new arcade.Text object with version-adaptive args
        created = None
        if hasattr(arcade, 'Text'):
            try:
                # Newer versions use font_size
                created = arcade.Text(text, x, y, color, font_size=size, anchor_x=anchor_x, anchor_y=anchor_y)
            except TypeError:
                try:
                    created = arcade.Text(text, x, y, color, size=size, anchor_x=anchor_x, anchor_y=anchor_y)
                except TypeError:
                    created = None
        if created is not None:
            self._text_cache[key] = created
            return created
        # Fallback tuple for manual draw
        self._text_cache[key] = (text, x, y, color, size, anchor_x, anchor_y)
        return self._text_cache[key]

    def _draw_cached_text(self, key: str):
        try:
            import arcade
        except ImportError:
            return
        obj = self._text_cache.get(key)
        if not obj:
            return
        if hasattr(obj, 'draw'):
            obj.draw()
        else:
            # tuple fallback
            text, x, y, color, size, anchor_x, anchor_y = obj
            arcade.draw_text(text, x, y, color, size, anchor_x=anchor_x, anchor_y=anchor_y)
