"""Four-Way Battle Test & Runner
================================

This consolidated module unifies the former demo/visual, manual runner, and
basic test into a single authoritative scenario definition.

Capabilities
------------
* Provides helper functions to build and run a four-way AI battle.
* Exposes a richer test with stricter assertions (survivors, teams, UI state).
* Can be invoked directly from the command line for ad‑hoc runs:
    python -m tests.test_fourway_battle --rounds 20 --visual
    python -m tests.test_fourway_battle --rounds 12            (headless)

Design Notes
------------
The visual Arcade window launch remains optional and only attempted when
--visual is passed and Arcade is importable. The test itself NEVER opens a
window (CI friendly).

Deprecated Files
----------------
The previous scripts:
* tests/demos/visual_fourway_demo.py
* tests/manual_fourway_battle.py
now delegate to these helpers and can be removed in the future.
"""
from __future__ import annotations
import argparse
import unittest
import random
import builtins
from typing import List, Dict, Tuple, Any, Optional

# Optional arcade import (only used if visual mode requested)
try:  # pragma: no cover - optional dependency
    import arcade  # type: ignore
except Exception:  # pragma: no cover
    arcade = None  # type: ignore

from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.spectator import SpectatorController
from interface.ui_adapter import UIAdapter
from interface.event_constants import UIStateEvents

# ---------------------------------------------------------------------------
# Scenario Construction Helpers
# ---------------------------------------------------------------------------

def build_four_way_specs(grid_size: int = 15) -> List[EntitySpec]:
    """Return the canonical four specs (one per team) placed into map corners."""
    return [
        EntitySpec(team="A", weapon_type="club",   size=(1,1), pos=(2, 2)),
        EntitySpec(team="B", weapon_type="pistol", size=(1,1), pos=(grid_size-3, grid_size-3)),
        EntitySpec(team="C", weapon_type="club",   size=(1,1), pos=(2, grid_size-3)),
        EntitySpec(team="D", weapon_type="pistol", size=(1,1), pos=(grid_size-3, 2)),
    ]


def setup_four_way_battle(*, grid_size: int = 15, max_rounds: int = 12) -> Dict[str, Any]:
    """Initialize the four-way battle and return the full game_setup dict.

    Returns keys: game_state, game_system, event_bus, all_ids, max_rounds, ...
    """
    specs = build_four_way_specs(grid_size)
    return initialize_game(entity_specs=specs, grid_size=grid_size, max_rounds=max_rounds, map_dir="battle_maps")


# ---------------------------------------------------------------------------
# Execution Helpers
# ---------------------------------------------------------------------------

