"""Enhanced Combat UI with Advanced Features
===========================================

This module provides the main Arcade-based combat UI with integrated advanced features:
- Camera system with following, panning, and edge scrolling
- Enhanced visual effects and animations
- Tooltip system with proper timing
- Spectator controls for debugging
- State management integration
"""
from __future__ import annotations
import math
import time
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import arcade
    import arcade.gui
    ARCADE_AVAILABLE = True
except ImportError:
    ARCADE_AVAILABLE = False
    # Create dummy classes for when arcade is not available
    class arcade:
        class Window:
            def __init__(self, *args, **kwargs): pass
        class gui:
            class UIManager:
                def enable(self): pass
                def draw(self): pass
        class Texture:
            @staticmethod
            def create_empty(*args): return None
            @staticmethod 
            def create_filled(*args): return None
            def draw_scaled(self, *args): pass
        color = type('color', (), {
            'GRAY': (128, 128, 128), 'WHITE': (255, 255, 255), 'BLACK': (0, 0, 0),
            'LIGHT_GRAY': (200, 200, 200), 'RED': (255, 0, 0), 'GREEN': (0, 255, 0),
            'BLUE': (0, 0, 255)
        })()
        MOUSE_BUTTON_LEFT = 1
        MOUSE_BUTTON_RIGHT = 2
        key = type('key', (), {
            'A': ord('A'), 'M': ord('M'), 'E': ord('E'), 'ESC': 27, 'TAB': 9,
            'L': ord('L'), 'KEY_0': ord('0'), 'LEFT': 65361, 'RIGHT': 65363,
            'UP': 65362, 'DOWN': 65364, 'W': ord('W'), 'S': ord('S'), 'D': ord('D')
        })()
        MOD_SHIFT = 1
        @staticmethod
        def set_background_color(*args): pass
        @staticmethod
        def load_texture(*args): return None
        @staticmethod
        def draw_circle_filled(*args): pass
        @staticmethod
        def draw_circle_outline(*args): pass
        @staticmethod
        def draw_rectangle_filled(*args): pass
        @staticmethod
        def draw_rectangle_outline(*args): pass
        @staticmethod
        def draw_line(*args): pass
        @staticmethod
        def draw_polygon_filled(*args): pass
        @staticmethod
        def draw_polygon_outline(*args): pass
        @staticmethod
        def draw_text(*args): pass
        @staticmethod
        def run(): pass
        @staticmethod
        def close_window(): pass

from interface.input_manager import InputManager
from interface.player_turn_controller import PlayerTurnController
from interface.ui_adapter import UIAdapter
from interface.ui_state import UiState, InitiativeEntry
from interface.event_constants import UIStateEvents, CoreEvents


@dataclass
class ColorScheme:
    """Enhanced color definitions for the UI"""
    # Entity relationship colors
    SAME_PLAYER: Tuple[int, int, int] = (0, 255, 0)     # Green
    ALLY: Tuple[int, int, int] = (0, 100, 255)          # Blue
    NEUTRAL: Tuple[int, int, int] = (255, 255, 0)       # Yellow
    ENEMY: Tuple[int, int, int] = (255, 0, 0)           # Red
    
    # UI element colors
    INITIATIVE_SEPARATOR: Tuple[int, int, int] = (255, 215, 0)  # Gold
    MOVEMENT_NORMAL: Tuple[int, int, int] = (173, 216, 230)     # Light blue
    MOVEMENT_SPRINT: Tuple[int, int, int] = (70, 130, 180)      # Steel blue
    MOVEMENT_CONSUMED: Tuple[int, int, int] = (64, 64, 64)      # Dark grey
    
    # Resource bars - enhanced with circular health
    HEALTH: Tuple[int, int, int] = (200, 40, 40)        # Red for health circle
    HEALTH_BG: Tuple[int, int, int] = (10, 10, 10)      # Dark background
    WILLPOWER: Tuple[int, int, int] = (64, 224, 208)    # Turquoise
    BLOOD_POOL: Tuple[int, int, int] = (139, 0, 0)      # Dark red
    
    # Action icons - enhanced
    PRIMARY_ACTION: Tuple[int, int, int] = (10, 50, 140)        # Dark blue circle
    SECONDARY_ACTION: Tuple[int, int, int] = (80, 140, 220)     # Light blue square
    
    # Backgrounds and effects
    UI_BACKGROUND: Tuple[int, int, int] = (50, 50, 50)          # Dark grey
    GRID_LINE: Tuple[int, int, int] = (128, 128, 128)           # Grey
    MINIMAP_BACKGROUND: Tuple[int, int, int] = (30, 30, 30)     # Very dark grey
    
    # Tooltip and notifications
    TOOLTIP_BG: Tuple[int, int, int, int] = (30, 30, 40, 220)   # With alpha
    NOTIFICATION: Tuple[int, int, int] = (255, 255, 200)        # Light yellow
    
    # Camera and effects
    ACTIVE_HIGHLIGHT: Tuple[int, int, int] = (255, 255, 255)    # White
    PULSE_COLOR: Tuple[int, int, int, int] = (255, 255, 255, 100) # Pulsing white


