"""Interactive Four-Way Battle (One Player-Controlled Entity)
=============================================================

Purpose
-------
Minimal console (headless) harness to exercise the PlayerTurnController and
UI intent -> core action flow using the existing four‑way battle scenario.
One entity (first created) is designated as player controlled; the rest use AI.

Goals
-----
* Demonstrate that player input (actions / targets / end turn) drives progress.
* Re-use existing initialization & systems; no game logic duplication.
* Keep dependencies minimal: pure console I/O (no Arcade window required).

Usage
-----
Run directly:

    python -m tests.manual.test_fourway_battle_player --rounds 30

During the player's turn you'll be prompted with available actions. Enter:
  number   -> pick an action
  m x y    -> quick move to tile (shorthand for selecting a move action + target)
  a        -> quick attack (auto-picks first valid adjacent target if any)
  end      -> end turn
  help     -> reprint help
  quit     -> abort the whole simulation

For actions that require a target:
  * Move: you'll be asked for coordinates (x y)
  * Attack: you'll be shown candidate enemy IDs (adjacent only)

Simplifications
---------------
* Target validation kept lightweight (delegated to core on request).
* Reachability preview/pathfinding not printed (future enhancement).
* If an invalid input is given, you re-prompt without consuming the turn.

This file is intentionally in tests/manual so it is excluded from automated CI.
"""
from __future__ import annotations
import argparse
import threading
import time
from typing import List, Dict, Any, Optional

from interface.event_constants import CoreEvents, UIIntents, UIStateEvents
from interface.player_turn_controller import PlayerTurnController
from interface.ui_adapter import UIAdapter
from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.spectator import SpectatorController

# ---------------------------------------------------------------------------
# Scenario setup helpers (mirrors test_fourway_battle)
# ---------------------------------------------------------------------------

def build_four_way_specs(grid_size: int = 15) -> List[EntitySpec]:
    return [
        EntitySpec(team="A", weapon_type="club",   size=(1,1), pos=(2, 2)),
        EntitySpec(team="B", weapon_type="pistol", size=(1,1), pos=(grid_size-3, grid_size-3)),
        EntitySpec(team="C", weapon_type="club",   size=(1,1), pos=(2, grid_size-3)),
        EntitySpec(team="D", weapon_type="pistol", size=(1,1), pos=(grid_size-3, 2)),
    ]


def setup_battle(grid_size: int, max_rounds: int) -> Dict[str, Any]:
    specs = build_four_way_specs(grid_size)
    return initialize_game(entity_specs=specs, grid_size=grid_size, max_rounds=max_rounds, map_dir="battle_maps")

# ---------------------------------------------------------------------------
# Interactive Loop
# ---------------------------------------------------------------------------

