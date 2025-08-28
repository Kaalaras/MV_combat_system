"""Automated Four-Way Battle With Simulated Player Entity
=======================================================

Self-contained test that injects a PlayerTurnController for the first entity
and simulates UIIntents so the game loop does not stall waiting for input.

Rationale: Avoid importing tests.test_fourway_battle (keeps independence even
if tests directory isn't a package). Reuses the same initialize_game helper.
"""
from __future__ import annotations
import unittest
import random
import threading
from typing import Dict, Any, List, Optional

from interface.player_turn_controller import PlayerTurnController
from interface.event_constants import UIIntents, CoreEvents, UIStateEvents
from interface.ui_adapter import UIAdapter
from interface.spectator import SpectatorController
from tests.manual.game_initializer import initialize_game, EntitySpec
from core.event_bus import EventBus


class PlayerAISimulator:
    """Simulates player input by automatically making decisions for Team A entities."""

    def __init__(self, event_bus: EventBus, team_a_entities: List[str]):
        self.event_bus = event_bus
        self.team_a_entities = set(team_a_entities)
        self.active_entity_id: Optional[str] = None

        # Subscribe to turn start events to know when to act
        event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)

    def _on_turn_start(self, entity_id: str, **kwargs):
        """When a Team A entity's turn starts, simulate player actions."""
        if entity_id in self.team_a_entities:
            self.active_entity_id = entity_id
            # Add a small delay to simulate thinking time
            threading.Timer(0.1, self._simulate_player_actions).start()

    def _simulate_player_actions(self):
        """Simulate player decision making by selecting actions automatically."""
        if not self.active_entity_id:
            return

        # Simple AI: try to attack if possible, otherwise move randomly, then end turn
        entity_id = self.active_entity_id

        # Try attack first
        self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=entity_id, action_name="attack")

        # Add delay before ending turn
        threading.Timer(0.2, lambda: self._end_turn(entity_id)).start()

    def _end_turn(self, entity_id: str):
        """End the turn for the current entity."""
        self.event_bus.publish(UIIntents.END_TURN, entity_id=entity_id)
        self.active_entity_id = None


def build_four_way_specs(grid_size: int = 15) -> List[EntitySpec]:
    """Return the canonical four specs (one per team) placed into map corners."""
    return [
        EntitySpec(team="A", weapon_type="club",   size=(1,1), pos=(2, 2)),
        EntitySpec(team="B", weapon_type="pistol", size=(1,1), pos=(grid_size-3, grid_size-3)),
        EntitySpec(team="C", weapon_type="club",   size=(1,1), pos=(2, grid_size-3)),
        EntitySpec(team="D", weapon_type="pistol", size=(1,1), pos=(grid_size-3, 2)),
    ]


def setup_four_way_battle_with_player(*, grid_size: int = 15, max_rounds: int = 12) -> Dict[str, Any]:
    """Initialize the four-way battle with Team A as player-controlled."""
    specs = build_four_way_specs(grid_size)
    game_setup = initialize_game(entity_specs=specs, grid_size=grid_size, max_rounds=max_rounds, map_dir="battle_maps")

    # Identify Team A entities
    team_a_entities = []
    for entity_id in game_setup["all_ids"]:
        entity = game_setup["game_state"].get_entity(entity_id)
        if entity and hasattr(entity.get("character_ref"), "character"):
            char = entity["character_ref"].character
            if char.team == "A":
                team_a_entities.append(entity_id)

    game_setup["team_a_entities"] = team_a_entities
    return game_setup


def run_visual_four_way_battle_with_player(*, max_rounds: int = 25, grid_size: int = 15,
                                          turn_delay: float = 0.6, action_delay: float = 0.25) -> None:
    """Launch a visual simulation with Team A as player-controlled."""
    try:
        import arcade
        from interface.arcade_app import SpectatorWindow, SimulationThread
        from interface.ui_manager_v2 import UIManagerV2
    except ImportError:
        print("Arcade not available, falling back to headless mode.")
        run_headless_four_way_battle_with_player(max_rounds=max_rounds, grid_size=grid_size, verbose=True, quiet=False)
        return

    game_setup = setup_four_way_battle_with_player(grid_size=grid_size, max_rounds=max_rounds)
    event_bus = game_setup["event_bus"]
    game_state = game_setup["game_state"]
    team_a_entities = game_setup["team_a_entities"]

    ui_adapter = UIAdapter(event_bus, game_state=game_state)
    ui_adapter.initialize()
    ui_manager = UIManagerV2(on_log=lambda msg: print(f"[UI] {msg}"))

    # Set up player controller for Team A entities only
    def is_team_a_entity(entity_id: str) -> bool:
        return entity_id in team_a_entities

    player_controller = PlayerTurnController(event_bus, is_player_entity=is_team_a_entity)

    # Set up AI simulator for Team A (simulates player input)
    player_ai_simulator = PlayerAISimulator(event_bus, team_a_entities)

    # Set up spectator for other entities
    spectator = SpectatorController(event_bus, entity_order=game_setup["all_ids"])

    # Auto-select first Team A entity for camera focus
    if team_a_entities:
        spectator.select_entity(team_a_entities[0])

    sim_thread = SimulationThread(game_setup["game_system"], game_setup["max_rounds"],
                                 event_bus=event_bus, turn_delay=turn_delay, action_delay=action_delay)
    sim_thread.start()

    print("🖼️  Opening visual interface with Team A as player-controlled...")
    print("🎮 Team A entities are user-controlled (simulated automatically)")
    print("🤖 Teams B, C, D remain AI-controlled")
    print("Controls: TAB cycle view | L lock/unlock camera | 0 free camera | ESC quit | Arrows/WASD pan")
    window = SpectatorWindow(game_setup, spectator, ui_adapter, ui_manager)
    arcade.run()


