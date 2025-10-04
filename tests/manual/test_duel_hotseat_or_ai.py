"""Interactive Duel: Player vs Player (Hot Seat) or Player vs AI
=================================================================

Overview
--------
This manual harness extends the console-based player input loop introduced in
``tests.manual.test_fourway_battle_player``. It allows you to play a focused
1v1 duel either against another local player (sharing the same keyboard) or
against the built-in basic AI. The mode is chosen when launching the script via
command-line flag or an interactive prompt. A simple ASCII battle map is also
rendered each turn so you can quickly gauge positions without needing to launch
the full Arcade client.

Why it lives in ``tests/manual``
--------------------------------
The file is intended strictly for exploratory / manual testing. It is not
collected by automated test suites, so feel free to tweak values while trying
out mechanics.

Scenario
--------
Two human-sized combatants start on opposite corners of a compact grid. Each
turn, the active combatant can move, attack, or end their turn. Health, position
and available actions are shown directly in the console.

Usage
-----
Run the script directly with ``python -m tests.manual.test_duel_hotseat_or_ai``.
Optional arguments:

``--mode``
    Choose the control scheme: ``vs-ai`` (default), ``hotseat`` or ``prompt``
    (ask on launch).
``--rounds``
    Maximum number of rounds before the match ends (default: 20).
``--grid``
    Size of the square arena (default: 12).
``--map``
    Enable the ASCII battle map (overrides ``--no-map``).
``--no-map``
    Disable the ASCII battle map if you prefer a quieter console.

Example invocations::

    # Play against AI using defaults
    python -m tests.manual.test_duel_hotseat_or_ai

    # Explicitly request hot seat mode on a larger map
    python -m tests.manual.test_duel_hotseat_or_ai --mode hotseat --grid 16

Controls
--------
During your entity's turn, the prompt accepts:

``number``
    Pick an action from the printed list.
``m x y``
    Quick move to the tile at coordinates (x, y).
``a``
    Quick attack – picks the first adjacent hostile target if any.
``end``
    End the current turn.
``status``
    Re-print the roster overview (HP, position, team control).
``help``
    Show the command reference again.
``map``
    Re-print the ASCII battle map on demand.
``quit``
    Abort the session immediately.

Implementation notes
--------------------
* Uses the shared ``initialize_game`` helper from ``tests.manual.game_initializer``.
* Relies on ``PlayerTurnController`` so the game loop pauses when a player
  entity is active.
* Uses ``UIAdapter`` state snapshots to display context and available actions.
* Works entirely in the console – no Arcade window required. The ASCII battle
  map provides lightweight spatial awareness right in the terminal.
"""
from __future__ import annotations

import argparse
import time
import threading
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set

from interface.event_constants import UIIntents, UIStateEvents
from interface.player_turn_controller import PlayerTurnController
from interface.spectator import SpectatorController
from interface.ui_adapter import UIAdapter
from tests.manual.game_initializer import EntitySpec, initialize_game


@dataclass
class EntityLabel:
    entity_id: str
    team: str
    label: str
    is_player_controlled: bool


def build_duel_specs(grid_size: int = 12) -> List[EntitySpec]:
    """Create two opposing combatants placed near opposite corners."""
    return [
        EntitySpec(team="A", weapon_type="club", size=(1, 1), pos=(2, 2)),
        EntitySpec(team="B", weapon_type="pistol", size=(1, 1), pos=(grid_size - 3, grid_size - 3)),
    ]


def setup_duel(grid_size: int, max_rounds: int) -> Dict[str, Any]:
    specs = build_duel_specs(grid_size)
    return initialize_game(entity_specs=specs, grid_size=grid_size, max_rounds=max_rounds, map_dir="battle_maps")


