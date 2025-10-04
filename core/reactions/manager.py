"""Reaction window orchestration."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol

from core.actions.catalog import ACTION_CATALOG, ActionDef
from core.actions.intent import ActionIntent, TargetSpec
from core.events import topics


class EventBusLike(Protocol):
    def subscribe(self, topic: str, handler: Callable[..., None]) -> None:
        ...

    def publish(self, topic: str, /, **payload: Any) -> None:
        ...


@dataclass
class ReactionOption:
    action_id: str
    name: str
    speed: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "id": self.action_id,
            "name": self.name,
            "reaction_speed": self.speed,
            "payload": dict(self.payload),
        }


@dataclass
class PendingWindow:
    window_id: str
    defender_id: str
    action_payload: Dict[str, Any]
    options: List[ReactionOption]
    resolved: bool = False
    selection: Optional[Mapping[str, Any]] = None


@dataclass
class PendingAction:
    action_id: str
    action_payload: Dict[str, Any]
    windows: Dict[str, PendingWindow]

    def all_resolved(self) -> bool:
        return all(window.resolved for window in self.windows.values())


class ReactionManager:
    """Manage reaction windows and resume action execution once done."""

    def __init__(self, rules_ctx: Any) -> None:
        self._rules = rules_ctx
        self._bus: EventBusLike | None = None
        self._pending_actions: Dict[str, PendingAction] = {}
        self._counter = itertools.count(1)

    def bind(self, bus: EventBusLike) -> None:
        self._bus = bus
        bus.subscribe(topics.PERFORM_ACTION, self._handle_perform_action)
        bus.subscribe(topics.REACTION_DECLARED, self._handle_reaction_declared)

    # ------------------------------------------------------------------
    def _handle_perform_action(self, *, await_reactions: bool | None = None, intent: Any, intent_obj: Any | None = None, **payload: Any) -> None:
        if not await_reactions:
            return
        if self._bus is None:
            return

        normalised = _ensure_intent(intent_obj, intent)
        action_def = ACTION_CATALOG.get(normalised.action_id)
        if action_def is None:
            return

        action_payload = dict(payload)
        action_payload.update({
            "intent": normalised.to_dict(),
            "intent_obj": normalised,
            "action_id": normalised.action_id,
            "actor_id": normalised.actor_id,
        })
        action_id = action_payload.get("reservation_id") or normalised.client_tx_id or f"{normalised.actor_id}:{normalised.action_id}:{next(self._counter)}"

        defenders = _collect_defenders(normalised.targets)
        if not defenders:
            self._resume_action(action_id, action_payload, reactions=[])
            return

        options = list(self._gather_reaction_options(action_def, normalised))
        if not options:
            self._resume_action(action_id, action_payload, reactions=[])
            return

        windows: Dict[str, PendingWindow] = {}
        for defender_id in defenders:
            window_id = f"{action_id}:{defender_id}"
            window = PendingWindow(
                window_id=window_id,
                defender_id=defender_id,
                action_payload=action_payload,
                options=list(options),
            )
            windows[window_id] = window
            self._publish_window(window, normalised, action_def)

        self._pending_actions[action_id] = PendingAction(
            action_id=action_id,
            action_payload=action_payload,
            windows=windows,
        )

    def _handle_reaction_declared(self, *, actor_id: str, reaction: Any = None, passed: bool = False, window_id: Optional[str] = None, **_: Any) -> None:
        if self._bus is None:
            return

        pending, window = self._locate_window(actor_id, window_id)
        if pending is None or window is None:
            return

        if window.defender_id != actor_id:
            # Ignore attempts to resolve a window by an unrelated actor.
            return

        window.resolved = True
        if not passed and reaction:
            window.selection = reaction

        if not pending.all_resolved():
            return

        reactions = []
        for wnd in pending.windows.values():
            if wnd.selection:
                reactions.append(dict(wnd.selection))

        self._finalise_reactions(pending, reactions)

    # ------------------------------------------------------------------
    def _publish_window(self, window: PendingWindow, intent: ActionIntent, action_def: ActionDef) -> None:
        if self._bus is None:
            return

        context = {
            "attacker": intent.actor_id,
            "defender": window.defender_id,
            "action_id": intent.action_id,
            "action_name": action_def.name,
        }
        options_payload = [option.to_payload() for option in window.options]
        self._bus.publish(
            topics.REACTION_WINDOW_OPENED,
            actor_id=window.defender_id,
            options=options_payload,
            window_id=window.window_id,
            context=context,
        )

    def _locate_window(self, actor_id: str, window_id: Optional[str]) -> tuple[Optional[PendingAction], Optional[PendingWindow]]:
        if window_id:
            action_id = window_id.rsplit(":", 1)[0]
            pending = self._pending_actions.get(action_id)
            if not pending:
                return None, None
            window = pending.windows.get(window_id)
            if window and window.defender_id != actor_id:
                return None, None
            return pending, window

        for action_id, pending in self._pending_actions.items():
            for window in pending.windows.values():
                if window.defender_id == actor_id and not window.resolved:
                    return pending, window
        return None, None

    def _finalise_reactions(self, pending: PendingAction, reactions: List[Mapping[str, Any]]) -> None:
        if self._bus is None:
            return

        sorted_reactions = sorted(
            reactions,
            key=lambda entry: _reaction_priority(entry.get("reaction_speed")),
        )

        self._bus.publish(
            topics.REACTION_RESOLVED,
            action_id=pending.action_payload.get("action_id"),
            actor_id=pending.action_payload.get("actor_id"),
            reactions=sorted_reactions,
            context=pending.action_payload.get("intent"),
        )

        self._resume_action(pending.action_id, pending.action_payload, sorted_reactions)

    def _resume_action(self, action_id: str, payload: Dict[str, Any], reactions: List[Mapping[str, Any]]) -> None:
        if self._bus is None:
            return

        payload = dict(payload)
        payload.update({
            "await_reactions": False,
            "reactions_resolved": True,
            "reaction_results": reactions,
        })
        self._bus.publish(topics.PERFORM_ACTION, **payload)
        self._pending_actions.pop(action_id, None)

    def _gather_reaction_options(self, action_def: ActionDef, intent: ActionIntent) -> Iterable[ReactionOption]:
        provider = getattr(self._rules, "iter_reaction_options", None)
        if callable(provider):
            yield from (
                ReactionOption(
                    action_id=str(option.get("id")),
                    name=str(option.get("name", option.get("id", "reaction"))),
                    speed=str(option.get("reaction_speed", "normal")),
                    payload=option,
                )
                for option in provider(action_def, intent)
                if isinstance(option, Mapping)
            )
            return

        for definition in ACTION_CATALOG.values():
            tags = {tag.lower() for tag in definition.tags}
            if "reaction" not in tags:
                continue
            yield ReactionOption(
                action_id=definition.id,
                name=definition.name,
                speed=definition.reaction_speed or "normal",
                payload={"action_id": definition.id},
            )


def _ensure_intent(intent_obj: Any | None, payload: Any) -> ActionIntent:
    if isinstance(intent_obj, ActionIntent):
        return intent_obj
    if isinstance(payload, ActionIntent):
        return payload
    if isinstance(payload, Mapping):
        return ActionIntent.from_dict(payload)
    raise TypeError("Intent payload is neither mapping nor ActionIntent")


def _collect_defenders(targets: Iterable[TargetSpec]) -> List[str]:
    defenders: List[str] = []
    for target in targets:
        if target.kind == "entity" and target.reference:
            defenders.append(target.reference)
    return defenders


def _reaction_priority(speed: Any) -> int:
    order = {"fast": 0, "normal": 1, "slow": 2}
    return order.get(str(speed).lower(), 1)


__all__ = ["ReactionManager"]

