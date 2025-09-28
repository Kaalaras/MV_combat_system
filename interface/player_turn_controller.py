"""Player Turn Controller (Skeleton)
===================================

Purpose
-------
Bridges core game turn events and UI intents for player‑controlled entities.
It:
  * Listens to core 'turn_start' events
  * Detects whether the active entity is player controlled (delegated strategy)
  * If player entity: enters a waiting state instead of blocking the main loop
  * Consumes UI intent events (ui.select_action / ui.select_target / ui.end_turn)
  * Validates basic preconditions then forwards to the core as action_requested
  * Publishes request_end_turn when the player ends the turn

Out of Scope (for now)
----------------------
  * Complex validation (range checks, resource costs) – belongs in ActionSystem
  * Building target lists – a future ActionMetadataService can provide those
  * Defense reactions – add later as a parallel small state machine

Free Movement Concept (Planned)
-------------------------------
We keep a per-turn flag `free_move_available` that can be toggled by external
logic (e.g. reset on turn_start). When a movement intent arrives and the player
has no remaining actions, we can mark it as a 'free move' via metadata param.
Implementation placeholder included.

Extension Points
----------------
Inject alternative policies by providing small strategy callables:
  * is_player_entity(entity_id: str) -> bool
  * action_requires_target(action_name: str) -> bool (optional override)

Threading / Async
-----------------
Currently synchronous – if an async UI is introduced later, intents still
arrive through the event bus.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

from core.event_bus import EventBus
from interface.event_constants import CoreEvents, UIIntents


@dataclass
class PendingActionData:
    entity_id: str
    action_name: str
    requires_target: bool = False
    metadata: Dict[str, Any] = None


class PlayerTurnController:
    """Stateful mediator handling a single local player's turn flow.

    Public Lifecycle Methods
    ------------------------
    * begin_player_turn(entity_id): Called when core turn_start indicates a player entity.
    * abort_turn(): Force exit (e.g. entity died mid-turn) – publishes end turn request.

    Event Handlers (auto subscribed)
    --------------------------------
    * _on_turn_start
    * _on_action_performed / _on_action_failed
    * _on_ui_select_action / _on_ui_select_target / _on_ui_end_turn / _on_ui_cancel
    """

    def __init__(
        self,
        event_bus: EventBus,
        *,
        is_player_entity: Callable[[str], bool],
        action_requires_target: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.event_bus = event_bus
        self.is_player_entity = is_player_entity
        self.action_requires_target = action_requires_target or (lambda name: any(keyword in name.lower() for keyword in {"move", "attack", "sprint"}))

        # Turn / interaction state
        self.active_entity_id: Optional[str] = None
        self.waiting_for_player_input: bool = False
        self.pending_action: Optional[PendingActionData] = None
        self.free_move_available: bool = False  # Reset per turn (placeholder)

        # Subscribe to core events
        event_bus.subscribe(CoreEvents.TURN_START, self._on_turn_start)
        event_bus.subscribe(CoreEvents.ACTION_PERFORMED, self._on_action_resolved)
        event_bus.subscribe(CoreEvents.ACTION_FAILED, self._on_action_resolved)
        event_bus.subscribe(CoreEvents.TURN_END, self._on_turn_end)

        # Subscribe to UI intent events
        event_bus.subscribe(UIIntents.SELECT_ACTION, self._on_ui_select_action)
        event_bus.subscribe(UIIntents.SELECT_TARGET, self._on_ui_select_target)
        event_bus.subscribe(UIIntents.END_TURN, self._on_ui_end_turn)
        event_bus.subscribe(UIIntents.CANCEL, self._on_ui_cancel)

    # ------------------------------------------------------------------
    # Core event handlers
    # ------------------------------------------------------------------
    def _on_turn_start(self, entity_id: str, **_: Any) -> None:  # noqa: D401
        """Handle the start of any entity's turn.

        If it's a player entity we enter interactive mode; otherwise remain passive.
        """
        if not self.is_player_entity(entity_id):
            return
        self.begin_player_turn(entity_id)

    def _on_turn_end(self, entity_id: str, **_: Any) -> None:
        if entity_id == self.active_entity_id:
            # Clean up state
            self.active_entity_id = None
            self.waiting_for_player_input = False
            self.pending_action = None

    def _on_action_resolved(self, entity_id: str, action_name: str, **kwargs: Any) -> None:
        """Observe action outcomes – could update free move consumption, etc."""
        if entity_id != self.active_entity_id:
            return
        # Example placeholder: if it's a movement and flagged free move, consume it
        if action_name.lower() == "move" and kwargs.get("free_move", False):
            self.free_move_available = False
        # If the action ended the turn implicitly (rare) we could detect here

    # ------------------------------------------------------------------
    # UI intent handlers
    # ------------------------------------------------------------------
    def _on_ui_select_action(self, entity_id: str, action_name: str, **_: Any) -> None:
        if not self._validate_intent_entity(entity_id):
            return
        requires_target = self.action_requires_target(action_name)
        if requires_target:
            # Defer until target chosen
            self.pending_action = PendingActionData(entity_id, action_name, True, metadata={})
        else:
            # Directly forward to core
            self._publish_action_request(entity_id, action_name)

    def _on_ui_select_target(self, entity_id: str, action_name: str, target: Any, **extra: Any) -> None:
        if not self._validate_intent_entity(entity_id):
            return
        # Basic guard: ensure it matches pending action (if any)
        if self.pending_action and self.pending_action.action_name != action_name:
            # Ignore mismatched target selection
            return
        metadata = dict(extra)
        # Example: attach free_move flag – decision placeholder
        if action_name.lower() == "move" and self.free_move_available:
            metadata["free_move"] = True
            self.free_move_available = False
        
        # Map target to appropriate parameter name based on action type
        action_params = metadata.copy()
        if action_name.lower() in ["standard move", "move", "sprint"]:
            action_params["target_tile"] = target
        elif action_name.lower() in ["attack", "basic attack"]:
            action_params["target"] = target
        else:
            action_params["target"] = target
            
        self._publish_action_request(entity_id, action_name, **action_params)
        self.pending_action = None

    def _on_ui_end_turn(self, entity_id: str, **_: Any) -> None:
        if not self._validate_intent_entity(entity_id):
            return
        self._request_end_turn(entity_id)

    def _on_ui_cancel(self, entity_id: str, **_: Any) -> None:
        if not self._validate_intent_entity(entity_id):
            return
        # Simple cancel only clears pending action – not the whole turn
        self.pending_action = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def begin_player_turn(self, entity_id: str) -> None:
        self.active_entity_id = entity_id
        self.waiting_for_player_input = True
        self.pending_action = None
        self.free_move_available = True  # Reset policy placeholder

    def abort_turn(self) -> None:
        if self.active_entity_id:
            self._request_end_turn(self.active_entity_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _publish_action_request(self, entity_id: str, action_name: str, **params: Any) -> None:
        self.event_bus.publish(
            CoreEvents.ACTION_REQUESTED,
            entity_id=entity_id,
            action_name=action_name,
            **params,
        )

    def _request_end_turn(self, entity_id: str) -> None:
        self.event_bus.publish(CoreEvents.REQUEST_END_TURN, entity_id=entity_id)
        self.waiting_for_player_input = False

    def _validate_intent_entity(self, entity_id: str) -> bool:
        return bool(self.waiting_for_player_input and entity_id == self.active_entity_id)