class DuelInteractiveController:
    """Console interaction manager supporting one or two local players."""

    _EMPTY_TILE = " . "
    _WALL_TILE = " # "

    def __init__(
        self,
        game_setup: Dict[str, Any],
        player_entities: Set[str],
        labels: Dict[str, EntityLabel],
        *,
        show_map: bool,
    ):
        self.game_setup = game_setup
        self.player_entities = set(player_entities)
        self.labels = labels
        self.show_map = show_map

        self.event_bus = game_setup["event_bus"]
        self.game_state = game_setup["game_state"]
        self.game_system = game_setup["game_system"]
        self.action_system = getattr(self.game_system, "action_system", None)

        self.ui_adapter = UIAdapter(self.event_bus, game_state=self.game_state)
        self.ui_adapter.initialize()
        self.latest_state = self.ui_adapter.latest_state()
        self.event_bus.subscribe(UIStateEvents.STATE_UPDATE, self._on_state_update)

        self.player_turn_controller = PlayerTurnController(
            self.event_bus,
            is_player_entity=lambda eid: eid in self.player_entities,
            action_requires_target=self._action_requires_target,
        )

        self.spectator = SpectatorController(self.event_bus, entity_order=game_setup["all_ids"])
        if game_setup["all_ids"]:
            self.spectator.select_entity(game_setup["all_ids"][0])

        self._quit_flag = False
        self._status_cache: Optional[str] = None
        self._map_cache: Optional[str] = None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_state_update(self, **_: Any) -> None:
        self.latest_state = self.ui_adapter.latest_state()
        self._status_cache = None
        self._map_cache = None

    # ------------------------------------------------------------------
    # Information helpers
    # ------------------------------------------------------------------
    def _build_status_text(self) -> str:
        if self._status_cache is not None:
            return self._status_cache
        lines = ["Current entities:"]
        for eid, label in self.labels.items():
            pos = self.game_state.get_component(eid, "position")
            health = self.game_state.get_component(eid, "health")
            if not pos or not health:
                continue
            lines.append(
                f"  - {label.label}: HP {health.current_health}/{health.max_health} at ({pos.x}, {pos.y})"
            )
        self._status_cache = "\n".join(lines)
        return self._status_cache

    def _list_actions(self) -> List[str]:
        extras = getattr(self.latest_state, "extras", None) or {}
        actions = extras.get("available_actions", []) or []
        if not actions and self.action_system and self.latest_state.active_entity_id:
            entity_actions = self.action_system.available_actions.get(self.latest_state.active_entity_id, [])
            actions = [action.name for action in entity_actions]
        return actions

    def _prompt_overview(self, entity_id: str) -> None:
        state = self.latest_state
        label = self.labels.get(entity_id)
        intro = label.label if label else entity_id
        print("\n=== Turn: {} | Round {} Turn {} ===".format(intro, state.round_number, state.turn_number))
        print(self._build_status_text())
        if self.show_map:
            print(self._build_ascii_map())
        actions = self._list_actions()
        if not actions:
            print("No actions reported; type 'end' to end your turn or 'help'.")
        else:
            print("Available actions:")
            for idx, action_name in enumerate(actions, 1):
                print(f"  {idx}. {action_name}")
            print("  end. End Turn")
        print("Commands: <number>, m x y, a, end, status, map, help, quit")

    def _screen_row_from_game_y(self, game_y: int, height: int) -> int:
        return height - game_y - 1

    def _format_marker(self, marker: str) -> str:
        return f" {marker} "

    def _build_ascii_map(self) -> str:
        if self._map_cache is not None:
            return self._map_cache

        terrain = getattr(self.game_state, "terrain", None)
        if terrain is None:
            self._map_cache = "[No terrain information available]"
            return self._map_cache

        width = getattr(terrain, "width", 0)
        height = getattr(terrain, "height", 0)
        if width <= 0 or height <= 0:
            self._map_cache = "[Invalid terrain dimensions]"
            return self._map_cache

        rows = [[self._EMPTY_TILE for _ in range(width)] for _ in range(height)]

        for wall_x, wall_y in getattr(terrain, "walls", set()):
            if 0 <= wall_x < width and 0 <= wall_y < height:
                rows[self._screen_row_from_game_y(wall_y, height)][wall_x] = self._WALL_TILE

        for (cell_x, cell_y), entity_id in getattr(terrain, "grid", {}).items():
            if not (0 <= cell_x < width and 0 <= cell_y < height):
                # Bounds check: this guards against possible invalid coordinates in the terrain grid.
                # If the terrain grid is always guaranteed to be valid, this check could be removed.
                continue
            label = self.labels.get(entity_id)
            if label and label.team:
                marker = label.team[0].upper()
            elif label:
                marker = label.label[:1].upper()
            elif entity_id:
                marker = entity_id[:1].upper()
            else:
                marker = "?"
            rows[self._screen_row_from_game_y(cell_y, height)][cell_x] = self._format_marker(marker)

        header = "    " + "".join(f"{x:>3}" for x in range(width))
        lines = [header]
        for row_index, row_cells in enumerate(rows):
            y_coord = height - row_index - 1
            lines.append(f"{y_coord:>3} " + "".join(row_cells))

        lines.append("Legend:")
        for label in self.labels.values():
            if label.team:
                marker = label.team[0].upper()
            else:
                marker = label.label[:1].upper()
            control = "Player" if label.is_player_controlled else "AI"
            marker_display = self._format_marker(marker).strip()
            lines.append(f"  {marker_display} = {label.label} [{control}]")

        self._map_cache = "\n".join(lines)
        return self._map_cache

    # ------------------------------------------------------------------
    # Target helpers
    # ------------------------------------------------------------------
    def _choose_attack_target(self, entity_id: str) -> Optional[str]:
        pos = self.game_state.get_component(entity_id, "position")
        if not pos:
            print("No position component; cannot resolve attack targets.")
            return None
        my_entity = self.game_state.get_entity(entity_id) or {}
        my_team = None
        if "character_ref" in my_entity:
            my_team = my_entity["character_ref"].character.team
        candidates: List[str] = []
        terrain = getattr(self.game_state, "terrain", None)
        if not terrain:
            return None
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            cell = (pos.x + dx, pos.y + dy)
            target_id = terrain.grid.get(cell)
            if not target_id or target_id == entity_id:
                continue
            target_entity = self.game_state.get_entity(target_id) or {}
            if "character_ref" not in target_entity:
                continue
            target_team = target_entity["character_ref"].character.team
            if target_team == my_team:
                continue
            candidates.append(target_id)
        if not candidates:
            print("No adjacent enemies in range.")
            return None
        if len(candidates) == 1:
            return candidates[0]
        print("Choose attack target:")
        for idx, candidate in enumerate(candidates, 1):
            print(f"  {idx}. {candidate}")
        while True:
            choice = input("Target #: ").strip()
            if choice.lower() in {"q", "quit", "x"}:
                return None
            if choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(candidates):
                    return candidates[index]
            print("Invalid selection. Enter a listed number or 'quit'.")

    # ------------------------------------------------------------------
    # Intent dispatchers
    # ------------------------------------------------------------------
    def _send_action(self, entity_id: str, action_name: str) -> None:
        self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=entity_id, action_name=action_name)

    def _action_requires_target(self, action_name: str) -> bool:
        lowered = action_name.lower()
        return lowered in {
            "standard move",
            "move",
            "sprint",
            "jump",
            "basic attack",
            "attack",
            "registered attack",
        }

    def _select_default_weapon(self, entity_id: str) -> Optional[Any]:
        equipment = self.game_state.get_component(entity_id, "equipment")
        if not equipment:
            return None
        weapon = getattr(equipment, "equipped_weapon", None)
        if weapon:
            return weapon
        for slot in ("melee", "ranged", "mental", "social", "special"):
            weapon = equipment.weapons.get(slot)
            if weapon:
                return weapon
        return None

    def _build_target_payload(self, entity_id: str, action_name: str, target: Any) -> Dict[str, Any]:
        lowered = action_name.lower()
        payload: Dict[str, Any] = {"target": target}
        if lowered in {"standard move", "move", "sprint", "jump"}:
            payload["target_tile"] = target
        elif lowered in {"basic attack", "attack", "registered attack"}:
            payload["target_id"] = target
            weapon = self._select_default_weapon(entity_id)
            if weapon:
                payload["weapon"] = weapon
            else:
                print("[Warning] No weapon equipped; attack request may fail.")
        return payload

    def _send_targeted_action(self, entity_id: str, action_name: str, target: Any) -> None:
        self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=entity_id, action_name=action_name)
        payload = self._build_target_payload(entity_id, action_name, target)
        self.event_bus.publish(UIIntents.SELECT_TARGET, entity_id=entity_id, action_name=action_name, **payload)

    def _end_turn(self, entity_id: str) -> None:
        self.event_bus.publish(UIIntents.END_TURN, entity_id=entity_id)

    # ------------------------------------------------------------------
    def interactive_loop(self) -> None:
        printed_waiting = False
        while not self._quit_flag:
            if getattr(self.latest_state, "is_game_over", False):
                winners = getattr(self.latest_state, "winning_teams", None)
                print("Match finished! Winners:", winners)
                break
            active_id = getattr(self.latest_state, "active_entity_id", None)
            if not active_id or active_id not in self.player_entities:
                if not printed_waiting:
                    print("Waiting for your next turn... (Ctrl+C to exit)")
                    printed_waiting = True
                time.sleep(0.2)
                continue
            if not self.player_turn_controller.waiting_for_player_input:
                time.sleep(0.1)
                continue
            printed_waiting = False
            self._prompt_overview(active_id)
            raw = input("Command: ").strip()
            if not raw:
                continue
            parts = raw.split()
            cmd = parts[0].lower()
            if cmd in {"quit", "q", "exit"}:
                print("Ending session...")
                self._quit_flag = True
                break
            if cmd == "help":
                self._status_cache = None
                self._prompt_overview(active_id)
                continue
            if cmd == "status":
                print(self._build_status_text())
                continue
            if cmd == "map":
                if self.show_map:
                    print(self._build_ascii_map())
                else:
                    print("Map display is disabled (launch without --no-map to enable it).")
                continue
            if cmd == "end":
                self._end_turn(active_id)
                continue
            if cmd == "m" and len(parts) == 3:
                try:
                    x = int(parts[1])
                    y = int(parts[2])
                    self._send_targeted_action(active_id, "Standard Move", target=(x, y))
                except ValueError:
                    print("Coordinates must be integers.")
                continue
            if cmd == "a":
                target = self._choose_attack_target(active_id)
                if target:
                    self._send_targeted_action(active_id, "Basic Attack", target=target)
                continue
            if cmd.isdigit():
                actions = self._list_actions()
                index = int(cmd) - 1
                if 0 <= index < len(actions):
                    chosen = actions[index]
                    lowered = chosen.lower()
                    if lowered in {"standard move", "move", "sprint"}:
                        coords = input("Target tile x y: ").strip().split()
                        if len(coords) == 2:
                            try:
                                x = int(coords[0])
                                y = int(coords[1])
                            except ValueError:
                                print("Invalid tile input. Coordinates must be integers.")
                            else:
                                self._send_targeted_action(active_id, chosen, target=(x, y))
                        else:
                            print("Invalid tile input.")
                    elif lowered in {"basic attack", "attack", "registered attack"}:
                        target = self._choose_attack_target(active_id)
                        if target:
                            self._send_targeted_action(active_id, chosen, target=target)
                    else:
                        self._send_action(active_id, chosen)
                else:
                    print("Action index out of range.")
                continue
            print("Unrecognized command. Type 'help' for reference.")

    def start_game_thread(self, max_rounds: int) -> threading.Thread:
        thread = threading.Thread(
            target=self.game_system.run_game_loop,
            kwargs={"max_rounds": max_rounds},
            daemon=True,
        )
        thread.start()
        return thread


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual duel harness supporting hot seat or AI opponents.")
    parser.add_argument("--mode", choices=["vs-ai", "hotseat", "prompt"], default="vs-ai",
                        help="Control mode: vs-ai (default), hotseat (two players) or prompt to ask on start.")
    parser.add_argument("--rounds", type=int, default=20, help="Maximum rounds before auto-termination.")
    parser.add_argument("--grid", type=int, default=12, help="Grid size of the square arena.")
    parser.add_argument("--map", dest="show_map", action="store_true",
                        help="Enable the ASCII battle map (overrides --no-map).")
    parser.add_argument("--no-map", dest="show_map", action="store_false",
                        help="Disable the ASCII battle map output.")
    parser.set_defaults(show_map=True)
    return parser.parse_args(argv)


