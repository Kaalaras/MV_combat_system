"""PlayerTurnController Integration Test
=====================================

Scenario:
  * 4 entities on distinct teams (A,B,C,D) placed apart
  * First entity (A_0) converted to player-controlled (is_ai_controlled=False)
  * Attach a PlayerTurnController with an auto_play_turn() helper so the
    headless test doesn't block and performs a deterministic simple move then end turn.

Assertions:
  * PlayerTurnController receives the turn (flag set)
  * A Standard Move action (if possible) is requested & performed (entity position changes)
    OR if movement impossible, test still passes as long as End Turn occurs
  * Turn ends cleanly without hanging the loop

We keep max_rounds small (3) for speed.
"""
from __future__ import annotations
import unittest

from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.player_turn_controller import PlayerTurnController
from core.event_bus import EventBus


class AutoPlayerControllerHelper(PlayerTurnController):
    def __init__(self, event_bus: EventBus, player_eid: str):
        super().__init__(event_bus, is_player_entity=lambda eid: eid == player_eid)
        self.player_eid = player_eid
        self.turns_handled = 0
        self.move_attempted = False
        self.ended = False

    def auto_play_turn(self, entity_id: str, game_state, action_system):  # called by GameSystem helper
        if entity_id != self.player_eid:
            return
        self.turns_handled += 1
        # Determine a simple adjacent target tile (try right, down, left, up)
        pos_comp = game_state.get_component(entity_id, "position")
        if pos_comp:
            start_x, start_y = pos_comp.x, pos_comp.y
        else:
            start_x = start_y = 0
        candidate_offsets = [(1,0), (0,1), (-1,0), (0,-1)]
        target_tile = None
        for dx, dy in candidate_offsets:
            tx, ty = start_x + dx, start_y + dy
            if 0 <= tx < game_state.terrain.width and 0 <= ty < game_state.terrain.height:
                if not game_state.is_tile_occupied(tx, ty):
                    target_tile = (tx, ty)
                    break
        if target_tile:
            self.move_attempted = True
            # Publish Standard Move request (name must match action registration)
            self.event_bus.publish(
                "action_requested",
                entity_id=entity_id,
                action_name="Standard Move",
                target_tile=target_tile,
            )
        # Always end turn afterward (whether move succeeded or not) via explicit End Turn action
        self.event_bus.publish(
            "action_requested",
            entity_id=entity_id,
            action_name="End Turn",
        )
        self.ended = True


def test_player_turn_controller_single_player():
    specs = [
        EntitySpec(team="A", weapon_type="club", size=(1,1), pos=(2,2)),
        EntitySpec(team="B", weapon_type="club", size=(1,1), pos=(6,6)),
        EntitySpec(team="C", weapon_type="club", size=(1,1), pos=(10,10)),
        EntitySpec(team="D", weapon_type="club", size=(1,1), pos=(14,14)),
    ]
    game_setup = initialize_game(entity_specs=specs, grid_size=20, max_rounds=3, map_dir="battle_maps")
    game_state = game_setup["game_state"]
    game_system = game_setup["game_system"]
    event_bus = game_setup["event_bus"]
    player_id = game_setup["all_ids"][0]  # Make first entity the player

    # Convert to player-controlled
    char = game_state.get_entity(player_id)["character_ref"].character
    char.is_ai_controlled = False

    controller = AutoPlayerControllerHelper(event_bus, player_eid=player_id)
    game_system.set_player_controller(controller)

    # Track initial position
    pos_before = (game_state.get_component(player_id, "position").x, game_state.get_component(player_id, "position").y)

    # Run a short loop
    game_system.run_game_loop(max_rounds=3)

    pos_after = (game_state.get_component(player_id, "position").x, game_state.get_component(player_id, "position").y)

    assert controller.turns_handled >= 1, "Controller did not handle any turns"
    assert controller.ended, "Controller did not end the turn via End Turn action"
    # If move attempted, expect a position change
    if controller.move_attempted:
        assert pos_after != pos_before, "Expected movement but position unchanged"
