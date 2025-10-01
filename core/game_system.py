from typing import Dict, Optional, Any, List, Tuple
from core.visualization.battle_map import draw_battle_map
import os

from ecs.components.character_ref import CharacterRefComponent
from ecs.components.position import PositionComponent


class GameSystem:
    """
    Main game loop controller that coordinates turn-based gameplay, action resolution,
    AI decision making, and game state management.

    The GameSystem orchestrates the flow of a turn-based game by managing:
    - Turn order and round progression
    - Player and AI action selection and execution
    - Event handling through an event bus
    - Game state visualization (battle map drawing)
    - End condition checking

    Example usage:
    ```python
    # Setup game components
    game_state = GameState()
    prep_manager = PreparationManager()
    event_bus = EventBus()
    ecs_manager = ECSManager()

    # Initialize the game system
    game_system = GameSystem(
        game_state=game_state,
        preparation_manager=prep_manager,
        ecs_manager=ecs_manager,
        event_bus=event_bus,
    )

    # Set up required subsystems
    turn_order_system = TurnOrderSystem(ecs_manager, event_bus)
    action_system = ActionSystem(game_state, event_bus)
    ai_system = BasicAISystem(game_state, event_bus)

    game_system.set_turn_order_system(turn_order_system)
    game_system.set_action_system(action_system)
    game_system.register_ai_system("basic", ai_system)

    # Set map output directory
    game_system.set_map_directory("./battle_maps")

    # Start the game loop with a maximum of 30 rounds
    game_system.run_game_loop(max_rounds=30)
    ```
    """

    def __init__(
            self,
            game_state: Any,
            preparation_manager: Any,
            event_bus: Optional[Any] = None,
            ecs_manager: Optional[Any] = None,
            enable_map_drawing: bool = True
    ) -> None:
        """
        Initialize the GameSystem with game state and required managers.

        Args:
            game_state: The central GameState object containing all entity and world data
            preparation_manager: Manager for game setup and preparation phase
            event_bus: Optional event bus for communication between systems;
                       if None, will attempt to use game_state.event_bus
            ecs_manager: Entity-Component-System manager required for game logic processing.
                Must not be None; a ValueError is raised if this dependency is missing.
            enable_map_drawing: Whether to save battle map visualizations between rounds

        Example:
            ```python
            game_system = GameSystem(
                game_state=game_state,
                preparation_manager=prep_manager,
                ecs_manager=ecs_manager,
                event_bus=event_bus,
                enable_map_drawing=True
            )
            ```
        """
        self.game_state = game_state
        self.preparation_manager = preparation_manager
        if ecs_manager is None:
            raise ValueError("GameSystem requires an ECS manager during initialization.")
        self.ecs_manager = ecs_manager
        self.event_bus = event_bus or getattr(game_state, "event_bus", None)
        self.enable_map_drawing = enable_map_drawing
        self.map_dir: Optional[str] = None  # Will be set later

        self.turn_order_system: Optional[Any] = None
        self.action_system: Optional[Any] = None
        self.ai_systems: Dict[str, Any] = {}

        self._current_turn_entity_id: Optional[str] = None
        self._turn_ended_flag: bool = False

        self.player_controller: Optional[Any] = None  # Optional PlayerTurnController

        if self.event_bus and hasattr(self.game_state, "set_event_bus"):
            self.game_state.set_event_bus(self.event_bus)

        if self.ecs_manager and hasattr(self.game_state, "set_ecs_manager"):
            self.game_state.set_ecs_manager(self.ecs_manager)

        if self.event_bus:
            self.event_bus.subscribe("action_performed", self.handle_action_resolved)
            self.event_bus.subscribe("action_failed", self.handle_action_resolved)
            self.event_bus.subscribe("request_end_turn", self.handle_request_end_turn)

    def set_map_directory(self, map_dir: str) -> None:
        """
        Set the directory where battle maps will be saved.
        Creates the directory if it doesn't exist.

        Args:
            map_dir: Path to the directory where maps will be saved

        Example:
            ```python
            game_system.set_map_directory("./output/battle_maps")
            ```
        """
        self.map_dir = map_dir
        # Create directory if it doesn't exist
        if self.map_dir and not os.path.exists(self.map_dir):
            os.makedirs(self.map_dir)

    def set_turn_order_system(self, turn_order_system: Any) -> None:
        """
        Set the system responsible for determining entity turn order.

        Args:
            turn_order_system: The turn order management system

        Example:
            ```python
            turn_system = TurnOrderSystem(ecs_manager, self.event_bus)
            game_system.set_turn_order_system(turn_system)
            ```
        """
        self.turn_order_system = turn_order_system

    def set_action_system(self, action_system: Any) -> None:
        """
        Set the system responsible for managing and executing entity actions.

        Args:
            action_system: The action management system

        Example:
            ```python
            action_system = ActionSystem(game_state, event_bus)
            game_system.set_action_system(action_system)
            ```
        """
        self.action_system = action_system

    def register_ai_system(self, name: str, ai_system: Any) -> None:
        """
        Register an AI system with the game system to handle AI-controlled entities.

        Args:
            name: Identifier for the AI system type
            ai_system: The AI system instance

        Example:
            ```python
            # Register different AI systems for different behaviors
            basic_ai = BasicAISystem(game_state, event_bus)
            advanced_ai = TacticalAISystem(game_state, event_bus)

            game_system.register_ai_system("basic", basic_ai)
            game_system.register_ai_system("tactical", advanced_ai)
            ```
        """
        self.ai_systems[name] = ai_system

    def handle_action_resolved(self, entity_id: str, action_name: str, **kwargs: Any) -> None:
        """
        Event handler for when an action is completed or fails.
        Specifically identifies "End Turn" actions to mark the turn as ended.

        Args:
            entity_id: The entity that performed or attempted the action
            action_name: The name of the action performed or attempted
            **kwargs: Additional event parameters

        Note:
            This method is typically called by the event bus and not directly.
        """
        if entity_id == self._current_turn_entity_id:
            if action_name == "End Turn":
                self._turn_ended_flag = True

    def handle_request_end_turn(self, entity_id: str) -> None:
        """
        Event handler for explicit requests to end the current turn.

        Args:
            entity_id: The entity requesting to end their turn

        Note:
            This method is typically called by the event bus and not directly.
        """
        if entity_id == self._current_turn_entity_id:
            self._turn_ended_flag = True

    def set_player_controller(self, controller: Any) -> None:
        """Attach a PlayerTurnController (non-blocking UI mediation).

        If set, player-controlled entities will no longer invoke the legacy
        _handle_player_turn() blocking console input; instead the controller
        is given the turn and expected to emit UI intent events that result
        in action_requested / request_end_turn publications.
        """
        self.player_controller = controller

    def _process_player_turn_with_controller(self, entity_id: str, char: Any) -> None:
        """Handle a player-controlled entity's turn via an attached controller.

        Sequence:
          1. begin_player_turn(entity_id)
          2. If controller provides auto_play_turn(), invoke it (headless/scripted tests)
          3. If still not ended, fallback safety publishes request_end_turn to avoid hang
        """
        if not self.player_controller:
            return
        if hasattr(self.player_controller, "begin_player_turn"):
            self.player_controller.begin_player_turn(entity_id)
        # Optional scripted auto play for headless tests
        if hasattr(self.player_controller, "auto_play_turn"):
            try:
                self.player_controller.auto_play_turn(entity_id, self.game_state, self.action_system)
            except Exception as e:  # pragma: no cover - defensive
                print(f"[PlayerController] auto_play_turn error: {e}")
        # Safety: if no end-turn yet, force end to keep loop progressing
        if not self._turn_ended_flag and self.event_bus:
            self.event_bus.publish("request_end_turn", entity_id=entity_id)

    def run_game_loop(self, max_rounds: int = 100) -> None:
        """
        Execute the main game loop for a specified maximum number of rounds.

        This method runs the core turn-based gameplay loop:
        1. Start a new round
        2. Process each entity's turn in order
        3. Allow players/AI to select and perform actions
        4. Check for game end conditions
        5. Render battle map (if enabled)
        6. Repeat until game end or max rounds reached

        Args:
            max_rounds: Maximum number of rounds to execute before ending (default: 100)

        Example:
            ```python
            # Run a quick game with 10 rounds maximum
            game_system.run_game_loop(max_rounds=10)

            # Run a standard game with default 100 rounds maximum
            game_system.run_game_loop()
            ```
        """
        for round_num in range(1, max_rounds + 1):
            print(f"\n=== Round {round_num} ===")
            if self.event_bus:
                self.event_bus.publish("round_start", round_number=round_num)

            self.turn_order_system.start_new_round()
            if self.action_system:
                self.action_system.decrement_cooldowns()

            character_snapshot: Dict[str, Tuple[CharacterRefComponent, Optional[PositionComponent]]] = {
                entity_id: (char_ref, position)
                for entity_id, char_ref, position in self.ecs_manager.iter_character_snapshots()
            }

            for entity_id in self.turn_order_system.get_turn_order():
                self._current_turn_entity_id = entity_id
                self._turn_ended_flag = False

                snapshot = character_snapshot.get(entity_id)
                if not snapshot:
                    raise RuntimeError(
                        "Error during turn processing in the game loop: "
                        f"Turn participant entity_id={entity_id} is missing CharacterRefComponent. "
                        "This may indicate that the entity was not properly initialized, "
                        "was removed from the ECS, or there is a bug in the component management system."
                    )
                char_ref, position_comp = snapshot
                char = char_ref.character
                if char.is_dead:
                    continue

                print(f"\n-- {char.name}'s turn (ID: {entity_id}) --")
                if self.event_bus:
                    self.event_bus.publish("turn_start", entity_id=entity_id)
                if self.action_system:
                    self.action_system.reset_counters(entity_id)
                if self.event_bus:
                    self.event_bus.publish("movement_reset_requested", entity_id=entity_id, position=position_comp)

                # Handle AI-controlled vs player-controlled entities differently
                if char.is_ai_controlled:
                    # Get the appropriate AI system based on the character's AI script
                    ai_name = getattr(char, "ai_script", "basic")
                    ai_system = self.ai_systems.get(ai_name)

                    if ai_system:
                        if self.event_bus:
                            self.event_bus.publish("ai_take_turn", entity_id=entity_id, ai_name=ai_name)
                        else:
                            action_success = ai_system.choose_action(entity_id)
                            if not action_success and self.event_bus:
                                print(f"AI for {char.name} failed to choose a valid action. Ending turn.")
                                self.event_bus.publish("request_end_turn", entity_id=entity_id)
                    else:
                        print(f"AI script '{ai_name}' not found for {char.name}. Ending turn.")
                        if self.event_bus:
                            self.event_bus.publish("request_end_turn", entity_id=entity_id)
                else:
                    if self.player_controller is not None:
                        self._process_player_turn_with_controller(entity_id, char)
                    else:
                        self._handle_player_turn(entity_id, char)

                # Process ECS systems if available
                if self.ecs_manager:
                    self.ecs_manager.process(game_state=self.game_state, event_bus=self.event_bus)

                print(f"{char.name} ends their turn.")
                if self.event_bus:
                    self.event_bus.publish("turn_end", entity_id=entity_id)
                self._current_turn_entity_id = None

            # Draw the battle map if enabled
            if self.enable_map_drawing and self.map_dir:
                teamA_ids = self.game_state.get_teams().get("A", [])
                teamB_ids = self.game_state.get_teams().get("B", [])
                draw_battle_map(
                    self.game_state,
                    self.game_state.terrain,
                    teamA_ids,
                    teamB_ids,
                    round_num=round_num + 1,
                    out_dir=self.map_dir,
                    grid_size=self.game_state.terrain.height,
                    px_size=8
                )

            if self.event_bus:
                self.event_bus.publish("round_end", round_number=round_num)

            if self.check_end_conditions():
                print("Game ended!")
                if self.event_bus:
                    self.event_bus.publish("game_end")
                break

    def _handle_player_turn(self, entity_id: str, char: Any) -> None:
        """
        Handle a turn for a player-controlled entity.

        Args:
            entity_id: The ID of the entity taking its turn
            char: The character object associated with the entity
        """
        while not self._turn_ended_flag:
            if not self.action_system:
                print("ActionSystem not available for player. Ending turn.")
                self._turn_ended_flag = True
                break

            # Get available actions
            available_actions = [
                action for action in self.action_system.available_actions.get(entity_id, [])
                if self.action_system.can_perform_action(entity_id, action)
            ]

            if not available_actions:
                print("No available actions. Ending turn.")
                if self.event_bus:
                    self.event_bus.publish("request_end_turn", entity_id=entity_id)
                break

            # Display available actions
            print("Available actions:")
            for idx, action_obj in enumerate(available_actions):
                print(f"{idx + 1}. {action_obj.name} - {action_obj.description}")
            print(f"{len(available_actions) + 1}. End Turn")

            # Get player choice
            try:
                raw_choice = input(f"{char.name}, choose action: ")
                choice_idx = int(raw_choice) - 1
            except ValueError:
                print("Invalid input. Please enter a number.")
                continue

            # Handle player choice
            if choice_idx == len(available_actions):
                if self.event_bus:
                    self.event_bus.publish("request_end_turn", entity_id=entity_id)
            elif 0 <= choice_idx < len(available_actions):
                selected_action = available_actions[choice_idx]
                action_params = {}

                # Parameter gathering would go here (simplified for this refactoring)
                # In a full implementation, we'd handle various parameter types based on action

                if self.event_bus:
                    self.event_bus.publish(
                        "action_requested",
                        entity_id=entity_id,
                        action_name=selected_action.name,
                        **action_params
                    )
            else:
                print("Invalid choice.")

    def check_end_conditions(self) -> bool:
        """
        Determine if the game has reached an end state by checking if only 0 or 1 teams
        have surviving entities.

        Returns:
            True if game end conditions are met, False otherwise

        Example:
            ```python
            # Inside a custom game loop
            if game_system.check_end_conditions():
                print("Game over!")
                break
            ```
        """
        self.game_state.update_teams()
        teams_data = self.game_state.get_teams()
        if not teams_data or len(teams_data) < 1:
            return False

        active_teams = 0
        for team_name, team_members in teams_data.items():
            if not team_members:
                continue
            team_alive = False
            for entity_id in team_members:
                entity = self.game_state.get_entity(entity_id)
                if not entity or "character_ref" not in entity:
                    continue
                char = entity["character_ref"].character
                if not char.is_dead:
                    team_alive = True
                    break
            if team_alive:
                active_teams += 1

        if active_teams <= 1 and len(teams_data) > 1:
            print(f"End condition met: {active_teams} active team(s) remaining.")
            return True
        return False
