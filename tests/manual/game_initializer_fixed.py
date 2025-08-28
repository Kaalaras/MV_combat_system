"""
This module provides a centralized and simplified way to initialize a complete game session,
including the game state, terrain, entities, and all necessary systems. It is designed
to be used by test scripts and other setup routines to avoid repetitive and error-prone
manual initialization.
"""
from typing import List, Dict, Tuple, Any
import os
import datetime
from math import ceil

from entities.default_entities.characters import DefautHuman, Character
from entities.default_entities.armors import Clothes
from entities.default_entities.weapons import Fists, LightPistol, Club
from core.terrain_manager import Terrain
from core.los_manager import LineOfSightManager
from ecs.components.position import PositionComponent
from ecs.components.inventory import InventoryComponent
from ecs.components.equipment import EquipmentComponent
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.health import HealthComponent
from ecs.components.willpower import WillpowerComponent
from ecs.components.velocity import VelocityComponent
from ecs.components.facing import FacingComponent
from core.game_state import GameState
from core.preparation_manager import PreparationManager
from core.game_system import GameSystem
from core.event_bus import EventBus
from core.movement_system import MovementSystem
from ecs.systems.turn_order_system import TurnOrderSystem
from ecs.systems.action_system import ActionSystem
from ecs.systems.facing_system import FacingSystem
from ecs.systems.ai.main import BasicAISystem  # Updated to use refactored AI system
from ecs.actions.movement_actions import StandardMoveAction, SprintAction
from ecs.actions.attack_actions import RegisteredAttackAction
from ecs.actions.aoe_attack_actions import RegisteredAoEAttackAction
from ecs.actions.turn_actions import EndTurnAction
from tests.manual.battle_map_utils import assemble_gif


class EntitySpec:
    """
    A data class for specifying the properties of an entity to be created.
    """
    def __init__(self, team: str, weapon_type: str, size: Tuple[int, int], pos: Tuple[int, int], health_mult: float = 1.0):
        self.team = team
        self.weapon_type = weapon_type
        self.size = size
        self.health_mult = health_mult
        self.pos = pos


def _create_entity_components(character: Character, spec: EntitySpec) -> Dict[str, Any]:
    """
    Internal factory to create the component dictionary for an entity.
    """
    inventory = InventoryComponent()
    equipment = EquipmentComponent()
    equipment.armor = Clothes()

    if spec.weapon_type == "pistol":
        equipment.weapons['ranged'] = LightPistol()
        equipment.weapons['melee'] = Fists()
    elif spec.weapon_type == "club":
        equipment.weapons['melee'] = Club()
        equipment.weapons['ranged'] = None
    else:
        equipment.weapons['melee'] = Fists()
        equipment.weapons['ranged'] = None

    health = HealthComponent(int(character.max_health * spec.health_mult))
    willpower = WillpowerComponent(character.max_willpower)
    char_ref = CharacterRefComponent(character)
    dex = character.traits.get("Attributes", {}).get("Physical", {}).get("Dexterity", 0)
    velocity = VelocityComponent(dex)
    position = PositionComponent(x=spec.pos[0], y=spec.pos[1], width=spec.size[0], height=spec.size[1])

    # Initialize facing component with character's orientation
    facing = FacingComponent()
    # Convert character orientation to direction vector
    orientation_map = {
        'up': (0.0, 1.0),
        'down': (0.0, -1.0),
        'left': (-1.0, 0.0),
        'right': (1.0, 0.0)
    }
    facing.direction = orientation_map.get(character.orientation, (0.0, 1.0))

    return {
        "inventory": inventory,
        "equipment": equipment,
        "health": health,
        "willpower": willpower,
        "character_ref": char_ref,
        "velocity": velocity,
        "position": position,
        "facing": facing
    }