class InteractiveController:
    """Console interaction layer bridging PlayerTurnController state to user input."""

    def __init__(self, game_setup: Dict[str, Any], player_entity_id: str):
        self.game_setup = game_setup
        self.player_entity_id = player_entity_id
        self.event_bus = game_setup["event_bus"]
        self.game_state = game_setup["game_state"]
        self.game_system = game_setup["game_system"]
        self.action_system = getattr(self.game_system, "action_system", None)

        # UI adapter to get available actions, state etc.
        self.ui_adapter = UIAdapter(self.event_bus, game_state=self.game_state)
        self.ui_adapter.initialize()
        self.latest_state = self.ui_adapter.latest_state()

        # Hook for updates
        self.event_bus.subscribe(UIStateEvents.STATE_UPDATE, self._on_state_update)

        # Player turn controller
        self.player_turn_controller = PlayerTurnController(
            self.event_bus,
            is_player_entity=lambda eid: eid == self.player_entity_id,
        )

        # Spectator (camera/entity focus logic not strictly needed, but consistent)
        self.spectator = SpectatorController(self.event_bus, entity_order=game_setup["all_ids"])
        if game_setup["all_ids"]:
            self.spectator.select_entity(game_setup["all_ids"][0])

        self._quit_flag = False

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_state_update(self, **_):
        self.latest_state = self.ui_adapter.latest_state()

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------
    def _print_header(self):
        st = self.latest_state
        print("\n=== PLAYER TURN: Entity {} | Round {} Turn {} ===".format(
            st.active_entity_id, st.round_number, st.turn_number))
        print("Health / Actions display is not yet mirrored here (see Arcade UI).")

    def _list_actions(self) -> List[str]:
        actions: List[str] = []
        extras = getattr(self.latest_state, 'extras', None) or {}
        actions = extras.get('available_actions', []) or []
        if not actions and self.action_system:
            # Fallback:
            actions = [a.name for a in self.action_system.available_actions.get(self.player_entity_id, [])]
        return actions

    def _prompt(self):
        actions = self._list_actions()
        if not actions:
            print("No actions available; type 'end' to end turn or 'quit'.")
        else:
            print("Available actions:")
            for idx, name in enumerate(actions, 1):
                print(f"  {idx}. {name}")
            print("  end. End Turn")
        print("Commands: <number>, m x y (move), a (auto attack), end, help, quit")

    def _choose_attack_target(self) -> Optional[str]:
        # Basic adjacent enemy scan (4-neighbors)
        pos = self.game_state.get_component(self.player_entity_id, 'position')
        if not pos:
            print("No position component; cannot attack.")
            return None
        candidates = []
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            cell = (pos.x + dx, pos.y + dy)
            eid = self.game_state.terrain.grid.get(cell)
            if not eid or eid == self.player_entity_id:
                continue
            ent = self.game_state.get_entity(eid)
            if not ent or 'character_ref' not in ent:
                continue
            # Team check
            char = ent['character_ref'].character
            my_ent = self.game_state.get_entity(self.player_entity_id)
            my_team = my_ent['character_ref'].character.team if my_ent and 'character_ref' in my_ent else None
            if char.team != my_team:
                candidates.append(eid)
        if not candidates:
            print("No adjacent enemies.")
            return None
        if len(candidates) == 1:
            return candidates[0]
        print("Choose target:")
        for idx, eid in enumerate(candidates, 1):
            print(f"  {idx}. {eid}")
        while True:
            sel = input("Target #: ").strip()
            if sel.lower() in {"q","quit","x"}:
                return None
            if sel.isdigit():
                idx = int(sel) - 1
                if 0 <= idx < len(candidates):
                    return candidates[idx]
            print("Invalid selection.")

    # ------------------------------------------------------------------
    # Action dispatchers via UI intents
    # ------------------------------------------------------------------
    def send_action(self, action_name: str):
        self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=self.player_entity_id, action_name=action_name)

    def send_targeted_action(self, action_name: str, target: Any):
        # The player_turn_controller expects a SELECT_ACTION first (sets pending)
        self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=self.player_entity_id, action_name=action_name)
        self.event_bus.publish(UIIntents.SELECT_TARGET, entity_id=self.player_entity_id, action_name=action_name, target=target)

    def end_turn(self):
        self.event_bus.publish(UIIntents.END_TURN, entity_id=self.player_entity_id)

    # ------------------------------------------------------------------
    def interactive_turn_loop(self):
        """Blocks while waiting for player turns interleaved with AI progression."""
        help_text_printed = False
        while not self._quit_flag:
            # Check for game end
            if getattr(self.latest_state, 'is_game_over', False):
                print("Game Over. Winner(s):", getattr(self.latest_state, 'winning_teams', None))
                break
            # Only prompt if it's our entity & controller waiting
            if self.player_turn_controller.waiting_for_player_input and self.latest_state.active_entity_id == self.player_entity_id:
                self._print_header()
                self._prompt()
                help_text_printed = True
                raw = input("Command: ").strip()
                if not raw:
                    continue
                parts = raw.split()
                cmd = parts[0].lower()
                if cmd in {"quit","q","exit"}:
                    print("Aborting simulation...")
                    self._quit_flag = True
                    break
                if cmd == "help":
                    help_text_printed = False
                    continue
                if cmd == "end":
                    self.end_turn()
                    continue
                if cmd == "m" and len(parts) == 3:
                    try:
                        x = int(parts[1]); y = int(parts[2])
                        self.send_targeted_action("Standard Move", target=(x,y))
                    except ValueError:
                        print("Invalid coordinates.")
                    continue
                if cmd == "a":
                    tgt = self._choose_attack_target()
                    if tgt:
                        self.send_targeted_action("Basic Attack", target=tgt)
                    continue
                # Numbered action
                if cmd.isdigit():
                    actions = self._list_actions()
                    idx = int(cmd) - 1
                    if 0 <= idx < len(actions):
                        chosen = actions[idx]
                        # Heuristic: movement & attack need target
                        lower = chosen.lower()
                        if lower in {"standard move", "move", "sprint"}:
                            # Prompt for target cell
                            coord = input("Target tile x y: ").strip().split()
                            if len(coord) == 2 and all(c.isdigit() for c in coord):
                                self.send_targeted_action(chosen, target=(int(coord[0]), int(coord[1])))
                            else:
                                print("Invalid tile input.")
                        elif lower in {"basic attack", "attack", "registered attack"}:
                            tgt = self._choose_attack_target()
                            if tgt:
                                self.send_targeted_action(chosen, target=tgt)
                        else:
                            self.send_action(chosen)
                    else:
                        print("Action index out of range.")
                    continue
                print("Unrecognized command. Type 'help' for options.")
            else:
                # Sleep briefly to avoid busy wait; state updates will wake prompt
                if not help_text_printed:
                    print("Waiting for next player turn... (Ctrl+C to abort)")
                    help_text_printed = True
                time.sleep(0.2)

    # ------------------------------------------------------------------
    def start_game_thread(self, max_rounds: int):
        t = threading.Thread(target=self.game_system.run_game_loop, kwargs={'max_rounds': max_rounds}, daemon=True)
        t.start()
        return t

# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Interactive player-controlled four-way battle (console)")
    ap.add_argument('--rounds', type=int, default=30)
    ap.add_argument('--grid', type=int, default=15)
    return ap.parse_args(argv)


def main(argv=None):  # pragma: no cover - manual harness
    args = parse_args(argv)
    game_setup = setup_battle(args.grid, args.rounds)
    all_ids = game_setup['all_ids']
    if not all_ids:
        print("No entities spawned.")
        return
    player_id = all_ids[0]
    print(f"Player controls entity: {player_id}")

    controller = InteractiveController(game_setup, player_id)
    # Start core loop in background
    game_thread = controller.start_game_thread(args.rounds)

    try:
        controller.interactive_turn_loop()
    except KeyboardInterrupt:
        print("\nInterrupted by user; requesting end-turn & shutdown...")
    finally:
        # Attempt graceful end if still running
        if game_thread.is_alive():
            controller.player_turn_controller.abort_turn()
            # Wait a bit so game loop can finish current cycle
            time.sleep(0.5)
        print("Session ended.")


if __name__ == '__main__':  # pragma: no cover
    main()
