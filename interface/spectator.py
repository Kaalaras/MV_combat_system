"""Spectator Controller
=======================

Provides a passive observer that can switch viewpoint between any entity or
no one. Intended for debugging / visualization: prints perspective changes
and can later drive camera focus in a graphical client.

Responsibilities
----------------
* Subscribe to turn_start / action_performed events.
* Maintain a selected entity_id (or None for free camera).
* Offer cycling utility given an ordered list of entity IDs.
* Provide hooks for a rendering layer to query current viewpoint.

Non-Responsibilities
--------------------
* Modifying game state.
* Performing actions or influencing AI.

Usage
-----
    spectator = SpectatorController(event_bus, entity_order=[...])
    # Cycle viewpoint (e.g. from input layer)
    spectator.cycle_forward()
    spectator.clear_view()

Integration Plan
----------------
Arcade window (arcade_app.py) will map key presses (e.g. TAB / SHIFT+TAB / 0)
into the public methods exposed here.
"""
from __future__ import annotations
from typing import List, Optional, Sequence
from core.event_bus import EventBus
from interface.event_constants import CoreEvents


class SpectatorController:
    def __init__(self, event_bus: EventBus, entity_order: Sequence[str] = ()) -> None:
        self.event_bus = event_bus
        self._entity_order: List[str] = list(entity_order)
        self._index: int = -1  # -1 means free camera / none
        self._active_turn_entity: Optional[str] = None

        event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)
        event_bus.subscribe(CoreEvents.ACTION_PERFORMED, self._on_action_performed)
        event_bus.subscribe(CoreEvents.ACTION_FAILED, self._on_action_performed)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    def _on_turn_start(self, entity_id: str, **_):
        self._active_turn_entity = entity_id
        if self.current_view is None:
            # Auto-follow logic could go here; we keep passive for now.
            pass

    def _on_action_performed(self, entity_id: str, action_name: str, **kwargs):
        if entity_id == self.current_view:
            # Minimal perspective feedback; extend as needed.
            print(f"[Spectator POV:{entity_id}] sees action {action_name}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def current_view(self) -> Optional[str]:
        if 0 <= self._index < len(self._entity_order):
            return self._entity_order[self._index]
        return None

    def set_entities(self, entity_ids: Sequence[str]) -> None:
        self._entity_order = list(entity_ids)
        if self._index >= len(self._entity_order):
            self._index = -1

    def cycle_forward(self) -> Optional[str]:
        if not self._entity_order:
            self._index = -1
            return None
        self._index = (self._index + 1) % (len(self._entity_order) + 1)
        # The +1 slot represents free camera (-1)
        if self._index == len(self._entity_order):
            self._index = -1
        return self.current_view

    def cycle_backward(self) -> Optional[str]:
        if not self._entity_order:
            self._index = -1
            return None
        if self._index == -1:
            self._index = len(self._entity_order) - 1
        else:
            self._index -= 1
            if self._index < -1:
                self._index = len(self._entity_order) - 1
        return self.current_view

    def select_entity(self, entity_id: str) -> Optional[str]:
        if entity_id in self._entity_order:
            self._index = self._entity_order.index(entity_id)
        else:
            self._index = -1
        return self.current_view

    def clear_view(self) -> None:
        self._index = -1

    def describe_view(self) -> str:
        return self.current_view or "<free>"