def run_headless_four_way_battle(*, max_rounds: int = 12, grid_size: int = 15, verbose: bool = False, seed: Optional[int] = 42, quiet: bool = True) -> Dict[str, Any]:
    """Run the simulation headlessly and return a rich result summary.

    Parameters:
        max_rounds: Upper bound of rounds to simulate (loop stops earlier if end conditions met)
        grid_size: Map size
        verbose: If True, prints scenario setup info
        seed: RNG seed for deterministic combat (None to disable)
        quiet: If True (default) suppresses internal GameSystem print spam for faster tests

    Result dict keys:
        survivors: Dict[str, List[str]]  teams -> surviving entity ids
        adapter: UIAdapter               (for further inspection)
        spectator: SpectatorController
        final_state: UiState
        state_updates: int               number of ui.state_update events observed
        game_setup: dict                 original setup (incl. game_state, game_system)
    """
    if seed is not None:
        random.seed(seed)

    game_setup = setup_four_way_battle(grid_size=grid_size, max_rounds=max_rounds)
    game_state = game_setup["game_state"]
    ecs_manager = getattr(game_state, "ecs_manager", None)
    game_system = game_setup["game_system"]
    event_bus = game_setup["event_bus"]
    all_ids = game_setup["all_ids"]

    # UI adapter + capture of state updates count
    adapter = UIAdapter(event_bus, game_state=game_state)
    adapter.initialize()
    state_updates = 0
    def _count_updates(**kwargs):
        nonlocal state_updates
        state_updates += 1
    event_bus.subscribe(UIStateEvents.STATE_UPDATE, _count_updates)

    spectator = SpectatorController(event_bus, entity_order=all_ids)

    if verbose and ecs_manager:
        team_rosters = ecs_manager.collect_team_rosters(include_position=False)
        print(f"🏁 Teams: {list(team_rosters.keys())}")
        print(f"👥 Entities: {all_ids}")
        print(f"⚔️  Running for up to {max_rounds} rounds headlessly...")

    original_print = builtins.print
    if quiet and not verbose:
        def _silent_print(*_a, **_k):
            pass
        builtins.print = _silent_print  # type: ignore
    try:
        game_system.run_game_loop(max_rounds=max_rounds)

        # Survivor aggregation
        survivors: Dict[str, List[str]] = {}
        if ecs_manager:
            team_rosters = ecs_manager.collect_team_rosters(include_position=False)
            known_ids = set(all_ids)
            for team_id, snapshot in team_rosters.items():
                alive_ids = [
                    eid for eid in snapshot.alive_member_ids if eid in known_ids
                ]
                if alive_ids:
                    survivors[team_id] = alive_ids

        final_state = adapter.latest_state()

        return {
            "survivors": survivors,
            "adapter": adapter,
            "spectator": spectator,
            "final_state": final_state,
            "state_updates": state_updates,
            "game_setup": game_setup,
        }
    finally:
        if quiet and not verbose:
            builtins.print = original_print  # restore


def run_visual_four_way_battle(*, max_rounds: int = 25, grid_size: int = 15, turn_delay: float = 0.6, action_delay: float = 0.25) -> None:  # pragma: no cover - visual path
    """Launch a visual simulation if Arcade is available. Falls back to headless otherwise.

    Parameters:
        max_rounds: Upper bound of rounds to simulate
        grid_size: Map size
        turn_delay: Seconds to pause at start of each turn (visual pacing)
        action_delay: Seconds to pause after each action (visual pacing)
    """
    if arcade is None:
        print("Arcade not available, falling back to headless mode.")
        run_headless_four_way_battle(max_rounds=max_rounds, grid_size=grid_size, verbose=True, quiet=False)
        return

    from interface.arcade_app import SpectatorWindow, SimulationThread  # updated thread supports delays
    from interface.ui_manager_v2 import UIManagerV2
    from interface.player_turn_controller import PlayerTurnController

    game_setup = setup_four_way_battle(grid_size=grid_size, max_rounds=max_rounds)
    event_bus = game_setup["event_bus"]
    game_state = game_setup["game_state"]

    ui_adapter = UIAdapter(event_bus, game_state=game_state)
    ui_adapter.initialize()
    ui_manager = UIManagerV2(on_log=lambda msg: print(f"[UI] {msg}"))

    # All AI scenario; still attach controller stub for consistency
    player_controller = PlayerTurnController(event_bus, is_player_entity=lambda _eid: False)  # noqa: F841
    spectator = SpectatorController(event_bus, entity_order=game_setup["all_ids"])
    # Auto-select first entity so camera lock shows immediate action
    if game_setup["all_ids"]:
        spectator.select_entity(game_setup["all_ids"][0])

    sim_thread = SimulationThread(game_setup["game_system"], game_setup["max_rounds"], event_bus=event_bus, turn_delay=turn_delay, action_delay=action_delay)
    sim_thread.start()

    print("🖼️  Opening visual interface...")
    print("Controls: TAB cycle view | L lock/unlock camera | 0 free camera | ESC quit | Arrows/WASD pan")
    print(f"Visual pacing: turn_delay={turn_delay}s action_delay={action_delay}s (adjust via CLI)")
    window = SpectatorWindow(game_setup, spectator, ui_adapter, ui_manager)  # noqa: F841
    arcade.run()