def initialize_game(
    entity_specs: List[EntitySpec],
    grid_size: int,
    max_rounds: int = 200,
    map_dir: str = "battle_maps"
) -> Dict[str, Any]:
    """
    Initializes a complete game instance based on a list of entity specifications.
    """
    game_state = GameState()
    event_bus = EventBus()
    game_state.set_event_bus(event_bus)

    prep_manager = PreparationManager(game_state)
    terrain = Terrain(width=grid_size, height=grid_size, game_state=game_state)
    game_state.set_terrain(terrain)

    # --- Entity Creation ---
    all_ids = []
    for idx, spec in enumerate(entity_specs):
        char = DefautHuman()
        char.set_team(spec.team)
        char.is_ai_controlled = True
        char.ai_script = "basic"
        char.hunger = 0
        entity_id = f"{spec.team}_{idx}"

        components = _create_entity_components(char, spec)

        # Add entity to game state FIRST, so terrain can look up its size.
        game_state.add_entity(entity_id, components)

        # Then, add entity to the terrain grid.
        if terrain.add_entity(entity_id, spec.pos[0], spec.pos[1]):
            all_ids.append(entity_id)
        else:
            print(f"Warning: Could not place entity {entity_id} at {spec.pos}.")
            game_state.remove_entity(entity_id)

    # --- Alliance Setup ---
    for char_id in all_ids:
        char_ref_comp = game_state.get_entity(char_id).get("character_ref")
        if not char_ref_comp: continue
        char = char_ref_comp.character

        for other_id in all_ids:
            if other_id == char_id:
                continue
            other_char_ref_comp = game_state.get_entity(other_id).get("character_ref")
            if not other_char_ref_comp: continue
            other_char = other_char_ref_comp.character

            if char.team == other_char.team:
                char.set_alliance(other_id, "ally")
            else:
                char.set_alliance(other_id, "enemy")
    game_state.update_teams()

    # This is the critical step, moved to *after* entities are placed.
    prep_manager.prepare()

    # --- System Initialization ---
    movement = MovementSystem(game_state)
    game_state.movement = movement
    action_system = ActionSystem(game_state, event_bus)
    game_state.action_system = action_system

    # Create facing system to handle entity orientation updates
    facing_system = FacingSystem(game_state, event_bus)
    game_state.facing_system = facing_system

    # Create LineOfSightManager
    los_manager = LineOfSightManager(game_state, terrain, event_bus)

    ai_system = BasicAISystem(game_state, movement, action_system, debug=True, event_bus=event_bus, los_manager=los_manager)
    turn_order = TurnOrderSystem(game_state)

    # --- Action Registration ---
    prep_manager.action_system = action_system
    prep_manager.initialize_character_actions()

    # Register generic actions available to all
    standard_move = StandardMoveAction(movement)
    sprint_move = SprintAction(movement)
    attack_action = RegisteredAttackAction()
    aoe_attack_action = RegisteredAoEAttackAction()
    end_turn_action = EndTurnAction()
    for entity_id in all_ids:
        action_system.register_action(entity_id, standard_move)
        action_system.register_action(entity_id, sprint_move)
        action_system.register_action(entity_id, attack_action)
        action_system.register_action(entity_id, aoe_attack_action)
        action_system.register_action(entity_id, end_turn_action)

    # --- GameSystem Setup ---
    game_system = GameSystem(game_state, prep_manager, event_bus=event_bus, enable_map_drawing=True)

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        current_dir = os.path.abspath(".")

    # Create a timestamped subfolder for this specific game run
    base_map_dir = os.path.join(current_dir, "..", map_dir)
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    game_id = f"game_{now_str}"
    full_map_dir = os.path.join(base_map_dir, game_id)

    # Create the directories if they don't exist
    if not os.path.exists(base_map_dir):
        os.makedirs(base_map_dir)
    if not os.path.exists(full_map_dir):
        os.makedirs(full_map_dir)

    game_system.set_map_directory(full_map_dir)
    game_system.set_turn_order_system(turn_order)
    game_system.set_action_system(action_system)
    game_system.register_ai_system("basic", ai_system)

    return {
        "game_state": game_state,
        "game_system": game_system,
        "event_bus": event_bus,
        "terrain": terrain,
        "all_ids": all_ids,
        "max_rounds": max_rounds
    }


def run_and_visualize_game(game_setup: Dict[str, Any], gif_name_prefix: str):
    """Run the game loop then assemble a battle GIF (manual visualization helper)."""
    game_system = game_setup["game_system"]
    game_state = game_setup["game_state"]
    max_rounds = game_setup["max_rounds"]
    map_dir = game_system.map_dir

    if os.path.exists(map_dir):
        for f in os.listdir(map_dir):
            if f.endswith('.png'):
                os.remove(os.path.join(map_dir, f))

    game_system.run_game_loop(max_rounds=max_rounds)

    teams = game_state.get_teams()
    alive_teams = []
    for team_id, members in teams.items():
        if any(not game_state.get_entity(eid)["character_ref"].character.is_dead for eid in members):
            alive_teams.append(team_id)
    if len(alive_teams) == 1:
        print(f"Team {alive_teams[0]} wins.")
    elif len(alive_teams) > 1:
        print("Draw: Multiple teams have survivors.")
    else:
        print("No survivors.")

    completed_rounds = sum(1 for f in os.listdir(map_dir) if f.endswith('.png'))
    if completed_rounds > 0:
        gif_name = f"{gif_name_prefix}.gif"
        assemble_gif(map_dir, completed_rounds, gif_name=gif_name, grid_size=game_state.terrain.width, px_size=8, duration=500)
        print(f"Battle GIF saved to {os.path.join(os.path.abspath(map_dir), gif_name)}")
    else:
        print("No rounds completed, GIF not assembled.")
