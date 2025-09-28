"""Combat UI for MV Combat System
==================================

A comprehensive Arcade-based user interface for the combat system featuring:
- Grid-based battlefield with character portraits
- Dynamic initiative bar with scrolling
- Character status panels
- Action selection interfaces
- Minimap with zoom controls
- Resource gauges (movement, health, willpower, blood pool)

Based on the UI design specification with:
- Same-player characters: Green circles
- Allies: Blue circles  
- Neutral: Yellow circles
- Enemies: Red circles
"""
from __future__ import annotations
import math
import os
from typing import Dict, List, Optional, Tuple, Any
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
        key = type('key', (), {
            'A': ord('A'), 'M': ord('M'), 'E': ord('E'), 'ESCAPE': 27
        })()
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

from interface.input_manager import InputManager
from interface.player_turn_controller import PlayerTurnController
from interface.ui_adapter import UIAdapter
from interface.ui_state import UiState, InitiativeEntry
from interface.event_constants import UIStateEvents, CoreEvents


@dataclass
class ColorScheme:
    """Color definitions for the UI"""
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
    
    # Resource bars
    HEALTH: Tuple[int, int, int] = (0, 255, 0)          # Green
    WILLPOWER: Tuple[int, int, int] = (64, 224, 208)    # Turquoise
    BLOOD_POOL: Tuple[int, int, int] = (139, 0, 0)      # Dark red
    
    # Action icons
    PRIMARY_ACTION: Tuple[int, int, int] = (255, 255, 0)        # Yellow
    SECONDARY_ACTION: Tuple[int, int, int] = (255, 165, 0)      # Orange
    
    # Backgrounds
    UI_BACKGROUND: Tuple[int, int, int] = (50, 50, 50)          # Dark grey
    GRID_LINE: Tuple[int, int, int] = (128, 128, 128)           # Grey
    MINIMAP_BACKGROUND: Tuple[int, int, int] = (30, 30, 30)     # Very dark grey


@dataclass
class UILayout:
    """Layout configuration for UI elements"""
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
    
    # Main interface (bottom)
    MAIN_INTERFACE_HEIGHT: int = 180
    MAIN_INTERFACE_Y: int = 10
    MAIN_INTERFACE_WIDTH: int = WINDOW_WIDTH - 400  # Leave space for menus
    
    # Minimap
    MINIMAP_SIZE: int = 150
    MINIMAP_X: int = 10
    MINIMAP_Y: int = WINDOW_HEIGHT - MINIMAP_SIZE - INITIATIVE_BAR_HEIGHT - 20
    
    # Menus (right side)
    MENU_PANEL_WIDTH: int = 150
    MENU_PANEL_X: int = WINDOW_WIDTH - MENU_PANEL_WIDTH - 10


