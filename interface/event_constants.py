"""Central event name constants for UI <-> core communication.
(Added in refactor skeleton phase)
"""
from dataclasses import dataclass
from typing import Tuple, List


@dataclass(frozen=True)
class CoreEvents:
    ROUND_START: str = "round_start"
    ROUND_END: str = "round_end"
    TURN_START: str = "turn_start"
    TURN_END: str = "turn_end"
    ACTION_REQUESTED: str = "action_requested"
    ACTION_PERFORMED: str = "action_performed"
    ACTION_FAILED: str = "action_failed"
    REQUEST_END_TURN: str = "request_end_turn"
    GAME_END: str = "game_end"


@dataclass(frozen=True)
class UIIntents:
    SELECT_ACTION: str = "ui.select_action"
    SELECT_TARGET: str = "ui.select_target"
    END_TURN: str = "ui.end_turn"
    CANCEL: str = "ui.cancel"
    READY_FOR_TURN: str = "ui.ready_for_turn"


@dataclass(frozen=True)
class UIStateEvents:
    STATE_UPDATE: str = "ui.state_update"
    NOTIFICATION: str = "ui.notification"


ALL_EVENTS: Tuple[str, ...] = (
    CoreEvents.ROUND_START, CoreEvents.ROUND_END, CoreEvents.TURN_START, CoreEvents.TURN_END,
    CoreEvents.ACTION_REQUESTED, CoreEvents.ACTION_PERFORMED, CoreEvents.ACTION_FAILED,
    CoreEvents.REQUEST_END_TURN, CoreEvents.GAME_END,
    UIIntents.SELECT_ACTION, UIIntents.SELECT_TARGET, UIIntents.END_TURN, UIIntents.CANCEL,
    UIIntents.READY_FOR_TURN, UIStateEvents.STATE_UPDATE, UIStateEvents.NOTIFICATION,
)

def list_all_events() -> List[str]:
    return list(ALL_EVENTS)


LEGACY_ALIAS_FIELD = "_legacy_alias_of"

