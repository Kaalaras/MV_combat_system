# PreparationManager is responsible for initial setup (entities, terrain, etc.), but does not hardcode any values.
# It uses the GameState class to manage the game state and ECS components.
from ecs.systems.action_system import Action, ActionType
from ecs.actions.attack_actions import AttackAction
from core.game_state import GameState
import importlib
from core.pathfinding_optimization import optimize_terrain
from typing import Dict, Any, List, Optional, Callable, Union, Type


class PreparationManager:
    """
    Manages the preparation and initialization phase of the game, setting up entities,
    terrain, actions, and optimizations before gameplay begins.

    The PreparationManager is responsible for:
    - Setting up the game environment (terrain, entities)
    - Applying optimizations to pathfinding systems
    - Initializing character actions from configuration files
    - Precalculating character attributes and caches

    Attributes:
        game_state: Reference to the central game state object
        action_system: Reference to the action system for registering character actions

    Example usage:
    ```python
    # Create game state and preparation manager
    game_state = GameState()

    # Create and configure terrain
    terrain = TerrainGrid(100, 100)
    terrain.load_map("forest_battlefield.json")
    game_state.set_terrain(terrain)

    # Initialize preparation manager
    prep_manager = PreparationManager(game_state)

    # Set the action system (needed for initializing character actions)
    action_system = ActionSystem(game_state)
    prep_manager.action_system = action_system

    # Run preparation
    prep_manager.prepare()
    prep_manager.initialize_character_actions()

    # Game is now ready to start
    ```
    """

    def __init__(self, game_state: GameState):
        """
        Initialize the PreparationManager with a reference to the game state.

        Args:
            game_state: The central GameState object containing all entity and world data

        Example:
            ```python
            game_state = GameState()
            prep_manager = PreparationManager(game_state)
            ```
        """
        self.game_state = game_state
        self.action_system = None

    def prepare(self, *args, **kwargs) -> None:
        """
        Prepare the game environment by optimizing terrain and precomputing entity attributes.

        This method:
        1. Applies pathfinding optimizations to the terrain
        2. Precomputes reachable tiles and paths for movement
        3. Calculates and caches attack pool sizes for all entities with equipment

        Args:
            *args: Variable length argument list for future extensibility
            **kwargs: Arbitrary keyword arguments for future extensibility

        Example:
            ```python
            # After setting up game_state with entities and terrain
            prep_manager = PreparationManager(game_state)

            # Apply optimizations and prepare calculations
            prep_manager.prepare()
            ```
        """
        # Setup entities, terrain, etc. using parameters
        # Precompute pathfinding if terrain is set
        if self.game_state.terrain:
            # Apply optimizations to terrain
            self.game_state.terrain = optimize_terrain(self.game_state.terrain)

            # Now run the optimized precomputation
            self.game_state.terrain.precompute_paths()
            self.game_state.terrain.precompute_reachable_tiles(move_distances=(7, 15))
        # Precompute attack/defense pool sizes for all characters and weapons
        if hasattr(self.game_state, 'entities'):
            for entity_id, components in self.game_state.entities.items():
                char = components.get("character_ref").character if components.get("character_ref") else None
                equipment = components.get("equipment")
                if char and equipment:
                    components["attack_pool_cache"] = {}
                    for wtype, weapon in equipment.weapons.items():
                        if weapon is None:  # Skip empty weapon slots
                            continue
                        attr_path, skill_path = weapon.attack_traits
                        attr = self._get_nested_trait(char.traits, attr_path)
                        skill = self._get_nested_trait(char.traits, skill_path)
                        components["attack_pool_cache"][wtype] = attr + skill

    def _get_nested_trait(self, traits: Dict[str, Any], path: str) -> int:
        """
        Retrieve a nested trait value from a character's trait dictionary using a dot-notation path.

        Traverses a nested dictionary structure to find trait values at specified paths,
        such as 'Attributes.Physical.Strength'.

        Args:
            traits: Dictionary containing nested character traits
            path: Dot-notation string path to the desired trait (e.g., 'Attributes.Physical.Strength')

        Returns:
            The integer value of the trait, or 0 if the path is invalid or the trait is not an integer

        Example:
            ```python
            # Character with nested traits
            traits = {
                'Attributes': {
                    'Physical': {
                        'Strength': 5,
                        'Dexterity': 3
                    }
                },
                'Skills': {
                    'Combat': {
                        'Melee': 4
                    }
                }
            }

            # Get specific trait values
            strength = prep_manager._get_nested_trait(traits, 'Attributes.Physical.Strength')  # Returns 5
            melee = prep_manager._get_nested_trait(traits, 'Skills.Combat.Melee')  # Returns 4
            missing = prep_manager._get_nested_trait(traits, 'Skills.Magic.Spellcasting')  # Returns 0
            ```
        """
        keys = path.split('.')
        value = traits
        for key in keys:
            if not isinstance(value, dict):
                return 0
            value = value.get(key, 0)
        if isinstance(value, int):
            return value
        return 0

    def initialize_character_actions(self) -> None:
        """
        Loads and assigns base actions and equipment for each character from their config.

        For each entity with a character component:
        1. Imports the character's configuration module
        2. Sets up base equipment if specified
        3. Registers actions defined in the configuration

        Each action is registered with the action system, with execute functions
        created dynamically based on action requirements.

        Raises:
            ModuleNotFoundError: If a character's config module cannot be found
            Exception: For other errors during action initialization

        Example:
            ```python
            # After creating game state with entities and setting action system
            game_state = GameState()
            action_system = ActionSystem(game_state)

            # Create preparation manager and set action system
            prep_manager = PreparationManager(game_state)
            prep_manager.action_system = action_system

            # Initialize actions for all characters
            prep_manager.initialize_character_actions()

            # Now characters have their actions available
            # Example character config structure in 'entities/default_entities/configs/warrior_config.py':
            # BASE_ACTIONS = [
            #    {
            #        "name": "Basic Attack",
            #        "type": "ATTACK",
            #        "class": RegisteredAttackAction,
            #        "description": "A basic melee attack with equipped weapon",
            #        "params": {"weapon": "melee"}
            #    }
            # ]
            ```
        """
        if not hasattr(self, "action_system") or self.action_system is None:
            print("Warning: No action_system set in preparation_manager")
            return

        for entity_id, components in self.game_state.entities.items():
            if "character_ref" not in components or not components["character_ref"].character:
                continue

            char = components["character_ref"].character
            config_module = f"entities.default_entities.configs.{char.__class__.__name__.lower()}_config"
            try:
                config = importlib.import_module(config_module)

                # Set base equipment
                equipment = components.get("equipment")
                # if equipment and hasattr(config, "BASE_EQUIPMENT"):
                #    equipment.armor = config.BASE_EQUIPMENT.get("armor")
                #    equipment.weapons = config.BASE_EQUIPMENT.get("weapons", {})

                # Register actions
                if hasattr(config, "BASE_ACTIONS"):
                    for action_config in config.BASE_ACTIONS:
                        # Validate action configuration
                        if not isinstance(action_config, dict):
                            print(f"Warning: Invalid action configuration for {entity_id}")
                            continue

                        action_class = action_config.get("class")
                        if action_class is None:
                            print(
                                f"Warning: action_class is None for action '{action_config.get('name', 'UNKNOWN')}' in {config_module}")
                            continue

                        action_params = action_config.get("params", {})
                        action_name = action_config.get("name")
                        action_type = action_config.get("type")

                        if not action_name or not action_type:
                            print(f"Warning: Missing required action parameters for {entity_id}")
                            continue

                        description = action_config.get("description", "")

                        # Create appropriate execute function based on action requirements
                        try:
                            if action_params.get("movement_required", False):
                                def make_movement_execute(cls):
                                    if not cls:
                                        raise ValueError("Invalid action class")
                                    return lambda entity_id, gs, **params: cls(gs.movement)._execute(entity_id, gs,
                                                                                                     **params)

                                execute_func = make_movement_execute(action_class)
                            elif action_class.__name__ == "RegisteredAttackAction":
                                def attack_execute_func(entity_id, gs, **action_params):
                                    attacker_id = entity_id
                                    target_id = action_params.get("target_id")
                                    weapon = action_params.get("weapon")
                                    if not target_id or not weapon:
                                        print("[ActionSystem-Attack] Missing target_id or weapon.")
                                        return False
                                    attack_executor = AttackAction(
                                        attacker_id=attacker_id,
                                        target_id=target_id,
                                        weapon=weapon,
                                        game_state=gs
                                    )
                                    return attack_executor.execute()

                                execute_func = attack_execute_func
                            else:
                                def make_execute(cls):
                                    if not cls:
                                        raise ValueError("Invalid action class")
                                    return lambda entity_id, gs, **params: cls()._execute(entity_id, gs, **params)

                                execute_func = make_execute(action_class)

                            # Create and register the action
                            action = Action(
                                action_name,
                                action_config.get("type"),
                                execute_func,
                                description=description
                            )
                            self.action_system.register_action(entity_id, action)
                            # print(f"Registered action '{action_name}' for {entity_id}")

                        except Exception as e:
                            print(f"Error creating execute function for action '{action_name}': {e}")
                            continue

            except ModuleNotFoundError:
                print(f"Config for {char.__class__.__name__} not found.")
            except Exception as e:
                import traceback
                print(f"Error initializing actions for {char.__class__.__name__}: {e}")
                print(traceback.format_exc())