class CombatUI(arcade.Window):
    """Main combat UI window"""
    
    def __init__(self, game_setup: Dict[str, Any], player_ids: List[str]):
        if not ARCADE_AVAILABLE:
            raise ImportError("Arcade library is required for the combat UI")
            
        super().__init__(UILayout.WINDOW_WIDTH, UILayout.WINDOW_HEIGHT, "MV Combat System")
        
        self.game_setup = game_setup
        self.game_state = game_setup["game_state"]
        self.player_ids = set(player_ids)
        self.current_player_id = player_ids[0] if player_ids else None
        
        # UI components
        self.layout = UILayout()
        self.colors = ColorScheme()
        self.ui_manager = arcade.gui.UIManager()
        self.ui_manager.enable()
        
        # Game interface components
        self.input_manager = InputManager(game_setup["event_bus"])
        self.ui_adapter = UIAdapter(game_setup["event_bus"], game_state=self.game_state)
        self.ui_adapter.initialize()
        
        # State management
        self.current_ui_state = UiState.empty()
        self.selected_action = None
        self.initiative_scroll_offset = 0
        self.minimap_zoom = 1.0
        self.minimap_center_on_player = True
        
        # Character portraits cache
        self.character_portraits: Dict[str, arcade.Texture] = {}
        self.default_portrait = None
        
        # Subscribe to UI events
        game_setup["event_bus"].subscribe(UIStateEvents.STATE_UPDATE, self._on_ui_state_update)
        game_setup["event_bus"].subscribe(CoreEvents.TURN_START, self._on_turn_start)
        
        # Load assets
        self._load_character_portraits()
        
        # Set background color
        arcade.set_background_color(self.colors.UI_BACKGROUND)
        
    def _load_character_portraits(self):
        """Load character portrait textures"""
        try:
            assets_path = Path("assets/sprites/characters")
            if assets_path.exists():
                for portrait_file in assets_path.glob("*.png"):
                    try:
                        texture = arcade.load_texture(str(portrait_file))
                        self.character_portraits[portrait_file.stem] = texture
                    except Exception as e:
                        print(f"Failed to load portrait {portrait_file}: {e}")
            
            # Create a default portrait if none loaded
            if not self.character_portraits:
                self._create_default_portrait()
                
        except Exception as e:
            print(f"Error loading portraits: {e}")
            self._create_default_portrait()
    
    def _create_default_portrait(self):
        """Create a simple default portrait texture"""
        # Create a simple colored square as default
        image = arcade.Texture.create_empty("default", (64, 64))
        image = arcade.Texture.create_filled("default", (64, 64), arcade.color.GRAY)
        self.default_portrait = image
    
    def _get_portrait_for_entity(self, entity_id: str) -> arcade.Texture:
        """Get the portrait texture for an entity"""
        entity = self.game_state.get_entity(entity_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            if hasattr(char, 'sprite_path') and char.sprite_path:
                # Try to get the portrait by sprite path
                sprite_name = Path(char.sprite_path).stem if char.sprite_path else "default_human"
                if sprite_name in self.character_portraits:
                    return self.character_portraits[sprite_name]
        
        # Return a default portrait
        return self.default_portrait or self.character_portraits.get("default_human", 
                arcade.Texture.create_filled("fallback", (64, 64), arcade.color.GRAY))
    
    def _get_entity_relationship_color(self, entity_id: str) -> Tuple[int, int, int]:
        """Get the relationship color for an entity relative to current player"""
        if not self.current_player_id:
            return self.colors.NEUTRAL
            
        if entity_id == self.current_player_id:
            return self.colors.SAME_PLAYER
        
        # Check if it's a player-controlled entity
        if entity_id in self.player_ids:
            return self.colors.SAME_PLAYER
            
        # Get team relationships (simplified for now)
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
        """Handle UI state updates"""
        if "state" in kwargs:
            self.current_ui_state = kwargs["state"]
    
    def _on_turn_start(self, entity_id: str, **kwargs):
        """Handle turn start events"""
        if entity_id in self.player_ids:
            self.current_player_id = entity_id
            self.input_manager.set_active_entity(entity_id)
    
    def on_draw(self):
        """Render the UI"""
        self.clear()
        
        # Draw main components
        self._draw_grid()
        self._draw_characters()
        self._draw_initiative_bar()
        self._draw_character_panel()
        self._draw_main_interface()
        self._draw_minimap()
        self._draw_menu_buttons()
        
        # Draw UI manager components
        self.ui_manager.draw()
    
    def _draw_grid(self):
        """Draw the battlefield grid"""
        start_x = self.layout.GRID_OFFSET_X
        start_y = self.layout.GRID_OFFSET_Y
        cell_size = self.layout.CELL_SIZE
        grid_size = self.layout.GRID_SIZE
        
        # Draw grid lines
        for i in range(grid_size + 1):
            # Vertical lines
            x = start_x + i * cell_size
            arcade.draw_line(x, start_y, x, start_y + grid_size * cell_size, 
                           self.colors.GRID_LINE, 1)
            
            # Horizontal lines  
            y = start_y + i * cell_size
            arcade.draw_line(start_x, y, start_x + grid_size * cell_size, y,
                           self.colors.GRID_LINE, 1)
    
    def _draw_characters(self):
        """Draw characters on the grid"""
        start_x = self.layout.GRID_OFFSET_X
        start_y = self.layout.GRID_OFFSET_Y
        cell_size = self.layout.CELL_SIZE
        
        # Draw all entities
        for entity_id in self.game_setup.get("all_ids", []):
            entity = self.game_state.get_entity(entity_id)
            if entity and "position" in entity:
                pos = entity["position"]
                
                # Calculate screen position
                screen_x = start_x + pos.x * cell_size + cell_size // 2
                screen_y = start_y + pos.y * cell_size + cell_size // 2
                
                # Get portrait and relationship color
                portrait = self._get_portrait_for_entity(entity_id)
                circle_color = self._get_entity_relationship_color(entity_id)
                
                # Draw character portrait
                portrait.draw_scaled(screen_x, screen_y, scale=cell_size / 64.0)
                
                # Draw relationship circle
                circle_radius = cell_size // 2 + 2
                arcade.draw_circle_outline(screen_x, screen_y, circle_radius, 
                                         circle_color, 3)
                
                # Highlight active character
                if entity_id == self.current_ui_state.active_entity_id:
                    arcade.draw_circle_outline(screen_x, screen_y, circle_radius + 3,
                                             arcade.color.WHITE, 2)
    
    def _draw_initiative_bar(self):
        """Draw the initiative bar at the top"""
        bar_y = self.layout.INITIATIVE_BAR_Y
        bar_height = self.layout.INITIATIVE_BAR_HEIGHT
        portrait_size = self.layout.INITIATIVE_PORTRAIT_SIZE
        visible_count = self.layout.INITIATIVE_VISIBLE_COUNT
        
        # Background
        arcade.draw_rectangle_filled(
            self.width // 2, bar_y + bar_height // 2,
            self.width - 20, bar_height,
            (40, 40, 40)
        )
        
        # Draw initiative entries
        if self.current_ui_state.initiative:
            start_x = 50
            current_x = start_x - self.initiative_scroll_offset
            
            for i, entry in enumerate(self.current_ui_state.initiative):
                if i >= visible_count + self.initiative_scroll_offset // (portrait_size + 10):
                    break
                    
                if current_x > self.width:
                    break
                    
                if current_x + portrait_size > 0:
                    # Draw portrait
                    portrait = self._get_portrait_for_entity(entry.entity_id)
                    circle_color = self._get_entity_relationship_color(entry.entity_id)
                    
                    center_x = current_x + portrait_size // 2
                    center_y = bar_y + bar_height // 2
                    
                    portrait.draw_scaled(center_x, center_y, scale=portrait_size / 64.0)
                    
                    # Draw relationship circle
                    arcade.draw_circle_outline(center_x, center_y, portrait_size // 2 + 2,
                                             circle_color, 2)
                    
                    # Highlight active character
                    if entry.is_active:
                        arcade.draw_circle_outline(center_x, center_y, portrait_size // 2 + 5,
                                                 arcade.color.WHITE, 3)
                
                current_x += portrait_size + 10
                
                # Draw turn separator
                if i < len(self.current_ui_state.initiative) - 1:
                    separator_x = current_x - 5
                    arcade.draw_line(separator_x, bar_y + 10, separator_x, bar_y + bar_height - 10,
                                   self.colors.INITIATIVE_SEPARATOR, 2)
    
    def _draw_character_panel(self):
        """Draw the left character panel"""
        panel_width = self.layout.CHARACTER_PANEL_WIDTH
        panel_height = self.layout.CHARACTER_PANEL_HEIGHT
        
        # Background
        arcade.draw_rectangle_filled(
            panel_width // 2, panel_height // 2 + self.layout.MAIN_INTERFACE_Y + self.layout.MAIN_INTERFACE_HEIGHT,
            panel_width, panel_height,
            (30, 30, 30)
        )
        
        # Draw player-controlled character portraits
        current_y = self.height - self.layout.INITIATIVE_BAR_HEIGHT - 50
        portrait_size = self.layout.CHARACTER_PORTRAIT_SIZE
        
        for entity_id in self.player_ids:
            if current_y < self.layout.MAIN_INTERFACE_HEIGHT + portrait_size:
                break
                
            portrait = self._get_portrait_for_entity(entity_id)
            center_x = panel_width // 2
            
            # Draw portrait
            portrait.draw_scaled(center_x, current_y, scale=portrait_size / 64.0)
            
            # Draw green circle for player characters
            arcade.draw_circle_outline(center_x, current_y, portrait_size // 2 + 2,
                                     self.colors.SAME_PLAYER, 2)
            
            # Highlight current character
            if entity_id == self.current_player_id:
                arcade.draw_circle_outline(center_x, current_y, portrait_size // 2 + 5,
                                         arcade.color.WHITE, 3)
            
            current_y -= portrait_size + 20
    
    def _draw_main_interface(self):
        """Draw the main interface at the bottom"""
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
        
        # Movement gauge (top left)
        self._draw_movement_gauge(interface_x + 20, interface_y + interface_height - 30)
        
        # Action icons (next to movement gauge)
        self._draw_action_icons(interface_x + 200, interface_y + interface_height - 30)
        
        # Current character portrait and stats (middle)
        if self.current_player_id:
            self._draw_current_character_info(interface_x + interface_width // 2, interface_y + 90)
        
        # Action grids (left and right of character info)
        self._draw_action_grid(interface_x + 50, interface_y + 20, "general")
        self._draw_action_grid(interface_x + interface_width - 200, interface_y + 20, "special")
    
    def _draw_movement_gauge(self, x: float, y: float):
        """Draw the movement gauge"""
        gauge_width = 150
        gauge_height = 20
        
        # Background
        arcade.draw_rectangle_filled(x + gauge_width // 2, y, gauge_width, gauge_height, 
                                   (20, 20, 20))
        arcade.draw_rectangle_outline(x + gauge_width // 2, y, gauge_width, gauge_height,
                                    arcade.color.WHITE, 1)
        
        # For now, show a simple movement gauge (would need actual movement data)
        normal_movement = 7  # Default movement
        sprint_movement = 8  # Additional sprint movement
        used_movement = 0    # Used movement (would come from game state)
        
        # Normal movement (light blue)
        normal_width = (normal_movement / 15.0) * gauge_width
        arcade.draw_rectangle_filled(x + normal_width // 2, y, normal_width, gauge_height - 2,
                                   self.colors.MOVEMENT_NORMAL)
        
        # Sprint movement (darker blue)
        sprint_start = normal_width
        sprint_width = (sprint_movement / 15.0) * gauge_width
        arcade.draw_rectangle_filled(x + sprint_start + sprint_width // 2, y, 
                                   sprint_width, gauge_height - 2,
                                   self.colors.MOVEMENT_SPRINT)
        
        # Used movement (dark grey overlay)
        if used_movement > 0:
            used_width = (used_movement / 15.0) * gauge_width
            arcade.draw_rectangle_filled(x + used_width // 2, y, used_width, gauge_height - 2,
                                       self.colors.MOVEMENT_CONSUMED)
        
        # Graduations
        for i in range(1, 15):
            grad_x = x + (i / 15.0) * gauge_width
            arcade.draw_line(grad_x, y - gauge_height // 2, grad_x, y + gauge_height // 2,
                           arcade.color.LIGHT_GRAY, 1)
    
    def _draw_action_icons(self, x: float, y: float):
        """Draw remaining action icons"""
        icon_size = 30
        
        # Primary actions (yellow circles)
        primary_actions = 1  # Would come from game state
        for i in range(primary_actions):
            center_x = x + i * (icon_size + 10)
            arcade.draw_circle_filled(center_x, y, icon_size // 2, 
                                    self.colors.PRIMARY_ACTION)
            arcade.draw_circle_outline(center_x, y, icon_size // 2,
                                     arcade.color.BLACK, 2)
        
        # Secondary actions (orange triangles)  
        secondary_actions = 1  # Would come from game state
        for i in range(secondary_actions):
            center_x = x + (primary_actions + i) * (icon_size + 10)
            
            # Draw triangle
            points = [
                (center_x, y + icon_size // 2),
                (center_x - icon_size // 2, y - icon_size // 2),
                (center_x + icon_size // 2, y - icon_size // 2)
            ]
            arcade.draw_polygon_filled(points, self.colors.SECONDARY_ACTION)
            arcade.draw_polygon_outline(points, arcade.color.BLACK, 2)
    
    def _draw_current_character_info(self, x: float, y: float):
        """Draw current character portrait and resource bars"""
        if not self.current_player_id:
            return
            
        # Character portrait
        portrait_size = 80
        portrait = self._get_portrait_for_entity(self.current_player_id)
        portrait.draw_scaled(x, y + 20, scale=portrait_size / 64.0)
        
        # Resource bars below portrait
        bar_width = 100
        bar_height = 8
        bar_spacing = 15
        
        entity = self.game_state.get_entity(self.current_player_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            
            # Health bar (green)
            health_y = y - 30
            max_health = getattr(char, 'max_health', 10)
            current_health = max_health - getattr(char, '_health_damage', {}).get('superficial', 0) - getattr(char, '_health_damage', {}).get('aggravated', 0)
            health_ratio = current_health / max_health if max_health > 0 else 0
            
            arcade.draw_rectangle_filled(x, health_y, bar_width, bar_height, (20, 20, 20))
            arcade.draw_rectangle_filled(x - bar_width//2 + (bar_width * health_ratio)//2, health_y,
                                       bar_width * health_ratio, bar_height, self.colors.HEALTH)
            arcade.draw_rectangle_outline(x, health_y, bar_width, bar_height, arcade.color.WHITE, 1)
            
            # Willpower bar (turquoise)
            willpower_y = y - 45
            max_willpower = getattr(char, 'max_willpower', 5)
            current_willpower = max_willpower - getattr(char, '_willpower_damage', {}).get('superficial', 0) - getattr(char, '_willpower_damage', {}).get('aggravated', 0)
            willpower_ratio = current_willpower / max_willpower if max_willpower > 0 else 0
            
            arcade.draw_rectangle_filled(x, willpower_y, bar_width, bar_height, (20, 20, 20))
            arcade.draw_rectangle_filled(x - bar_width//2 + (bar_width * willpower_ratio)//2, willpower_y,
                                       bar_width * willpower_ratio, bar_height, self.colors.WILLPOWER)
            arcade.draw_rectangle_outline(x, willpower_y, bar_width, bar_height, arcade.color.WHITE, 1)
            
            # Blood pool bar (red) - for vampires
            blood_y = y - 60
            if hasattr(char, 'blood_pool'):
                max_blood = getattr(char, 'max_blood_pool', 10)
                current_blood = getattr(char, 'blood_pool', 0)
                blood_ratio = current_blood / max_blood if max_blood > 0 else 0
                
                arcade.draw_rectangle_filled(x, blood_y, bar_width, bar_height, (20, 20, 20))
                arcade.draw_rectangle_filled(x - bar_width//2 + (bar_width * blood_ratio)//2, blood_y,
                                           bar_width * blood_ratio, bar_height, self.colors.BLOOD_POOL)
                arcade.draw_rectangle_outline(x, blood_y, bar_width, bar_height, arcade.color.WHITE, 1)
    
    def _draw_action_grid(self, x: float, y: float, grid_type: str):
        """Draw an action grid (general or special actions)"""
        grid_size = 3  # 3x3 grid
        icon_size = 40
        icon_spacing = 45
        
        # Title
        title = "Actions" if grid_type == "general" else "Powers"
        arcade.draw_text(title, x, y + grid_size * icon_spacing + 10,
                        arcade.color.WHITE, 12, anchor_x="center")
        
        for row in range(grid_size):
            for col in range(grid_size):
                icon_x = x + (col - 1) * icon_spacing
                icon_y = y + (row - 1) * icon_spacing
                
                # Draw grid cell background
                arcade.draw_rectangle_filled(icon_x, icon_y, icon_size, icon_size,
                                           (60, 60, 60))
                arcade.draw_rectangle_outline(icon_x, icon_y, icon_size, icon_size,
                                            arcade.color.GRAY, 1)
                
                # TODO: Draw actual action icons based on available actions
                # For now, just show empty cells
    
    def _draw_minimap(self):
        """Draw the minimap"""
        minimap_x = self.layout.MINIMAP_X
        minimap_y = self.layout.MINIMAP_Y
        minimap_size = self.layout.MINIMAP_SIZE
        
        # Background
        arcade.draw_rectangle_filled(
            minimap_x + minimap_size // 2, minimap_y + minimap_size // 2,
            minimap_size, minimap_size,
            self.colors.MINIMAP_BACKGROUND
        )
        arcade.draw_rectangle_outline(
            minimap_x + minimap_size // 2, minimap_y + minimap_size // 2,
            minimap_size, minimap_size,
            arcade.color.WHITE, 2
        )
        
        # Draw entities as dots
        grid_to_minimap = minimap_size / self.layout.GRID_SIZE
        
        for entity_id in self.game_setup.get("all_ids", []):
            entity = self.game_state.get_entity(entity_id)
            if entity and "position" in entity:
                pos = entity["position"]
                
                dot_x = minimap_x + pos.x * grid_to_minimap
                dot_y = minimap_y + pos.y * grid_to_minimap
                dot_color = self._get_entity_relationship_color(entity_id)
                
                arcade.draw_circle_filled(dot_x, dot_y, 3, dot_color)
        
        # Zoom controls (simple + and - buttons)
        arcade.draw_text("+", minimap_x + minimap_size - 15, minimap_y + minimap_size - 15,
                        arcade.color.WHITE, 14, anchor_x="center")
        arcade.draw_text("-", minimap_x + minimap_size - 15, minimap_y + minimap_size - 35,
                        arcade.color.WHITE, 14, anchor_x="center")
    
    def _draw_menu_buttons(self):
        """Draw menu buttons on the right side"""
        menu_x = self.layout.MENU_PANEL_X
        button_width = 120
        button_height = 40
        button_spacing = 50
        
        menus = ["Character", "Inventory", "Settings", "Help"]
        
        for i, menu_name in enumerate(menus):
            button_y = self.height - 100 - i * button_spacing
            
            # Button background
            arcade.draw_rectangle_filled(menu_x + button_width // 2, button_y,
                                       button_width, button_height,
                                       (70, 70, 70))
            arcade.draw_rectangle_outline(menu_x + button_width // 2, button_y,
                                        button_width, button_height,
                                        arcade.color.WHITE, 1)
            
            # Button text
            arcade.draw_text(menu_name, menu_x + button_width // 2, button_y,
                           arcade.color.WHITE, 12, anchor_x="center", anchor_y="center")
    
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        """Handle mouse clicks"""
        if button == arcade.MOUSE_BUTTON_LEFT:
            # Check if click is on the grid
            if self._is_click_on_grid(x, y):
                grid_x, grid_y = self._screen_to_grid(x, y)
                self._handle_grid_click(grid_x, grid_y)
            
            # Check other UI elements
            elif self._is_click_on_minimap(x, y):
                self._handle_minimap_click(x, y)
                
            elif self._is_click_on_initiative_bar(x, y):
                self._handle_initiative_bar_click(x, y)
    
    def _is_click_on_grid(self, x: float, y: float) -> bool:
        """Check if click is within the grid area"""
        grid_start_x = self.layout.GRID_OFFSET_X
        grid_start_y = self.layout.GRID_OFFSET_Y
        grid_end_x = grid_start_x + self.layout.GRID_SIZE * self.layout.CELL_SIZE
        grid_end_y = grid_start_y + self.layout.GRID_SIZE * self.layout.CELL_SIZE
        
        return grid_start_x <= x <= grid_end_x and grid_start_y <= y <= grid_end_y
    
    def _screen_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Convert screen coordinates to grid coordinates"""
        grid_x = int((x - self.layout.GRID_OFFSET_X) // self.layout.CELL_SIZE)
        grid_y = int((y - self.layout.GRID_OFFSET_Y) // self.layout.CELL_SIZE)
        return grid_x, grid_y
    
    def _handle_grid_click(self, grid_x: int, grid_y: int):
        """Handle clicks on the grid"""
        if not self.current_player_id or not self.input_manager:
            return
            
        if self.selected_action:
            # Target selection for action
            self.input_manager.handle_tile_click(grid_x, grid_y)
            self.selected_action = None
        else:
            # Default to movement
            self.input_manager.handle_action_hotkey("Standard Move")
            self.input_manager.handle_tile_click(grid_x, grid_y)
    
    def _is_click_on_minimap(self, x: float, y: float) -> bool:
        """Check if click is on the minimap"""
        minimap_x = self.layout.MINIMAP_X
        minimap_y = self.layout.MINIMAP_Y
        minimap_size = self.layout.MINIMAP_SIZE
        
        return (minimap_x <= x <= minimap_x + minimap_size and 
                minimap_y <= y <= minimap_y + minimap_size)
    
    def _handle_minimap_click(self, x: float, y: float):
        """Handle clicks on the minimap"""
        # TODO: Implement minimap click handling (center view, etc.)
        pass
    
    def _is_click_on_initiative_bar(self, x: float, y: float) -> bool:
        """Check if click is on the initiative bar"""
        return (self.layout.INITIATIVE_BAR_Y <= y <= 
                self.layout.INITIATIVE_BAR_Y + self.layout.INITIATIVE_BAR_HEIGHT)
    
    def _handle_initiative_bar_click(self, x: float, y: float):
        """Handle clicks on the initiative bar"""
        # TODO: Implement initiative bar scrolling
        pass
    
    def on_key_press(self, key, modifiers):
        """Handle keyboard input"""
        if not self.current_player_id:
            return
            
        if key == arcade.key.A:
            # Attack action
            self.selected_action = "Basic Attack"
            self.input_manager.handle_action_hotkey("Basic Attack")
            
        elif key == arcade.key.M:
            # Movement action
            self.selected_action = "Standard Move"
            self.input_manager.handle_action_hotkey("Standard Move")
            
        elif key == arcade.key.E:
            # End turn
            self.input_manager.handle_end_turn()
            
        elif key == arcade.key.ESCAPE:
            # Cancel current action
            self.input_manager.handle_cancel()
            self.selected_action = None
    
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Handle mouse movement for tooltips and hover effects"""
        # TODO: Implement hover effects and tooltips
        pass
    
    def setup_player_controller(self, player_controller: PlayerTurnController):
        """Set up the player controller integration"""
        self.player_controller = player_controller
        self.game_setup["game_system"].set_player_controller(player_controller)


def create_combat_ui(game_setup: Dict[str, Any], player_ids: List[str]) -> CombatUI:
    """Factory function to create and configure the combat UI"""
    if not ARCADE_AVAILABLE:
        raise ImportError("Arcade library is required for the combat UI. Install with: pip install arcade")
    
    ui = CombatUI(game_setup, player_ids)
    
    # Create and setup player controller
    player_controller = PlayerTurnController(
        game_setup["event_bus"],
        is_player_entity=lambda eid: eid in player_ids
    )
    ui.setup_player_controller(player_controller)
    
    return ui