def run_headless_four_way_battle_with_player(*, max_rounds: int = 12, grid_size: int = 15,
                                           verbose: bool = False, seed: Optional[int] = 42,
                                           quiet: bool = True) -> Dict[str, Any]:
    """Run the simulation headlessly with Team A as player-controlled."""
    if seed is not None:
        random.seed(seed)

    game_setup = setup_four_way_battle_with_player(grid_size=grid_size, max_rounds=max_rounds)
    game_state = game_setup["game_state"]
    game_system = game_setup["game_system"]
    event_bus = game_setup["event_bus"]
    all_ids = game_setup["all_ids"]
    team_a_entities = game_setup["team_a_entities"]

    # UI adapter + capture of state updates count
    adapter = UIAdapter(event_bus, game_state=game_state)
    adapter.initialize()
    state_updates = 0
    def _count_updates(**kwargs):
        nonlocal state_updates
        state_updates += 1
    event_bus.subscribe(UIStateEvents.STATE_UPDATE, _count_updates)

    # Set up player controller for Team A entities
    def is_team_a_entity(entity_id: str) -> bool:
        return entity_id in team_a_entities

    player_controller = PlayerTurnController(event_bus, is_player_entity=is_team_a_entity)

    # Set up AI simulator for Team A
    player_ai_simulator = PlayerAISimulator(event_bus, team_a_entities)

    # Set up spectator for non-player entities
    spectator = SpectatorController(event_bus, entity_order=all_ids)

    if verbose:
        print(f"🏁 Teams: {list(game_state.get_teams().keys())}")
        print(f"👥 All Entities: {all_ids}")
        print(f"🎮 Player-controlled (Team A): {team_a_entities}")
        print(f"🤖 AI-controlled (Teams B,C,D): {[eid for eid in all_ids if eid not in team_a_entities]}")
        print(f"⚔️  Running for up to {max_rounds} rounds...")

    import builtins
    original_print = builtins.print
    if quiet and not verbose:
        def _silent_print(*_a, **_k):
            pass
        builtins.print = _silent_print

    try:
        game_system.run_game_loop(max_rounds=max_rounds)

        # Survivor aggregation
        survivors: Dict[str, List[str]] = {}
        for eid in all_ids:
            ent = game_state.get_entity(eid)
            if not ent:
                continue
            char_ref = ent.get("character_ref")
            if not char_ref:
                continue
            char = getattr(char_ref, "character", None)
            if not char or getattr(char, "is_dead", True):
                continue
            team = char.team
            survivors.setdefault(team, []).append(eid)

        final_state = adapter.latest_state()

        return {
            "survivors": survivors,
            "adapter": adapter,
            "spectator": spectator,
            "final_state": final_state,
            "state_updates": state_updates,
            "game_setup": game_setup,
            "player_controller": player_controller,
            "team_a_entities": team_a_entities,
        }
    finally:
        if quiet and not verbose:
            builtins.print = original_print


class TestFourWayBattleWithPlayer(unittest.TestCase):
    """Test the four-way battle with Team A as player-controlled."""

    def test_four_way_battle_with_player_runs(self):
        """Test that the battle runs successfully with player-controlled Team A."""
        max_rounds = 40
        result = run_headless_four_way_battle_with_player(max_rounds=max_rounds, verbose=False, seed=42, quiet=True)

        game_setup = result["game_setup"]
        game_state = game_setup["game_state"]
        all_ids = game_setup["all_ids"]
        team_a_entities = result["team_a_entities"]
        survivors = result["survivors"]
        final_state = result["final_state"]
        state_updates = result["state_updates"]
        player_controller = result["player_controller"]

        # Verify Team A entities are identified correctly
        self.assertTrue(len(team_a_entities) > 0, "Should have at least one Team A entity")

        # Verify player controller is set up correctly
        for entity_id in team_a_entities:
            self.assertTrue(player_controller.is_player_entity(entity_id),
                          f"Entity {entity_id} should be recognized as player entity")

        # Verify non-Team A entities are not player-controlled
        for entity_id in all_ids:
            if entity_id not in team_a_entities:
                self.assertFalse(player_controller.is_player_entity(entity_id),
                               f"Entity {entity_id} should NOT be player-controlled")

        # Basic game state validation
        game_state.update_teams()
        teams = game_state.get_teams()
        self.assertEqual(set(teams.keys()), {"A","B","C","D"}, f"Unexpected teams: {teams}")

        # Game completed successfully
        self.assertGreaterEqual(final_state.round_number, 1, "No rounds recorded.")
        self.assertLessEqual(final_state.round_number, max_rounds)

        # UI state updates occurred
        self.assertGreaterEqual(state_updates, final_state.round_number, "Too few UI state updates.")

        print(f"✅ Test completed - Team A (Player): {team_a_entities}")
        print(f"   Survivors: {survivors}; Final Round: {final_state.round_number}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Four-Way Battle with Player-Controlled Team A")
    parser.add_argument("--rounds", type=int, default=25, help="Maximum rounds to run")
    parser.add_argument("--grid-size", type=int, default=15, help="Grid size for the battle")
    parser.add_argument("--visual", action="store_true", help="Run with visual interface")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.visual:
        run_visual_four_way_battle_with_player(
            max_rounds=args.rounds,
            grid_size=args.grid_size
        )
    else:
        result = run_headless_four_way_battle_with_player(
            max_rounds=args.rounds,
            grid_size=args.grid_size,
            verbose=args.verbose,
            quiet=not args.verbose
        )
        print(f"\n🏆 Final Results:")
        print(f"   Survivors: {result['survivors']}")
        print(f"   Team A (Player) entities: {result['team_a_entities']}")
        print(f"   Total rounds: {result['final_state'].round_number}")
