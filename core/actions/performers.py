"""Action performers translating queued actions into system side-effects."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol

from core.actions.intent import ActionIntent, TargetSpec
from core.events import topics
from core.event_bus import Topic


DEFAULT_ATTACK_DAMAGE = 1


class EventBusLike(Protocol):
    def subscribe(self, topic: Topic, handler: Callable[..., None]) -> None:
        ...

    def publish(
        self, topic: Topic, payload: Mapping[str, Any] | None = None, /, **kwargs: Any
    ) -> None:
        ...


@dataclass(frozen=True)
class PerformActionEvent:
    """Structured view of a ``PERFORM_ACTION`` event payload."""

    intent: ActionIntent
    await_reactions: bool
    reactions_resolved: bool
    payload: Mapping[str, Any]

    @classmethod
    def from_bus(cls, data: Mapping[str, Any]) -> "PerformActionEvent":
        extras = dict(data)
        intent_obj = extras.pop("intent_obj", None)
        intent_payload = extras.get("intent")
        intent = _ensure_intent(intent_obj, intent_payload)
        extras.setdefault("intent", intent.to_dict())
        extras.setdefault("intent_obj", intent)

        await_reactions = bool(extras.pop("await_reactions", False))
        reactions_resolved = bool(extras.pop("reactions_resolved", False))

        # Preserve signalling flags so downstream consumers can still inspect
        # them when the performer republishes the payload.
        extras["await_reactions"] = await_reactions
        extras["reactions_resolved"] = reactions_resolved

        return cls(
            intent=intent,
            await_reactions=await_reactions,
            reactions_resolved=reactions_resolved,
            payload=extras,
        )


class ActionPerformer:
    """Dispatch ``PERFORM_ACTION`` events to the appropriate subsystems."""

    def __init__(self, rules_ctx: Any) -> None:
        self._rules = rules_ctx
        self._bus: EventBusLike | None = None

    def bind(self, bus: EventBusLike) -> None:
        self._bus = bus
        bus.subscribe(topics.PERFORM_ACTION, self._handle_perform_action)

    # ------------------------------------------------------------------
    def _handle_perform_action(self, **raw_payload: Any) -> None:
        if self._bus is None:
            return

        event = PerformActionEvent.from_bus(raw_payload)

        if event.await_reactions and not event.reactions_resolved:
            # Wait for reaction manager to re-dispatch the event.
            return

        normalised = event.intent
        action_id = normalised.action_id
        handler = getattr(self, f"_perform_{action_id}", None)
        if callable(handler):
            result = handler(normalised, event.payload)
        else:
            result = self._perform_generic(normalised, event.payload)

        publish_payload = {
            "actor_id": normalised.actor_id,
            "action_id": normalised.action_id,
            "intent": normalised.to_dict(),
            "result": result,
        }
        publish_payload.update(event.payload)
        self._bus.publish(topics.ACTION_RESOLVED, **publish_payload)

    # ------------------------------------------------------------------
    # Concrete performers
    # ------------------------------------------------------------------
    def _perform_move(self, intent: ActionIntent, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        movement_system = getattr(self._rules, "movement_system", None)
        destination = _first_tile(intent.targets)
        success = False
        if movement_system and destination:
            steps = payload.get("max_steps")
            mover = getattr(movement_system, "move", None)
            if callable(mover):
                if steps is not None and _supports_keyword(mover, "max_steps"):
                    success = bool(mover(intent.actor_id, destination, max_steps=steps))
                else:
                    success = bool(mover(intent.actor_id, destination))
        return {"success": success, "destination": destination}

    def _perform_attack_melee(self, intent: ActionIntent, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._execute_attack("melee", intent, payload)

    def _perform_attack_ranged(self, intent: ActionIntent, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._execute_attack("ranged", intent, payload)

    def _perform_generic(self, intent: ActionIntent, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"handled": False, "payload": dict(payload)}

    # ------------------------------------------------------------------
    def _execute_attack(self, kind: str, intent: ActionIntent, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        resolver = getattr(self._rules, "resolve_attack", None)
        target_id = _first_entity(intent.targets)
        result: dict[str, Any] = {
            "kind": kind,
            "target": target_id,
        }
        if callable(resolver) and target_id:
            kwargs: dict[str, Any] = {}
            if _supports_keyword(resolver, "intent"):
                kwargs["intent"] = intent
            if _supports_keyword(resolver, "payload"):
                kwargs["payload"] = payload
            if _supports_keyword(resolver, "kind"):
                kwargs["kind"] = kind
            try:
                outcome = resolver(intent.actor_id, target_id, **kwargs)
            except TypeError:
                outcome = resolver(intent.actor_id, target_id)
            if isinstance(outcome, Mapping):
                result.update(outcome)

        if "hit" not in result:
            # Minimal deterministic placeholder.
            result["hit"] = bool(target_id)
        if "damage" not in result:
            result["damage"] = DEFAULT_ATTACK_DAMAGE if target_id else 0
        return result


def _ensure_intent(intent_obj: Any | None, payload: Any) -> ActionIntent:
    if isinstance(intent_obj, ActionIntent):
        return intent_obj
    if isinstance(payload, ActionIntent):
        return payload
    if isinstance(payload, Mapping):
        return ActionIntent.from_dict(payload)
    raise TypeError("Intent payload is neither mapping nor ActionIntent")


def _first_tile(targets: Iterable[TargetSpec]) -> Optional[tuple[int, int]]:
    for target in targets:
        if target.kind == "tile" and target.position is not None:
            coords = target.position
            if len(coords) >= 2:
                return int(coords[0]), int(coords[1])
    return None


def _first_entity(targets: Iterable[TargetSpec]) -> Optional[str]:
    for target in targets:
        if target.kind == "entity" and target.reference:
            return target.reference
    return None


def _supports_keyword(callable_obj: Callable[..., Any], keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    params = signature.parameters
    if keyword in params:
        return True
    return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())


__all__ = ["ActionPerformer"]

