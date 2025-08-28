"""UI Adapter (Skeleton)
=======================

Purpose
-------
Listens to core simulation events and maintains a lightweight aggregation
of data required by the UI layer, emitting UiState snapshots whenever
something relevant changes.

Design Goals
------------
* Stateless output: each emission is a full snapshot (UiState)
* Minimal coupling: only shallow reads of GameState / ECS
* Replaceable: A future advanced adapter could add caching, diffing, or
  background thread building without changing the public contract.

Usage Flow (Intended)
---------------------
1. Instantiate with references: event_bus, game_state, optional ecs_manager / action_system.
2. Call .initialize() once to subscribe.
3. On each subscribed event the adapter updates internal scratch data and
   publishes ui.state_update(state=<UiState>).
4. UIManager listens for ui.state_update and re-renders.

Extensibility
-------------
Add new event handlers -> update scratch -> rebuild snapshot -> publish.
Keep expensive derivations (e.g., pathfinding overlays) outside this class.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List

from core.event_bus import EventBus
from interface.event_constants import CoreEvents, UIStateEvents
from interface.ui_state import UiState, InitiativeEntry, PendingAction
from utils.condition_utils import IMMOBILIZED  # reuse if needed


class UIAdapter:
    """Aggregates core events into UiState snapshots.

    NOTE: Initiative list logic is placeholder; integrate real TurnOrderSystem later.
    """

    def __init__(self, event_bus: EventBus, *, game_state: Any = None, action_system: Any = None, turn_order_system: Any = None) -> None:
        self.event_bus = event_bus
        self.game_state = game_state
        self.action_system = action_system
        self.turn_order_system = turn_order_system

        # Scratch data
        self._round_number: int = 0
        self._active_entity_id: Optional[str] = None
        self._initiative_order: List[str] = []
        self._actions_remaining: Dict[str, int] = {}
        self._free_move_available: Dict[str, bool] = {}
        self._pending_action: Optional[PendingAction] = None
        self._last_action_name: Optional[str] = None
        self._last_action_result: Optional[str] = None
        self._notifications: List[str] = []

        self._latest_state: UiState = UiState.empty()
        self._initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        if self._initialized:
            return
        eb = self.event_bus
        eb.subscribe(CoreEvents.ROUND_START, self._on_round_start)
        eb.subscribe(CoreEvents.TURN_START, self._on_turn_start)
        eb.subscribe(CoreEvents.TURN_END, self._on_turn_end)
        eb.subscribe(CoreEvents.ACTION_PERFORMED, self._on_action_performed)
        eb.subscribe(CoreEvents.ACTION_FAILED, self._on_action_failed)
        eb.subscribe(CoreEvents.GAME_END, self._on_game_end)
        self._initialized = True

    def latest_state(self) -> UiState:
        return self._latest_state

    # ------------------------------------------------------------------
    # Event Handlers (core)
    # ------------------------------------------------------------------
    def _on_round_start(self, round_number: int, **_: Any) -> None:
        self._round_number = round_number
        self._notify(f"Round {round_number}")
        self._publish()

    def _on_turn_start(self, entity_id: str, **_: Any) -> None:
        self._active_entity_id = entity_id
        # Reset per-turn highlights / pending action
        self._pending_action = None
        # Free move policy placeholder
        self._free_move_available.setdefault(entity_id, True)
        # Derive initiative order (placeholder): if a turn order system exists, query it
        self._rebuild_initiative_order()
        self._publish()

    def _on_turn_end(self, entity_id: str, **_: Any) -> None:
        if entity_id == self._active_entity_id:
            self._active_entity_id = None
        self._publish()

    def _on_action_performed(self, entity_id: str, action_name: str, result: Optional[str] = None, **_: Any) -> None:
        self._last_action_name = action_name
        self._last_action_result = result or "success"
        # Decrement action counters if action_system not providing them automatically
        if entity_id in self._actions_remaining and action_name.lower() != "end turn":
            self._actions_remaining[entity_id] = max(0, self._actions_remaining[entity_id] - 1)
        self._publish()

    def _on_action_failed(self, entity_id: str, action_name: str, reason: Optional[str] = None, **_: Any) -> None:
        self._last_action_name = action_name
        self._last_action_result = reason or "failed"
        if reason:
            self._notify(f"{action_name} failed: {reason}")
        self._publish()

    def _on_game_end(self, **_: Any) -> None:
        self._notify("Game Over")
        self._publish()

    # ------------------------------------------------------------------
    # Snapshot Construction
    # ------------------------------------------------------------------
    def _build_state(self) -> UiState:
        # Build initiative entries – now with vitals
        initiative_entries = []
        for eid in self._initiative_order:
            health_cur = health_max = will_cur = will_max = None
            conditions_tuple = ()
            try:
                ent = self.game_state.get_entity(eid) if self.game_state else None
                if ent and 'character_ref' in ent:
                    char = ent['character_ref'].character
                    if hasattr(char, 'max_health') and hasattr(char, '_health_damage'):
                        health_max = getattr(char, 'max_health')
                        hd = getattr(char, '_health_damage', {})
                        health_cur = max(0, health_max - (hd.get('superficial', 0) + hd.get('aggravated', 0)))
                    if hasattr(char, 'max_willpower') and hasattr(char, '_willpower_damage'):
                        will_max = getattr(char, 'max_willpower')
                        wd = getattr(char, '_willpower_damage', {})
                        will_cur = max(0, will_max - (wd.get('superficial', 0) + wd.get('aggravated', 0)))
            except Exception:
                pass
            try:
                if self.game_state:
                    ent2 = self.game_state.get_entity(eid)
                    if ent2 and 'character_ref' in ent2:
                        char2 = ent2['character_ref'].character
                        if hasattr(char2, 'states'):
                            conditions_tuple = tuple(sorted(char2.states))
            except Exception:
                conditions_tuple = ()
            initiative_entries.append(
                InitiativeEntry(
                    entity_id=eid,
                    is_active=(eid == self._active_entity_id),
                    is_player_controlled=self._is_player(eid),
                    health=health_cur, max_health=health_max,
                    willpower=will_cur, max_willpower=will_max,
                    conditions=conditions_tuple
                )
            )
        active_id = self._active_entity_id
        actions_remaining = self._actions_remaining.get(active_id) if active_id else None
        free_move = self._free_move_available.get(active_id, False) if active_id else False
        primary_remaining = None
        secondary_remaining = None
        available_actions_list: List[str] = []
        reactive_actions_list: List[str] = []
        movement_used = 0
        sprint_max = 0
        if active_id and self.action_system:
            counters = getattr(self.action_system, 'action_counters', {}).get(active_id)
            if counters:
                # Counters keys may be enum; attempt both string and enum access
                primary_remaining = counters.get(getattr(self.action_system, 'ActionType').PRIMARY) if hasattr(self.action_system, 'ActionType') else counters.get('primary')
                secondary_remaining = counters.get(getattr(self.action_system, 'ActionType').SECONDARY) if hasattr(self.action_system, 'ActionType') else counters.get('secondary')
            av = getattr(self.action_system, 'available_actions', {})
            for act in av.get(active_id, []):
                name = getattr(act, 'name', None)
                atype = getattr(act, 'action_type', None)
                if not name:
                    continue
                if atype and str(getattr(atype, 'value', atype)) == 'reaction':
                    reactive_actions_list.append(name)
                else:
                    available_actions_list.append(name)
        if active_id and self.game_state and hasattr(self.game_state, 'get_movement_used'):
            try:
                movement_used = self.game_state.get_movement_used(active_id) or 0
            except Exception:
                movement_used = 0
            try:
                ent = self.game_state.get_entity(active_id)
                if ent and 'character_ref' in ent:
                    char = ent['character_ref'].character
                    if hasattr(char, 'calculate_sprint_distance'):
                        sprint_max = char.calculate_sprint_distance()
            except Exception:
                sprint_max = 0
        # Health/willpower for active already computed separately below for extras
        active_health = None
        active_max_health = None
        active_will = None
        active_max_will = None
        if active_id and self.game_state:
            try:
                ent = self.game_state.get_entity(active_id)
                if ent and 'character_ref' in ent:
                    char = ent['character_ref'].character
                    if hasattr(char, 'max_health') and hasattr(char, '_health_damage'):
                        active_max_health = getattr(char, 'max_health')
                        dmg = getattr(char, '_health_damage', {})
                        active_health = max(0, active_max_health - (dmg.get('superficial', 0) + dmg.get('aggravated', 0)))
                    if hasattr(char, 'max_willpower') and hasattr(char, '_willpower_damage'):
                        active_max_will = getattr(char, 'max_willpower')
                        wdmg = getattr(char, '_willpower_damage', {})
                        active_will = max(0, active_max_will - (wdmg.get('superficial', 0) + wdmg.get('aggravated', 0)))
            except Exception:
                pass
        state = UiState(
            active_entity_id=active_id,
            round_number=self._round_number,
            initiative=tuple(initiative_entries),
            actions_remaining=actions_remaining,
            free_move_available=free_move,
            pending_action=self._pending_action,
            notifications=tuple(self._notifications[-5:]),
            last_action_name=self._last_action_name,
            last_action_result=self._last_action_result,
            is_player_turn=(active_id is not None and self._is_player(active_id)),
            waiting_for_player_input=(active_id is not None and self._is_player(active_id)),
            primary_actions_remaining=primary_remaining,
            secondary_actions_remaining=secondary_remaining,
            extras={
                'available_actions': available_actions_list,
                'reactive_actions': reactive_actions_list,
                'movement_used': movement_used,
                'movement_sprint_max': sprint_max,
                'active_health': active_health,
                'active_max_health': active_max_health,
                'active_willpower': active_will,
                'active_max_willpower': active_max_will,
                'initiative_wrap_index': len(initiative_entries) if initiative_entries else None,
            }
        )
        if active_id and self.game_state:
            try:
                ent_act = self.game_state.get_entity(active_id)
                if ent_act and 'character_ref' in ent_act:
                    char_act = ent_act['character_ref'].character
                    state_extras_conditions = tuple(sorted(getattr(char_act, 'states', [])))
                    state.extras['active_entity_conditions'] = state_extras_conditions
            except Exception:
                pass
        return state

    def _publish(self) -> None:
        self._latest_state = self._build_state()
        self.event_bus.publish(UIStateEvents.STATE_UPDATE, state=self._latest_state)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _rebuild_initiative_order(self) -> None:
        # Use real turn order system if available
        if self.turn_order_system:
            try:
                self._initiative_order = list(self.turn_order_system.get_turn_order())
                return
            except Exception:
                pass
        if not self._initiative_order and self._active_entity_id:
            self._initiative_order = [self._active_entity_id]

    def _notify(self, message: str) -> None:
        self._notifications.append(message)

    def _is_player(self, entity_id: str) -> bool:
        # Minimal heuristic: look up entity and check a 'character_ref.character.is_ai_controlled' flag
        if not self.game_state:
            return False
        ent = self.game_state.get_entity(entity_id)
        if not ent:
            return False
        char_ref = ent.get("character_ref")
        if not char_ref or not hasattr(char_ref, "character"):
            return False
        char = char_ref.character
        return not getattr(char, "is_ai_controlled", True)