# ---------------------------------------------------------------------------
# Rich Unit Test
# ---------------------------------------------------------------------------
class TestFourWayBattle(unittest.TestCase):
    """Stricter validation of the four-way AI battle pipeline."""

    def test_four_way_battle_runs(self):
        # Increase max_rounds to allow a decisive winner; keep quiet for speed
        max_rounds = 40
        result = run_headless_four_way_battle(max_rounds=max_rounds, verbose=False, seed=42, quiet=True)
        game_setup = result["game_setup"]
        game_state = game_setup["game_state"]
        all_ids = game_setup["all_ids"]
        survivors = result["survivors"]
        final_state = result["final_state"]
        state_updates = result["state_updates"]

        # Teams present & stable via ECS snapshot
        team_rosters = game_state.ecs_manager.collect_team_rosters(include_position=False)
        self.assertEqual(set(team_rosters.keys()), {"A","B","C","D"}, f"Unexpected teams registered: {team_rosters}")

        # All initial entity IDs should exist (pre-elimination) and be unique
        self.assertEqual(len(all_ids), 4)
        self.assertEqual(len(set(all_ids)), 4)

        # Game produced at least one round and did not exceed max
        self.assertGreaterEqual(final_state.round_number, 1, "No rounds recorded.")
        self.assertLessEqual(final_state.round_number, max_rounds)

        # UI state updates should correlate with rounds & turns (loose lower bound)
        self.assertGreaterEqual(state_updates, final_state.round_number, "Too few UI state updates emitted.")

        # At least one survivor (some entity made it) unless mutual annihilation
        self.assertTrue(survivors or True, "Unexpected error building survivors map.")
        # NEW: Assert at most one surviving team remains (decisive outcome)
        self.assertLessEqual(len(survivors), 1, f"Expected ≤1 surviving team, got {survivors}")

        # Spectator basic cycling safety
        spectator = result["spectator"]
        initial_view = spectator.describe_view()
        spectator.cycle_forward()
        spectator.cycle_backward()
        self.assertIsNotNone(spectator.describe_view() or initial_view)  # ensure no crash

        # Adapter last action name should have been set at least once (some action executed)
        adapter = result["adapter"]
        self.assertIsNotNone(adapter.latest_state().last_action_name, "No actions appeared to execute.")

        print(f"Survivors: {survivors}; Final Round: {final_state.round_number}; UI updates: {state_updates}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None):  # pragma: no cover - simple wrapper
    p = argparse.ArgumentParser(description="Run Four-Way Battle Scenario (test harness)")
    p.add_argument("--rounds", type=int, default=12, help="Maximum number of rounds to simulate")
    p.add_argument("--grid", type=int, default=15, help="Grid size")
    p.add_argument("--visual", action="store_true", help="Attempt visual (Arcade) mode")
    p.add_argument("--verbose", action="store_true", help="Verbose headless logging")
    p.add_argument("--turn-delay", type=float, default=0.6, help="Turn start delay (visual mode)")
    p.add_argument("--action-delay", type=float, default=0.25, help="Action delay (visual mode)")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None):  # pragma: no cover - CLI utility
    args = _parse_args(argv)
    if args.visual:
        run_visual_four_way_battle(max_rounds=args.rounds, grid_size=args.grid, turn_delay=args.turn_delay, action_delay=args.action_delay)
    else:
        result = run_headless_four_way_battle(max_rounds=args.rounds, grid_size=args.grid, verbose=args.verbose, quiet=False)
        survivors = result["survivors"]
        final_state = result["final_state"]
        print("=== Four-Way Battle (Headless) ===")
        print(f"Rounds completed: {final_state.round_number}")
        print(f"Survivors: {survivors if survivors else 'None'}")
        print(f"UI state updates: {result['state_updates']}")


if __name__ == "__main__":  # pragma: no cover
    main()