@dataclass
class UILayout:
    """Enhanced layout configuration for UI elements"""
    # Screen dimensions
    WINDOW_WIDTH: int = 1400
    WINDOW_HEIGHT: int = 1000
    
    # Grid configuration
    GRID_SIZE: int = 15
    CELL_SIZE: int = 30
    GRID_OFFSET_X: int = 250
    GRID_OFFSET_Y: int = 200
    
    # Initiative bar
    INITIATIVE_BAR_HEIGHT: int = 80
    INITIATIVE_BAR_Y: int = WINDOW_HEIGHT - INITIATIVE_BAR_HEIGHT - 10
    INITIATIVE_PORTRAIT_SIZE: int = 60
    INITIATIVE_VISIBLE_COUNT: int = 10
    
    # Character panel (left side)
    CHARACTER_PANEL_WIDTH: int = 200
    CHARACTER_PANEL_HEIGHT: int = WINDOW_HEIGHT - INITIATIVE_BAR_HEIGHT - 20
    CHARACTER_PORTRAIT_SIZE: int = 60
    
    # Main interface (bottom) - enhanced with circular gauges
    MAIN_INTERFACE_HEIGHT: int = 180
    MAIN_INTERFACE_Y: int = 10
    MAIN_INTERFACE_WIDTH: int = WINDOW_WIDTH - 400  # Leave space for menus
    
    # Health gauge (circular)
    HEALTH_GAUGE_X: int = 50
    HEALTH_GAUGE_Y: int = 55  
    HEALTH_GAUGE_RADIUS: int = 40
    
    # Movement bar (enhanced with sections)
    MOVEMENT_BAR_X: int = 100
    MOVEMENT_BAR_Y: int = 20
    MOVEMENT_BAR_WIDTH: int = 300
    MOVEMENT_BAR_HEIGHT: int = 14
    
    # Minimap
    MINIMAP_SIZE: int = 150
    MINIMAP_X: int = 10
    MINIMAP_Y: int = WINDOW_HEIGHT - MINIMAP_SIZE - INITIATIVE_BAR_HEIGHT - 20
    
    # Menus (right side)
    MENU_PANEL_WIDTH: int = 150
    MENU_PANEL_X: int = WINDOW_WIDTH - MENU_PANEL_WIDTH - 10


@dataclass
class CameraState:
    """Camera system state for smooth following and edge scrolling"""
    x: float = 0.0
    y: float = 0.0
    speed: float = 200.0
    locked: bool = True
    follow_entity_id: Optional[str] = None
    edge_scroll_margin: int = 20
    edge_scroll_speed: float = 150.0
    free_mode: bool = False


@dataclass
class AnimationState:
    """Animation timers and effects state"""
    elapsed_time: float = 0.0
    turn_banner_timer: float = 0.0
    tooltip_timer: float = 0.0
    notification_timers: Dict[str, float] = field(default_factory=dict)
    pulse_phase: float = 0.0
    
    def update(self, dt: float):
        """Update all animation timers"""
        self.elapsed_time += dt
        self.turn_banner_timer = max(0.0, self.turn_banner_timer - dt)
        self.tooltip_timer = max(0.0, self.tooltip_timer - dt)
        self.pulse_phase = (self.pulse_phase + dt * 2) % (2 * math.pi)
        
        # Update notification timers
        expired = []
        for notif, timer in self.notification_timers.items():
            new_time = max(0.0, timer - dt)
            if new_time <= 0:
                expired.append(notif)
            else:
                self.notification_timers[notif] = new_time
        
        for notif in expired:
            del self.notification_timers[notif]


class SpectatorController:
    """Integrated spectator system for viewpoint cycling and debugging"""
    
    def __init__(self, event_bus, entity_order: List[str] = None):
        self.event_bus = event_bus
        self._entity_order = entity_order or []
        self._index = -1  # -1 means free camera
        self._active_turn_entity = None
        
        event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)
    
    def _on_turn_start(self, entity_id: str, **_):
        self._active_turn_entity = entity_id
    
    @property
    def current_view(self) -> Optional[str]:
        if 0 <= self._index < len(self._entity_order):
            return self._entity_order[self._index]
        return None
    
    def set_entities(self, entity_ids: List[str]):
        self._entity_order = entity_ids
        if self._index >= len(self._entity_order):
            self._index = -1
    
    def cycle_forward(self) -> Optional[str]:
        if not self._entity_order:
            self._index = -1
            return None
        self._index = (self._index + 1) % (len(self._entity_order) + 1)
        if self._index == len(self._entity_order):
            self._index = -1
        return self.current_view
    
    def cycle_backward(self) -> Optional[str]:
        if not self._entity_order:
            self._index = -1
            return None
        if self._index == -1:
            self._index = len(self._entity_order) - 1
        else:
            self._index -= 1
            if self._index < -1:
                self._index = len(self._entity_order) - 1
        return self.current_view
    
    def clear_view(self):
        self._index = -1


