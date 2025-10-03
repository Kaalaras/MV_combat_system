"""Action performers translating queued actions into system side-effects."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional, Protocol

from core.actions.intent import ActionIntent, TargetSpec
from core.events import topics


class EventBusLike(Protocol):
    def subscribe(self, topic: str, handler: Callable[..., None]) -> None:
        ...

    def publish(self, topic: str, /, **payload: Any) -> None:
        ...


class ActionPerformer:
    """Dispatch ``PERFORM_ACTION`` events to the appropriate subsystems."""

    def __init__(self, rules_ctx: Any) -> None:
        self._rules = rules_ctx
        self._bus: EventBusLike | None = None

    def bind(self, bus: EventBusLike) -> None:
        self._bus = bus
        bus.subscribe(topics.PERFORM_ACTION, self._handle_perform_action)

    # ------------------------------------------------------------------
    def _handle_perform_action(self, *, intent: Any, intent_obj: Any | None = None, await_reactions: bool | None = None, reactions_resolved: bool | None = None, **payload: Any) -> None:
        if self._bus is None:
            return

        if await_reactions and not reactions_resolved:
            # Wait for reaction manager to re-dispatch the event.
            return

        normalised = _ensure_intent(intent_obj, intent)
        action_id = normalised.action_id
        handler = getattr(self, f"_perform_{action_id}", None)
        if callable(handler):
            result = handler(normalised, payload)
        else:
            result = self._perform_generic(normalised, payload)

        publish_payload = {
            "actor_id": normalised.actor_id,
            "action_id": normalised.action_id,
            "intent": normalised.to_dict(),
            "result": result,
        }
        publish_payload.update(payload)
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
            try:
                success = bool(movement_system.move(intent.actor_id, destination, max_steps=steps))
            except TypeError:
                success = bool(movement_system.move(intent.actor_id, destination))
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
            outcome = resolver(intent.actor_id, target_id, intent=intent, payload=payload, kind=kind)
            if isinstance(outcome, Mapping):
                result.update(outcome)
        else:
            # Minimal deterministic placeholder.
            result.setdefault("hit", bool(target_id))
            result.setdefault("damage", 1 if target_id else 0)
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


__all__ = ["ActionPerformer"]