def _resolve_mode(selected: str) -> str:
    if selected != "prompt":
        return selected
    while True:
        choice = input("Select mode: [vs-ai/hotseat]: ").strip().lower()
        if choice in {"vs-ai", "hotseat"}:
            return choice
        print("Please enter 'vs-ai' or 'hotseat'.")


def _build_labels(game_setup: Dict[str, Any], mode: str) -> Dict[str, EntityLabel]:
    labels: Dict[str, EntityLabel] = {}
    for entity_id in game_setup["all_ids"]:
        entity = game_setup["game_state"].get_entity(entity_id)
        if not entity or "character_ref" not in entity:
            continue
        character = entity["character_ref"].character
        team = character.team
        if team == "A":
            suffix = "Player 1"
            is_player = True
        elif team == "B" and mode == "hotseat":
            suffix = "Player 2"
            is_player = True
        else:
            suffix = "AI"
            is_player = False
        label = f"Team {team} ({suffix})"
        labels[entity_id] = EntityLabel(
            entity_id=entity_id,
            team=team,
            label=label,
            is_player_controlled=is_player,
        )
    return labels


def main(argv: Optional[List[str]] = None) -> None:  # pragma: no cover - manual harness
    args = parse_args(argv)
    mode = _resolve_mode(args.mode)
    game_setup = setup_duel(args.grid, args.rounds)
    if not game_setup["all_ids"]:
        print("No entities initialized; aborting.")
        return

    labels = _build_labels(game_setup, mode)
    player_entities = {eid for eid, label in labels.items() if label.is_player_controlled}
    if not player_entities:
        print("Configuration error: no player-controlled entities detected.")
        return

    print("Loaded entities:")
    for label in labels.values():
        control = "Player" if label.is_player_controlled else "AI"
        print(f"  - {label.entity_id}: {label.label} [{control}]")
    if args.show_map:
        print("ASCII battle map enabled; type 'map' anytime to refresh it.")
    else:
        print("ASCII battle map disabled; launch with --map to enable it.")

    controller = DuelInteractiveController(
        game_setup,
        player_entities,
        labels,
        show_map=args.show_map,
    )
    game_thread = controller.start_game_thread(args.rounds)

    try:
        controller.interactive_loop()
    except KeyboardInterrupt:
        print("\nInterrupted by user; attempting graceful shutdown...")
    finally:
        if game_thread.is_alive():
            controller.player_turn_controller.abort_turn()
            time.sleep(0.5)
        print("Session terminated.")


if __name__ == "__main__":  # pragma: no cover
    main()
