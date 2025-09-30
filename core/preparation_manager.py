# PreparationManager is responsible for initial setup (entities, terrain, etc.), but does not hardcode any values.
# It uses the GameState class to manage the game state and ECS components.
import importlib
import random
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type, Union

from core.game_state import GameState
from core.pathfinding_optimization import optimize_terrain
from core.terrain_manager import Terrain
from ecs.actions.attack_actions import AttackAction
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.equipment import EquipmentComponent
from ecs.components.facing import FacingComponent
from ecs.components.health import HealthComponent
from ecs.components.inventory import InventoryComponent
from ecs.components.position import PositionComponent
from ecs.components.velocity import VelocityComponent
from ecs.components.willpower import WillpowerComponent
from ecs.systems.action_system import Action, ActionType
from entities.character import Character


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

    # --- Modern arcade demo helpers ---

    def create_grid_terrain(self, width: int, height: int, *, cell_size: int = 64) -> Terrain:
        """Create and attach a :class:`Terrain` instance to the game state.

        Args:
            width: Number of walkable columns.
            height: Number of walkable rows.
            cell_size: Render cell size in pixels. Defaults to ``64``.

        Returns:
            The newly created :class:`Terrain` instance.
        """

        terrain = Terrain(width=width, height=height, cell_size=cell_size, game_state=self.game_state)
        self.game_state.set_terrain(terrain)
        return terrain

    def scatter_walls(
        self,
        *,
        count: Optional[int] = None,
        density: float = 0.1,
        margin: int = 1,
        avoid: Optional[Iterable[Tuple[int, int]]] = None,
        seed: Optional[int] = None,
    ) -> List[Tuple[int, int]]:
        """Add a collection of random blocking walls to the active terrain.

        This replaces the legacy ``create_simple_arena`` / ``create_obstacle_pattern``
        helpers that used to live in ``main.py``.

        Args:
            count: Explicit number of walls to place. When ``None`` a value is
                derived from ``density``.
            density: Ratio of walkable tiles that should become walls when
                ``count`` is omitted.
            margin: How many cells to keep clear from the outer border.
            avoid: Iterable of coordinates that must remain walkable (e.g.,
                spawn points).
            seed: Optional deterministic seed for the RNG.

        Returns:
            List of the coordinates that ended up with walls.
        """

        if not self.game_state.terrain:
            raise RuntimeError("Terrain must be created before scattering walls.")

        terrain = self.game_state.terrain
        rng = random.Random(seed)
        avoid_positions = set(avoid or [])

        candidates: List[Tuple[int, int]] = []
        for x in range(margin, terrain.width - margin):
            for y in range(margin, terrain.height - margin):
                if (x, y) in avoid_positions or (x, y) in terrain.walls:
                    continue
                candidates.append((x, y))

        if not candidates:
            return []

        if count is None:
            if not 0.0 <= density <= 1.0:
                raise ValueError(f"density must be between 0.0 and 1.0 inclusive, got {density}")
            count = int(len(candidates) * density)

        count = min(count, len(candidates))

        rng.shuffle(candidates)
        selected = candidates[:count]

        placed: List[Tuple[int, int]] = []
        for x, y in selected:
            if terrain.add_wall(x, y):
                placed.append((x, y))
        return placed

    def spawn_character(
        self,
        character: Character,
        position: Tuple[int, int],
        *,
        entity_id: Optional[str] = None,
        size: Tuple[int, int] = (1, 1),
        team: Optional[str] = None,
        orientation: str = "up",
        armor: Optional[Any] = None,
        weapons: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create an ECS entity for a ``Character`` and place it on the terrain."""

        if not self.game_state.terrain:
            raise RuntimeError("Terrain must exist before spawning characters.")

        if team is not None:
            set_team = getattr(character, "set_team", None)
            if not callable(set_team):
                raise AttributeError(
                    "Characters spawned through PreparationManager must expose set_team()."
                )
            set_team(team)

        if hasattr(character, "set_orientation"):
            character.set_orientation(orientation)

        inventory = InventoryComponent()
        equipment = EquipmentComponent()
        if armor is not None:
            equipment.armor = armor
        if weapons:
            for slot, weapon in weapons.items():
                if slot in equipment.weapons:
                    equipment.weapons[slot] = weapon

        health = HealthComponent(getattr(character, "max_health", 1))
        willpower = WillpowerComponent(getattr(character, "max_willpower", 1))
        dexterity = self._get_character_trait(character, "Attributes.Physical.Dexterity")
        velocity = VelocityComponent(dexterity)
        position_comp = PositionComponent(
            x=position[0],
            y=position[1],
            width=size[0],
            height=size[1],
        )

        orientation_map = {
            "up": (0.0, 1.0),
            "down": (0.0, -1.0),
            "left": (-1.0, 0.0),
            "right": (1.0, 0.0),
        }
        facing = FacingComponent(direction=orientation_map.get(orientation, (0.0, 1.0)))

        components: Dict[str, Any] = {
            "inventory": inventory,
            "equipment": equipment,
            "health": health,
            "willpower": willpower,
            "character_ref": CharacterRefComponent(character),
            "velocity": velocity,
            "position": position_comp,
            "facing": facing,
        }

        assigned_id = entity_id or f"entity_{len(self.game_state.entities) + 1}"
        terrain = self.game_state.terrain

        placement_issues = self._describe_placement_issues(terrain, position_comp)
        if placement_issues:
            reason_str = ", ".join(placement_issues)
            raise ValueError(
                f"Unable to place entity '{assigned_id}' at {position}: {reason_str}."
            )

        self.game_state.add_entity(assigned_id, components)

        if not terrain.add_entity(assigned_id, position_comp.x, position_comp.y):
            self.game_state.remove_entity(assigned_id)
            raise RuntimeError(
                "Terrain rejected placement after validation; placement logic may be out of sync."
            )

        self.game_state.update_teams()
        return assigned_id

    def _describe_placement_issues(
        self,
        terrain: Any,
        position: PositionComponent,
    ) -> List[str]:
        """Return human-readable reasons an entity cannot occupy ``position`` on ``terrain``."""

        reasons: List[str] = []

        if not terrain.is_valid_position(
            position.x,
            position.y,
            position.width,
            position.height,
        ):
            reasons.append("out of bounds")
            return reasons

        if terrain.is_occupied(
            position.x,
            position.y,
            position.width,
            position.height,
            check_walls=True,
        ):
            reasons.append("position occupied")

        if hasattr(terrain, "is_walkable") and not terrain.is_walkable(
            position.x,
            position.y,
            position.width,
            position.height,
        ):
            reasons.append("blocked by terrain")

        return reasons

    def _get_character_trait(
        self,
        character: Character,
        path: str,
        *,
        default: int = 0,
    ) -> int:
        """Return a nested trait value from ``character`` or ``default`` if unavailable."""

        traits = getattr(character, "traits", None)
        return self._get_nested_trait(traits, path, default=default)

    def _get_nested_trait(
        self,
        traits: Optional[Dict[str, Any]],
        path: str,
        default: int = 0,
    ) -> int:
        """
        Retrieve a nested trait value from a character's trait dictionary using a dot-notation path.

        Traverses a nested dictionary structure to find trait values at specified paths,
        such as 'Attributes.Physical.Strength'.

        Args:
            traits: Dictionary containing nested character traits
            path: Dot-notation string path to the desired trait (e.g., 'Attributes.Physical.Strength')

        Returns:
            The integer value of the trait, or ``default`` if the path is invalid or the trait is not an integer

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
        if not isinstance(traits, dict):
            return default

        keys = path.split('.')
        value: Any = traits
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key, default)
        if isinstance(value, int):
            return value
        return default

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