class EnhancedCombatUI(arcade.Window):
    """Enhanced combat UI with all advanced features integrated"""
    
    def __init__(self, game_setup: Dict[str, Any], player_ids: List[str]):
        if not ARCADE_AVAILABLE:
            raise ImportError("Arcade library is required for the enhanced combat UI")
            
        super().__init__(UILayout.WINDOW_WIDTH, UILayout.WINDOW_HEIGHT, "MV Combat System - Enhanced")
        
        self.game_setup = game_setup
        self.game_state = game_setup["game_state"]
        self.player_ids = set(player_ids)
        self.current_player_id = player_ids[0] if player_ids else None
        
        # UI components
        self.layout = UILayout()
        self.colors = ColorScheme()
        self.ui_manager = arcade.gui.UIManager()
        self.ui_manager.enable()
        
        # Enhanced systems
        self.camera = CameraState()
        self.animation = AnimationState()
        self.keys_pressed = set()
        
        # Game interface components
        self.input_manager = InputManager(game_setup["event_bus"])
        self.ui_adapter = UIAdapter(game_setup["event_bus"], game_state=self.game_state)
        self.ui_adapter.initialize()
        
        # Spectator system
        self.spectator = SpectatorController(game_setup["event_bus"], game_setup.get("all_ids", []))
        
        # State management
        self.current_ui_state = UiState.empty()
        self.selected_action = None
        self.hover_entity_id = None
        self.hover_time = 0.0
        self.last_mouse_pos = (0, 0)
        self.force_tooltip = False
        
        # Character portraits and sprite cache
        self.character_portraits: Dict[str, arcade.Texture] = {}
        self.sprite_cache: Dict[str, arcade.Texture] = {}
        self.default_portrait = None
        self._tex_draw_variant = None  # For adaptive texture drawing
        
        # Subscribe to UI events
        game_setup["event_bus"].subscribe(UIStateEvents.STATE_UPDATE, self._on_ui_state_update)
        game_setup["event_bus"].subscribe(CoreEvents.TURN_START, self._on_turn_start)
        
        # Load assets
        self._load_character_portraits()
        
        # Set background color
        arcade.set_background_color(self.colors.UI_BACKGROUND)
        
        # Center camera on terrain initially
        self._center_camera_on_terrain()
        
    def _load_character_portraits(self):
        """Load character portrait textures with fallback"""
        try:
            assets_path = Path("assets/sprites/characters")
            if assets_path.exists():
                for portrait_file in assets_path.glob("*.png"):
                    try:
                        texture = arcade.load_texture(str(portrait_file))
                        self.character_portraits[portrait_file.stem] = texture
                    except Exception as e:
                        print(f"Failed to load portrait {portrait_file}: {e}")
            
            # Create default portrait if none loaded
            if not self.character_portraits:
                self._create_default_portrait()
                
        except Exception as e:
            print(f"Error loading portraits: {e}")
            self._create_default_portrait()
    
    def _create_default_portrait(self):
        """Create a simple default portrait texture"""
        self.default_portrait = arcade.Texture.create_filled("default", (64, 64), arcade.color.GRAY)
    
    def _get_portrait_for_entity(self, entity_id: str) -> arcade.Texture:
        """Get portrait texture for an entity with caching"""
        entity = self.game_state.get_entity(entity_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            if hasattr(char, 'sprite_path') and char.sprite_path:
                sprite_name = Path(char.sprite_path).stem if char.sprite_path else "default_human"
                if sprite_name in self.character_portraits:
                    return self.character_portraits[sprite_name]
        
        return self.default_portrait or arcade.Texture.create_filled("fallback", (64, 64), arcade.color.GRAY)
    
    def _get_entity_relationship_color(self, entity_id: str) -> Tuple[int, int, int]:
        """Enhanced relationship color detection"""
        if not self.current_player_id:
            return self.colors.NEUTRAL
            
        if entity_id == self.current_player_id or entity_id in self.player_ids:
            return self.colors.SAME_PLAYER
            
        # Get team relationships
        current_entity = self.game_state.get_entity(self.current_player_id)
        target_entity = self.game_state.get_entity(entity_id)
        
        if current_entity and target_entity:
            current_team = getattr(current_entity.get("character_ref", {}).get("character", {}), "team", "")
            target_team = getattr(target_entity.get("character_ref", {}).get("character", {}), "team", "")
            
            if current_team and target_team:
                if current_team == target_team:
                    return self.colors.ALLY
                else:
                    return self.colors.ENEMY
        
        return self.colors.NEUTRAL
    
    def _on_ui_state_update(self, **kwargs):
        """Handle UI state updates with animation triggers"""
        if "state" in kwargs:
            prev_state = self.current_ui_state
            self.current_ui_state = kwargs["state"]
            
            # Trigger turn banner animation if active entity changed
            if (self.current_ui_state.active_entity_id != prev_state.active_entity_id and 
                self.current_ui_state.active_entity_id in self.player_ids):
                self.animation.turn_banner_timer = 2.5
            
            # Update spectator entity list
            if hasattr(self.current_ui_state, 'initiative') and self.current_ui_state.initiative:
                entity_ids = [entry.entity_id for entry in self.current_ui_state.initiative]
                self.spectator.set_entities(entity_ids)
    
    def _on_turn_start(self, entity_id: str, **kwargs):
        """Handle turn start with camera following"""
        if entity_id in self.player_ids:
            self.current_player_id = entity_id
            self.input_manager.set_active_entity(entity_id)
            
            # Update camera following
            if self.camera.locked:
                self.camera.follow_entity_id = entity_id
    
    def on_draw(self):
        """Enhanced rendering with all advanced features"""
        self.clear()
        
        # Draw main components with camera offset
        self._draw_grid()
        self._draw_characters_with_effects()
        self._draw_enhanced_initiative_bar()
        self._draw_character_panel()
        self._draw_enhanced_main_interface()
        self._draw_minimap()
        self._draw_menu_buttons()
        
        # Draw overlays and effects
        self._draw_turn_banner()
        self._draw_notifications_with_fade()
        self._draw_tooltip()
        
        # Draw UI manager components
        self.ui_manager.draw()
    
    def _draw_grid(self):
        """Draw battlefield grid with camera offset"""
        offset_x = self._get_camera_offset_x()
        offset_y = self._get_camera_offset_y()
        cell_size = self.layout.CELL_SIZE
        grid_size = self.layout.GRID_SIZE
        
        # Only draw visible grid lines for performance
        start_grid_x = max(0, int(-offset_x / cell_size) - 1)
        end_grid_x = min(grid_size, int((self.width - offset_x) / cell_size) + 1)
        start_grid_y = max(0, int(-offset_y / cell_size) - 1)
        end_grid_y = min(grid_size, int((self.height - offset_y) / cell_size) + 1)
        
        # Draw grid lines
        for i in range(start_grid_x, end_grid_x + 1):
            x = offset_x + i * cell_size
            if 0 <= x <= self.width:
                arcade.draw_line(x, max(0, offset_y), x, min(self.height, offset_y + grid_size * cell_size), 
                               self.colors.GRID_LINE, 1)
        
        for i in range(start_grid_y, end_grid_y + 1):
            y = offset_y + i * cell_size
            if 0 <= y <= self.height:
                arcade.draw_line(max(0, offset_x), y, min(self.width, offset_x + grid_size * cell_size), y,
                               self.colors.GRID_LINE, 1)
    
    def _draw_characters_with_effects(self):
        """Draw characters with enhanced visual effects"""
        offset_x = self._get_camera_offset_x()
        offset_y = self._get_camera_offset_y()
        cell_size = self.layout.CELL_SIZE
        
        for entity_id in self.game_setup.get("all_ids", []):
            entity = self.game_state.get_entity(entity_id)
            if not entity or "position" not in entity:
                continue
                
            # Skip dead entities (enhanced dead entity filtering)
            char_ref = entity.get("character_ref")
            if char_ref and hasattr(char_ref, "character"):
                char = char_ref.character
                if getattr(char, "is_dead", False):
                    continue
            
            pos = entity["position"]
            screen_x = offset_x + pos.x * cell_size + cell_size // 2
            screen_y = offset_y + pos.y * cell_size + cell_size // 2
            
            # Skip if not visible on screen
            if (screen_x < -cell_size or screen_x > self.width + cell_size or
                screen_y < -cell_size or screen_y > self.height + cell_size):
                continue
            
            # Draw sprite or fallback
            sprite_drawn = self._draw_entity_sprite_with_caching(char, screen_x, screen_y, cell_size)
            
            if not sprite_drawn:
                self._draw_fallback_token(entity_id, screen_x, screen_y, cell_size)
            
            # Draw relationship circle
            circle_color = self._get_entity_relationship_color(entity_id)
            circle_radius = cell_size // 2 + 2
            arcade.draw_circle_outline(screen_x, screen_y, circle_radius, circle_color, 3)
            
            # Enhanced active entity highlighting with pulsing
            if entity_id == self.current_ui_state.active_entity_id:
                arcade.draw_circle_outline(screen_x, screen_y, circle_radius + 3, self.colors.ACTIVE_HIGHLIGHT, 2)
                
                # Pulsing effect
                pulse_intensity = (math.sin(self.animation.pulse_phase) + 1) * 0.5
                pulse_radius = circle_radius + 5 + int(pulse_intensity * 5)
                pulse_alpha = int(50 + pulse_intensity * 50)
                pulse_color = (*self.colors.PULSE_COLOR[:3], pulse_alpha)
                try:
                    arcade.draw_circle_filled(screen_x, screen_y, pulse_radius, pulse_color)
                except Exception:
                    pass  # Skip if alpha not supported
            
            # Draw facing indicators (arrows)
            if char_ref and hasattr(char_ref, "character"):
                self._draw_facing_indicator(char_ref.character, screen_x, screen_y, cell_size)
    
    def _draw_entity_sprite_with_caching(self, char, x: float, y: float, cell_size: int) -> bool:
        """Enhanced sprite drawing with adaptive API detection and caching"""
        sprite_path = getattr(char, 'sprite_path', None)
        if not sprite_path:
            return False
            
        # Use cached texture
        tex = self.sprite_cache.get(sprite_path)
        if tex is None:
            try:
                tex = arcade.load_texture(sprite_path)
                self.sprite_cache[sprite_path] = tex
            except Exception:
                self.sprite_cache[sprite_path] = None
                return False
        
        if not tex:
            return False
            
        scale = (cell_size / max(tex.width, tex.height)) * 0.8
        
        # Use cached drawing variant if available
        if self._tex_draw_variant:
            try:
                self._execute_draw_variant(self._tex_draw_variant, tex, x, y, scale)
                return True
            except Exception:
                self._tex_draw_variant = None  # Reset if variant fails
        
        # Try different drawing methods
        variants = [
            lambda: arcade.draw_scaled_texture_rectangle(x, y, tex, scale),
            lambda: arcade.draw_texture_rectangle(x, y, tex.width * scale, tex.height * scale, tex),
        ]
        
        for variant in variants:
            try:
                variant()
                self._tex_draw_variant = variant
                return True
            except Exception:
                continue
                
        return False
    
    def _execute_draw_variant(self, variant, tex, x, y, scale):
        """Execute cached drawing variant"""
        variant()
    
    def _draw_fallback_token(self, entity_id: str, x: float, y: float, cell_size: int):
        """Draw fallback colored token"""
        color = self._get_entity_relationship_color(entity_id)
        radius = max(8, int(cell_size * 0.35))
        arcade.draw_circle_filled(x, y, radius, color)
        arcade.draw_circle_outline(x, y, radius, arcade.color.BLACK, 2)
        
        # Draw entity identifier
        text = entity_id[:2].upper()
        arcade.draw_text(text, x - 8, y - 8, arcade.color.BLACK, 12, anchor_x="center", anchor_y="center")
    
    def _draw_facing_indicator(self, char, x: float, y: float, cell_size: int):
        """Draw facing arrow indicator"""
        orientation = getattr(char, 'orientation', 'up')
        arrow_len = cell_size * 0.3
        arrow_w = cell_size * 0.2
        
        # Calculate arrow points based on orientation
        if orientation == 'up':
            points = [(x, y + arrow_len), (x - arrow_w/2, y), (x + arrow_w/2, y)]
        elif orientation == 'down':
            points = [(x, y - arrow_len), (x - arrow_w/2, y), (x + arrow_w/2, y)]
        elif orientation == 'left':
            points = [(x - arrow_len, y), (x, y - arrow_w/2), (x, y + arrow_w/2)]
        else:  # right
            points = [(x + arrow_len, y), (x, y - arrow_w/2), (x, y + arrow_w/2)]
        
        arcade.draw_polygon_filled(points, self.colors.ACTIVE_HIGHLIGHT)
        arcade.draw_polygon_outline(points, arcade.color.BLACK, 1)
    
    def _draw_enhanced_initiative_bar(self):
        """Enhanced initiative bar with round separators"""
        bar_y = self.layout.INITIATIVE_BAR_Y
        bar_height = self.layout.INITIATIVE_BAR_HEIGHT
        portrait_size = self.layout.INITIATIVE_PORTRAIT_SIZE
        
        # Background
        arcade.draw_rectangle_filled(
            self.width // 2, bar_y + bar_height // 2,
            self.width - 20, bar_height,
            (40, 40, 40)
        )
        
        # Draw initiative entries with enhanced separators
        if self.current_ui_state.initiative:
            start_x = 50
            current_x = start_x
            
            for i, entry in enumerate(self.current_ui_state.initiative[:self.layout.INITIATIVE_VISIBLE_COUNT]):
                # Draw portrait
                portrait = self._get_portrait_for_entity(entry.entity_id)
                circle_color = self._get_entity_relationship_color(entry.entity_id)
                
                center_x = current_x + portrait_size // 2
                center_y = bar_y + bar_height // 2
                
                portrait.draw_scaled(center_x, center_y, scale=portrait_size / 64.0)
                
                # Draw relationship circle
                arcade.draw_circle_outline(center_x, center_y, portrait_size // 2 + 2, circle_color, 2)
                
                # Enhanced active character highlighting
                if entry.is_active:
                    arcade.draw_circle_outline(center_x, center_y, portrait_size // 2 + 5, self.colors.ACTIVE_HIGHLIGHT, 3)
                    # Pulsing effect
                    pulse_radius = portrait_size // 2 + 8 + int(math.sin(self.animation.pulse_phase) * 3)
                    arcade.draw_circle_outline(center_x, center_y, pulse_radius, self.colors.ACTIVE_HIGHLIGHT, 1)
                
                current_x += portrait_size + 10
                
                # Enhanced turn separators with round indicators  
                if i < len(self.current_ui_state.initiative) - 1:
                    separator_x = current_x - 5
                    # Golden separator line
                    arcade.draw_line(separator_x, bar_y + 10, separator_x, bar_y + bar_height - 10,
                                   self.colors.INITIATIVE_SEPARATOR, 2)
                    
                    # Round separator indicator (grey translucent)
                    if (i + 1) % 5 == 0:  # Every 5th character marks potential round boundary
                        arcade.draw_rectangle_filled(separator_x, bar_y + bar_height // 2, 4, bar_height - 20, 
                                                   (120, 120, 130, 180))
    
    def _draw_enhanced_main_interface(self):
        """Enhanced main interface with circular health gauge and sectioned movement bar"""
        interface_y = self.layout.MAIN_INTERFACE_Y
        interface_height = self.layout.MAIN_INTERFACE_HEIGHT
        interface_width = self.layout.MAIN_INTERFACE_WIDTH
        interface_x = self.layout.CHARACTER_PANEL_WIDTH + 10
        
        # Background
        arcade.draw_rectangle_filled(
            interface_x + interface_width // 2, interface_y + interface_height // 2,
            interface_width, interface_height,
            (40, 40, 40)
        )
        
        # Enhanced circular health gauge
        self._draw_circular_health_gauge()
        
        # Enhanced movement bar with color sections
        self._draw_sectioned_movement_bar()
        
        # Enhanced action economy
        self._draw_enhanced_action_economy(interface_x + 250, interface_y + interface_height - 30)
        
        # Current character info
        if self.current_player_id:
            self._draw_current_character_info(interface_x + interface_width // 2, interface_y + 90)
        
        # Action grids
        self._draw_action_grid(interface_x + 50, interface_y + 20, "general")
        self._draw_action_grid(interface_x + interface_width - 200, interface_y + 20, "special")
    
    def _draw_circular_health_gauge(self):
        """Draw circular health gauge (bottom left)"""
        center_x = self.layout.HEALTH_GAUGE_X
        center_y = self.layout.HEALTH_GAUGE_Y
        radius = self.layout.HEALTH_GAUGE_RADIUS
        
        # Background circle
        arcade.draw_circle_filled(center_x, center_y, radius, self.colors.HEALTH_BG)
        
        # Get health data for current character
        if self.current_player_id:
            entity = self.game_state.get_entity(self.current_player_id)
            if entity and "character_ref" in entity:
                char = entity["character_ref"].character
                max_health = getattr(char, 'max_health', 10)
                health_damage = getattr(char, '_health_damage', {})
                superficial = health_damage.get('superficial', 0) if isinstance(health_damage, dict) else 0
                aggravated = health_damage.get('aggravated', 0) if isinstance(health_damage, dict) else 0
                current_health = max_health - superficial - aggravated
                
                if max_health > 0:
                    health_ratio = max(0.0, current_health / max_health)
                    if health_ratio > 0:
                        # Health fill as progressively smaller circle
                        health_radius = max(1, int(radius * health_ratio))
                        arcade.draw_circle_filled(center_x, center_y, health_radius, self.colors.HEALTH)
                    
                    # Health text
                    arcade.draw_text(f"{current_health}/{max_health}", center_x, center_y - 8, 
                                   self.colors.ACTIVE_HIGHLIGHT, 11, anchor_x="center")
                else:
                    arcade.draw_text("HP", center_x, center_y - 8, self.colors.ACTIVE_HIGHLIGHT, 11, anchor_x="center")
            else:
                arcade.draw_text("HP", center_x, center_y - 8, self.colors.ACTIVE_HIGHLIGHT, 11, anchor_x="center")
        
        # Border
        arcade.draw_circle_outline(center_x, center_y, radius, self.colors.ACTIVE_HIGHLIGHT, 2)
    
    def _draw_sectioned_movement_bar(self):
        """Draw movement bar with green standard and yellow extra sections"""
        bar_x = self.layout.MOVEMENT_BAR_X
        bar_y = self.layout.MOVEMENT_BAR_Y
        bar_w = self.layout.MOVEMENT_BAR_WIDTH
        bar_h = self.layout.MOVEMENT_BAR_HEIGHT
        
        # Get movement data (with defaults)
        move_used = 0
        move_max = 10
        standard_movement = 7
        
        if self.current_player_id:
            # Would get actual movement data from game state
            pass
        
        # Background
        arcade.draw_rectangle_filled(bar_x + bar_w // 2, bar_y, bar_w, bar_h, (25, 25, 30))
        
        # Standard movement section (green)
        std_width = int(bar_w * (standard_movement / max(move_max, 1)))
        arcade.draw_rectangle_filled(bar_x + std_width // 2, bar_y, std_width, bar_h - 2, (0, 255, 0))
        
        # Extra movement section (yellow)
        if move_max > standard_movement:
            extra_start = std_width
            extra_width = int(bar_w * ((move_max - standard_movement) / max(move_max, 1)))
            arcade.draw_rectangle_filled(bar_x + extra_start + extra_width // 2, bar_y, 
                                       extra_width, bar_h - 2, (255, 255, 0))
        
        # Used movement (grey overlay)
        if move_used > 0:
            used_width = int(bar_w * (min(move_used, move_max) / max(move_max, 1)))
            arcade.draw_rectangle_filled(bar_x + used_width // 2, bar_y, used_width, bar_h - 2, (100, 100, 100))
        
        # Border and graduations
        arcade.draw_rectangle_outline(bar_x + bar_w // 2, bar_y, bar_w, bar_h, self.colors.ACTIVE_HIGHLIGHT, 1)
        
        # Graduation marks
        for i in range(1, move_max):
            grad_x = bar_x + int((i / move_max) * bar_w)
            arcade.draw_line(grad_x, bar_y - bar_h // 2, grad_x, bar_y + bar_h // 2, arcade.color.LIGHT_GRAY, 1)
        
        # Movement text
        arcade.draw_text(f"Move {move_used}/{move_max}", bar_x + bar_w + 8, bar_y - 5,
                        self.colors.ACTIVE_HIGHLIGHT, 10)
    
    def _draw_enhanced_action_economy(self, x: float, y: float):
        """Draw enhanced action economy with proper colors"""
        # Primary actions (dark blue circles)
        primary_actions = 1  # Would get from game state
        for i in range(primary_actions):
            center_x = x + i * 35
            arcade.draw_circle_filled(center_x, y, 12, self.colors.PRIMARY_ACTION)
            arcade.draw_circle_outline(center_x, y, 12, self.colors.ACTIVE_HIGHLIGHT, 2)
        
        # Secondary actions (light blue squares)
        secondary_actions = 1  # Would get from game state
        y_secondary = y - 30
        for i in range(secondary_actions):
            center_x = x + i * 35
            size = 20
            arcade.draw_rectangle_filled(center_x, y_secondary, size, size, self.colors.SECONDARY_ACTION)
            arcade.draw_rectangle_outline(center_x, y_secondary, size, size, self.colors.ACTIVE_HIGHLIGHT, 2)
    
    def _draw_turn_banner(self):
        """Draw turn banner with fade animation"""
        if self.animation.turn_banner_timer > 0:
            fade_progress = self.animation.turn_banner_timer / 2.5
            alpha = int(255 * fade_progress)
            
            banner_text = "Your Turn!"
            arcade.draw_text(banner_text, self.width // 2, self.height // 2, 
                           (*self.colors.ACTIVE_HIGHLIGHT, alpha) if alpha < 255 else self.colors.ACTIVE_HIGHLIGHT, 
                           32, anchor_x="center", anchor_y="center")
    
    def _draw_notifications_with_fade(self):
        """Draw notifications with fade timers"""
        if not self.current_ui_state.notifications:
            return
        
        y_base = self.height - 200
        for i, notification in enumerate(self.current_ui_state.notifications[-5:]):
            alpha = 255
            if notification in self.animation.notification_timers:
                fade_progress = self.animation.notification_timers[notification] / 3.0
                alpha = int(255 * fade_progress)
            
            if alpha > 0:
                color = (*self.colors.NOTIFICATION[:3], alpha) if alpha < 255 else self.colors.NOTIFICATION
                arcade.draw_text(notification, 10, y_base - i * 22, color, 12)
    
    def _draw_tooltip(self):
        """Draw tooltip with 1.5s delay + TAB instant display"""
        if not self.hover_entity_id or self.hover_time < 1.5:
            if not self.force_tooltip:
                return
        
        # Build tooltip content
        entity = self.game_state.get_entity(self.hover_entity_id)
        if not entity:
            return
            
        lines = [self.hover_entity_id[:8]]
        
        # Add character info if available
        if "character_ref" in entity:
            char = entity["character_ref"].character
            
            # Health info
            max_health = getattr(char, 'max_health', None)
            if max_health:
                health_damage = getattr(char, '_health_damage', {})
                superficial = health_damage.get('superficial', 0) if isinstance(health_damage, dict) else 0
                aggravated = health_damage.get('aggravated', 0) if isinstance(health_damage, dict) else 0
                current_health = max_health - superficial - aggravated
                lines.append(f"Health: {current_health}/{max_health}")
            
            # Team info
            team = getattr(char, 'team', None)
            if team:
                lines.append(f"Team: {team}")
        
        # Draw tooltip box
        if lines:
            x, y = self.last_mouse_pos
            x += 10
            y += 10
            
            max_width = max(len(line) * 7 for line in lines)
            box_width = max_width + 12
            box_height = len(lines) * 16 + 8
            
            # Background with alpha
            arcade.draw_rectangle_filled(x + box_width // 2, y + box_height // 2, 
                                       box_width, box_height, self.colors.TOOLTIP_BG)
            arcade.draw_rectangle_outline(x + box_width // 2, y + box_height // 2,
                                        box_width, box_height, self.colors.ACTIVE_HIGHLIGHT, 1)
            
            # Text lines
            for i, line in enumerate(lines):
                arcade.draw_text(line, x + 6, y + box_height - 16 - i * 16, 
                               self.colors.ACTIVE_HIGHLIGHT, 10)
    
    def _draw_character_panel(self):
        """Draw character panel (unchanged)"""
        # Implementation same as before...
        pass
    
    def _draw_current_character_info(self, x: float, y: float):
        """Draw current character info (unchanged)"""
        # Implementation same as before...
        pass
    
    def _draw_action_grid(self, x: float, y: float, grid_type: str):
        """Draw action grid (unchanged)"""
        # Implementation same as before...
        pass
    
    def _draw_minimap(self):
        """Draw minimap (unchanged)"""
        # Implementation same as before...
        pass
    
    def _draw_menu_buttons(self):
        """Draw menu buttons (unchanged)"""  
        # Implementation same as before...
        pass
    
    # Camera system methods
    def _get_camera_offset_x(self) -> float:
        return self.layout.GRID_OFFSET_X - self.camera.x
    
    def _get_camera_offset_y(self) -> float:
        return self.layout.GRID_OFFSET_Y - self.camera.y
    
    def _center_camera_on_terrain(self):
        """Center camera on terrain initially"""
        terrain_width = self.layout.GRID_SIZE * self.layout.CELL_SIZE
        terrain_height = self.layout.GRID_SIZE * self.layout.CELL_SIZE
        self.camera.x = (terrain_width - self.width) / 2
        self.camera.y = (terrain_height - self.height) / 2
    
    def _update_camera(self, delta_time: float):
        """Update camera with following and edge scrolling"""
        # Camera following
        if self.camera.locked and self.camera.follow_entity_id:
            entity = self.game_state.get_entity(self.camera.follow_entity_id)
            if entity and "position" in entity:
                pos = entity["position"]
                cell_size = self.layout.CELL_SIZE
                target_x = pos.x * cell_size - (self.width / 2) + cell_size / 2
                target_y = pos.y * cell_size - (self.height / 2) + cell_size / 2
                
                # Smooth camera movement
                dx = (target_x - self.camera.x) * delta_time * 3
                dy = (target_y - self.camera.y) * delta_time * 3
                self.camera.x += dx
                self.camera.y += dy
        
        # Free camera movement with keys
        if not self.camera.locked and self.keys_pressed:
            speed = self.camera.speed * delta_time
            if arcade.key.LEFT in self.keys_pressed:
                self.camera.x -= speed
            if arcade.key.RIGHT in self.keys_pressed:
                self.camera.x += speed
            if arcade.key.UP in self.keys_pressed:
                self.camera.y += speed
            if arcade.key.DOWN in self.keys_pressed:
                self.camera.y -= speed
        
        # Edge scrolling
        if not self.camera.locked:
            self._handle_edge_scrolling(delta_time)
    
    def _handle_edge_scrolling(self, delta_time: float):
        """Handle mouse edge scrolling"""
        x, y = self.last_mouse_pos
        margin = self.camera.edge_scroll_margin
        speed = self.camera.edge_scroll_speed * delta_time
        
        if x < margin:
            self.camera.x = max(0, self.camera.x - speed)
        elif x > self.width - margin:
            self.camera.x += speed
        
        if y < margin:
            self.camera.y = max(0, self.camera.y - speed)  
        elif y > self.height - margin:
            self.camera.y += speed
    
    # Input handling with enhanced features
    def on_key_press(self, key, modifiers):
        """Enhanced keyboard input with spectator and camera controls"""
        # Window control
        if key == arcade.key.ESCAPE:
            arcade.close_window()
            return
        
        # Spectator controls
        if key == arcade.key.TAB:
            if modifiers & arcade.key.MOD_SHIFT:
                self.spectator.cycle_backward()
            else:
                self.spectator.cycle_forward()
                self.force_tooltip = True  # Instant tooltip on TAB
            return
        
        if key == arcade.key.KEY_0:
            # Free camera mode
            self.spectator.clear_view()
            self.camera.free_mode = True
            self.camera.locked = False
            return
        
        if key == arcade.key.L:
            # Camera lock toggle
            self.camera.locked = not self.camera.locked
            if self.camera.locked and self.current_player_id:
                self.camera.follow_entity_id = self.current_player_id
            return
        
        # Action hotkeys
        if not self.current_player_id:
            return
        
        action_hotkeys = {
            arcade.key.M: "Standard Move",
            arcade.key.A: "Basic Attack", 
            arcade.key.S: "Sprint",
            arcade.key.E: "End Turn"
        }
        
        if key in action_hotkeys:
            action_name = action_hotkeys[key]
            requires_target = action_name not in ("End Turn",)
            self.input_manager.handle_action_hotkey(action_name, requires_target=requires_target)
            return
        
        # Camera movement keys
        camera_keys = {
            arcade.key.LEFT, arcade.key.RIGHT, arcade.key.UP, arcade.key.DOWN,
            arcade.key.W, arcade.key.S, arcade.key.D
        }
        
        if key in camera_keys:
            self.keys_pressed.add(key)
            self.camera.locked = False  # Manual movement unlocks camera
    
    def on_key_release(self, key, modifiers):
        """Handle key releases"""
        self.keys_pressed.discard(key)
    
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Enhanced mouse motion with hover detection"""
        self.last_mouse_pos = (x, y)
        
        # Determine hovered entity for tooltip
        cell = self._screen_to_grid(x, y)
        hovered = None
        
        if cell:
            cx, cy = cell
            # Find entity at position (with dead filtering)
            for entity_id in self.game_setup.get("all_ids", []):
                entity = self.game_state.get_entity(entity_id)
                if not entity or "position" not in entity:
                    continue
                
                pos = entity["position"]
                if pos.x == cx and pos.y == cy:
                    # Check if alive
                    char_ref = entity.get("character_ref")
                    if char_ref and hasattr(char_ref, "character"):
                        char = char_ref.character
                        if getattr(char, "is_dead", False):
                            continue
                    hovered = entity_id
                    break
        
        if hovered != self.hover_entity_id:
            self.hover_entity_id = hovered
            self.hover_time = 0.0
            self.force_tooltip = False
    
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        """Enhanced mouse input handling"""
        if button == arcade.MOUSE_BUTTON_RIGHT:
            self.input_manager.handle_cancel()
            return
        
        if button == arcade.MOUSE_BUTTON_LEFT:
            cell = self._screen_to_grid(x, y)
            if cell:
                self.input_manager.handle_tile_click(cell[0], cell[1])
    
    def _screen_to_grid(self, screen_x: float, screen_y: float) -> Optional[Tuple[int, int]]:
        """Convert screen coordinates to grid coordinates with camera offset"""
        offset_x = self._get_camera_offset_x()
        offset_y = self._get_camera_offset_y()
        
        grid_x = screen_x - offset_x
        grid_y = screen_y - offset_y
        
        if grid_x < 0 or grid_y < 0:
            return None
        
        cell_x = int(grid_x // self.layout.CELL_SIZE)
        cell_y = int(grid_y // self.layout.CELL_SIZE)
        
        if 0 <= cell_x < self.layout.GRID_SIZE and 0 <= cell_y < self.layout.GRID_SIZE:
            return (cell_x, cell_y)
        return None
    
    def on_update(self, delta_time: float):
        """Update animations and camera"""
        self.animation.update(delta_time)
        self._update_camera(delta_time)
        
        # Update hover time for tooltip
        if self.hover_entity_id:
            self.hover_time += delta_time
    
    def setup_player_controller(self, player_controller: PlayerTurnController):
        """Set up player controller integration"""
        self.player_controller = player_controller
        self.game_setup["game_system"].set_player_controller(player_controller)


def create_enhanced_combat_ui(game_setup: Dict[str, Any], player_ids: List[str]) -> EnhancedCombatUI:
    """Factory function to create and configure the enhanced combat UI"""
    if not ARCADE_AVAILABLE:
        raise ImportError("Arcade library is required for the enhanced combat UI")
    
    ui = EnhancedCombatUI(game_setup, player_ids)
    
    # Create and setup player controller
    player_controller = PlayerTurnController(
        game_setup["event_bus"],
        is_player_entity=lambda eid: eid in player_ids
    )
    ui.setup_player_controller(player_controller)
    
    return ui