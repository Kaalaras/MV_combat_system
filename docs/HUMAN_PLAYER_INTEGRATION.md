"""Human Player Integration Guide
==============================

This document explains how to integrate human players into the MV Combat System.

## Overview

The combat system now supports human players alongside AI entities through a clean,
event-driven architecture that processes user inputs via the same game engine used
for AI players.

## Key Components

### 1. PlayerTurnController
- **Purpose**: Manages the turn flow for human-controlled entities
- **Location**: `interface/player_turn_controller.py` 
- **Function**: Bridges UI intents to core game actions

### 2. InputManager  
- **Purpose**: Converts raw input events to semantic UI intents
- **Location**: `interface/input_manager.py`
- **Function**: Translates mouse clicks, keyboard input to action/target selection

### 3. UI Event System
- **Events**: SELECT_ACTION, SELECT_TARGET, END_TURN, CANCEL
- **Flow**: Input → UI Intent → PlayerTurnController → Core Action

## Basic Usage

### Setting Up a Human Player

```python
from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.player_turn_controller import PlayerTurnController
from interface.input_manager import InputManager

# 1. Create game with entities
specs = [
    EntitySpec(team="Player", weapon_type="club", pos=(5, 5)),
    EntitySpec(team="AI", weapon_type="pistol", pos=(10, 10))
]
game_setup = initialize_game(entity_specs=specs, grid_size=15)

# 2. Mark entity as player-controlled
player_id = game_setup["all_ids"][0]
char = game_setup["game_state"].get_entity(player_id)["character_ref"].character
char.is_ai_controlled = False

# 3. Create player controller
player_controller = PlayerTurnController(
    game_setup["event_bus"],
    is_player_entity=lambda eid: eid == player_id
)

# 4. Set controller on game system
game_setup["game_system"].set_player_controller(player_controller)

# 5. Create input manager (for UI integration)
input_manager = InputManager(game_setup["event_bus"])
```

### Processing Player Input

```python
# When it's the player's turn:
input_manager.set_active_entity(player_id)

# For movement:
input_manager.handle_action_hotkey("Standard Move")  # Select action
input_manager.handle_tile_click(6, 5)               # Select target tile

# For attack:
input_manager.handle_action_hotkey("Basic Attack")  # Select action  
input_manager.handle_tile_click(target_x, target_y) # Select target

# To end turn:
input_manager.handle_end_turn()
```

## Advanced Usage

### Multiple Human Players

```python
# Mark multiple entities as player-controlled
player_ids = game_setup["all_ids"][:2]  # First 2 entities
for player_id in player_ids:
    char = game_setup["game_state"].get_entity(player_id)["character_ref"].character
    char.is_ai_controlled = False

# Create controller for all players
player_controller = PlayerTurnController(
    game_setup["event_bus"],
    is_player_entity=lambda eid: eid in player_ids
)
```

### Custom Action Requirements

```python
def custom_action_requires_target(action_name: str) -> bool:
    # Define which actions need target selection
    return any(keyword in action_name.lower() 
              for keyword in ["move", "attack", "cast", "throw"])

player_controller = PlayerTurnController(
    game_setup["event_bus"],
    is_player_entity=lambda eid: eid == player_id,
    action_requires_target=custom_action_requires_target
)
```

## Integration with UI Frameworks

### Console Integration
See `tests/manual/test_fourway_battle_player.py` for a complete console-based example.

### Arcade Integration  
```python
import arcade
from interface.input_manager import InputManager

class GameWindow(arcade.Window):
    def __init__(self, game_setup, player_ids):
        super().__init__(800, 600, "Combat Game")
        self.input_manager = InputManager(game_setup["event_bus"])
        # ... setup ...
    
    def on_mouse_press(self, x, y, button, modifiers):
        # Convert screen coords to game coords
        grid_x, grid_y = self.screen_to_grid(x, y)
        
        if self.selected_action:
            # Target selection
            self.input_manager.handle_tile_click(grid_x, grid_y)
        else:
            # Movement
            self.input_manager.handle_action_hotkey("Standard Move")
            self.input_manager.handle_tile_click(grid_x, grid_y)
    
    def on_key_press(self, key, modifiers):
        if key == arcade.key.A:
            self.input_manager.handle_action_hotkey("Basic Attack")
        elif key == arcade.key.E:
            self.input_manager.handle_end_turn()
```

## Event Flow

1. **Turn Start**: Game system calls `player_controller.begin_player_turn(entity_id)`
2. **Action Selection**: UI calls `input_manager.handle_action_hotkey(action_name)`
3. **Target Selection**: UI calls `input_manager.handle_tile_click(x, y)` 
4. **Action Execution**: PlayerTurnController publishes ACTION_REQUESTED event
5. **Turn End**: UI calls `input_manager.handle_end_turn()`

## Action Parameter Mapping

The PlayerTurnController automatically maps UI targets to appropriate action parameters:

- **Movement actions** ("Standard Move", "Sprint"): `target` → `target_tile`
- **Attack actions** ("Basic Attack", "Area Attack"): `target` → `target`
- **Other actions**: `target` → `target`

## Testing

Comprehensive test suite in `tests/test_human_player_input.py`:

```bash
# Run human player integration tests
python -m pytest tests/test_human_player_input.py -v

# Run specific test
python -m pytest tests/test_human_player_input.py::TestHumanPlayerInput::test_single_human_player_basic_actions -v
```

## Error Handling

- **Invalid input**: InputManager ignores invalid actions/targets gracefully
- **No active entity**: Input events are ignored if no player entity is active
- **Action validation**: Core ActionSystem validates all player actions same as AI
- **Turn timeout**: Optional timeout mechanisms can be added at UI level

## Performance Considerations

- **Non-blocking**: Player input doesn't block the game loop
- **Event-driven**: Minimal overhead when no human players present
- **Validation**: Action validation occurs at core level, not UI level
- **State management**: Minimal state kept in PlayerTurnController

## Example Game Configurations

### Single Player vs AI
```python
specs = [
    EntitySpec(team="Player", weapon_type="club", pos=(2, 2)),   # Human
    EntitySpec(team="AI1", weapon_type="pistol", pos=(12, 12)), # AI 
    EntitySpec(team="AI2", weapon_type="club", pos=(12, 2))     # AI
]
```

### Cooperative Players vs AI
```python
specs = [
    EntitySpec(team="Players", weapon_type="club", pos=(2, 2)),   # Human 1
    EntitySpec(team="Players", weapon_type="pistol", pos=(2, 12)), # Human 2  
    EntitySpec(team="Enemy", weapon_type="pistol", pos=(12, 7))   # AI
]
```

### PvP (All Human Players)
```python
specs = [
    EntitySpec(team="Team1", weapon_type="club", pos=(2, 2)),   # Human 1
    EntitySpec(team="Team2", weapon_type="pistol", pos=(12, 12)) # Human 2
]
# Mark all entities as player-controlled
```

This system provides a flexible, testable foundation for human player integration
that scales from single-player scenarios to complex multi-player combat.