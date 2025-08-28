"""Input Manager (UI Intent Emitter)
===================================

Purpose
-------
Convert low‑level user inputs (key presses, mouse clicks) captured by the
actual windowing layer (e.g. an Arcade Window) into *semantic* UI intents
broadcast on the EventBus.

This module intentionally avoids any direct reference to rendering code or
simulation state. It is a pure state machine that tracks what phase of input
collection we are in and which action (if any) is being parameterized.

High‑Level Flow
---------------
1. External layer calls handle_action_hotkey("Move") or handle_mouse_tile_click(x,y)
2. InputManager updates its internal InteractionState.
3. When enough parameters collected -> publishes intent event(s):
      ui.select_action / ui.select_target / ui.end_turn / ui.cancel
4. PlayerTurnController reacts and forwards validated actions to the core.

Design Decisions
----------------
* No direct knowledge of entity stats or legality of targets – that belongs
  to higher layers or specialized services.
* Tile coordinates are passed transparently as (x, y) tuples.
* Extensible: add new InteractionMode values for multi‑step actions (e.g.
  area selection) without changing external contract.

Thread Safety
-------------
Single‑threaded expectation; if used in multi‑threaded context wrap public
methods with appropriate synchronization.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

from core.event_bus import EventBus
from interface.event_constants import UIIntents

Tile = Tuple[int, int]


class InteractionMode(Enum):
    IDLE = auto()
    CHOOSING_ACTION = auto()      # (Reserved – hotkeys currently skip this)
    TARGET_SELECTION = auto()


@dataclass
class InteractionState:
    active_entity_id: Optional[str] = None
    mode: InteractionMode = InteractionMode.IDLE
    pending_action: Optional[str] = None
    requires_target: bool = False


class InputManager:
    """Translate raw inputs into high‑level UI intent events.

    External expected usage pattern (pseudo):
        im.set_active_entity(player_eid)
        im.handle_action_hotkey("Move")
        im.handle_tile_click(5, 6, button="left")

    The surrounding window layer decides which physical inputs map to these
    semantic calls – keeping this class framework agnostic.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.state = InteractionState()

    # ------------------------------------------------------------------
    # Turn context
    # ------------------------------------------------------------------
    def set_active_entity(self, entity_id: Optional[str]) -> None:
        """Set (or clear) which entity the player is currently controlling.

        Resets interaction state when switching entity.
        """
        if entity_id != self.state.active_entity_id:
            self.state = InteractionState(active_entity_id=entity_id)

    # ------------------------------------------------------------------
    # High level semantic input handlers (call from window layer)
    # ------------------------------------------------------------------
    def handle_action_hotkey(self, action_name: str, *, requires_target: bool = True) -> None:
        """Begin an action selection via keyboard shortcut or UI button click.

        Args:
            action_name: Name of the action (e.g. "Move", "Attack")
            requires_target: Whether a subsequent target selection is mandatory.
        """
        if not self._has_active_entity():
            return
        if not requires_target:
            # Emit immediate selection (no target step)
            self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=self.state.active_entity_id, action_name=action_name)
            return
        # Move into target selection mode
        self.state.mode = InteractionMode.TARGET_SELECTION
        self.state.pending_action = action_name
        self.state.requires_target = True
        self.event_bus.publish(UIIntents.SELECT_ACTION, entity_id=self.state.active_entity_id, action_name=action_name)

    def handle_tile_click(self, x: int, y: int, *, button: str = "left") -> None:
        """Handle a tile click (grid cell selection) from the window layer.

        Only produces a UI target selection intent if currently in TARGET_SELECTION mode.
        """
        if button != "left":
            return
        if self.state.mode != InteractionMode.TARGET_SELECTION:
            return
        if not self.state.pending_action or not self._has_active_entity():
            return
        target: Tile = (x, y)
        self.event_bus.publish(
            UIIntents.SELECT_TARGET,
            entity_id=self.state.active_entity_id,
            action_name=self.state.pending_action,
            target=target,
        )
        # Reset state after target confirmed
        self._reset_to_idle()

    def handle_end_turn(self) -> None:
        if not self._has_active_entity():
            return
        self.event_bus.publish(UIIntents.END_TURN, entity_id=self.state.active_entity_id)
        self._reset_to_idle()

    def handle_cancel(self) -> None:
        if not self._has_active_entity():
            return
        # Emit cancel intent only if we were mid interaction
        if self.state.mode != InteractionMode.IDLE:
            self.event_bus.publish(UIIntents.CANCEL, entity_id=self.state.active_entity_id)
        self._reset_to_idle()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _reset_to_idle(self) -> None:
        self.state.mode = InteractionMode.IDLE
        self.state.pending_action = None
        self.state.requires_target = False

    def _has_active_entity(self) -> bool:
        return bool(self.state.active_entity_id)
