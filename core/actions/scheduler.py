"""Action scheduling layer bridging validated intents and execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol

from core.actions.catalog import ACTION_CATALOG, ActionDef
from core.actions.intent import ActionIntent
from core.events import topics
from ecs.components.action_budget import ActionBudgetComponent
from core.event_bus import Topic


class EventBusLike(Protocol):
    def subscribe(self, topic: Topic, handler: Callable[..., None]) -> None:
        ...

    def publish(
        self, topic: Topic, payload: Mapping[str, Any] | None = None, /, **kwargs: Any
    ) -> None:
        ...


@dataclass
class ReservationResult:
    actor_id: str
    action_id: str
    costs: Mapping[str, int]
    reservation_id: Optional[str]


class ActionScheduler:
    """Reserve action budgets and trigger execution."""

    def __init__(self, ecs: Any) -> None:
        self._ecs = ecs
        self._bus: EventBusLike | None = None
        self._fallback_budgets: dict[str, ActionBudgetComponent] = {}

    def bind(self, bus: EventBusLike) -> None:
        self._bus = bus
        bus.subscribe(topics.INTENT_VALIDATED, self._handle_intent_validated)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------
    def _handle_intent_validated(self, *, intent: Any, intent_obj: Any | None = None, **extra: Any) -> None:
        if self._bus is None:
            return

        normalised = _ensure_intent(intent_obj, intent)
        action_def = ACTION_CATALOG.get(normalised.action_id)
        if action_def is None:
            return

        costs = action_def.costs.to_dict()
        reservation_id = extra.get("reservation_id") or normalised.client_tx_id

        budget_component = self._ensure_budget_component(normalised.actor_id)
        budget_component.reserve(costs, transaction_id=reservation_id)

        payload = {
            "actor_id": normalised.actor_id,
            "action_id": normalised.action_id,
            "intent": normalised.to_dict(),
            "intent_obj": normalised,
            "costs": costs,
            "reservation_id": reservation_id,
        }
        payload.update(extra)

        reactionable = _is_reactionable(action_def)
        if reactionable:
            payload.setdefault("await_reactions", True)
        else:
            payload.setdefault("await_reactions", False)

        self._bus.publish(topics.ACTION_ENQUEUED, **payload)
        self._bus.publish(topics.PERFORM_ACTION, **payload)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ensure_budget_component(self, actor_id: str) -> ActionBudgetComponent:
        resolver = getattr(self._ecs, "resolve_entity", None)
        try_get = getattr(self._ecs, "try_get_component", None)
        add_component = getattr(self._ecs, "add_component", None)

        if callable(resolver) and callable(try_get) and callable(add_component):
            internal_id = resolver(actor_id)
            if internal_id is not None:
                component = try_get(internal_id, ActionBudgetComponent)
                if component is None:
                    component = ActionBudgetComponent()
                    add_component(internal_id, component)
                return component

        component = self._fallback_budgets.get(actor_id)
        if component is None:
            component = ActionBudgetComponent()
            self._fallback_budgets[actor_id] = component
        return component


def _ensure_intent(intent_obj: Any | None, payload: Any) -> ActionIntent:
    if isinstance(intent_obj, ActionIntent):
        return intent_obj
    if isinstance(payload, Mapping):
        return ActionIntent.from_dict(payload)
    if isinstance(payload, ActionIntent):
        return payload
    raise TypeError("Intent payload is neither mapping nor ActionIntent")


def _is_reactionable(action_def: ActionDef) -> bool:
    tags = {tag.lower() for tag in action_def.tags}
    if "reactionable" in tags:
        return True
    if "attack" in tags:
        return True
    return False


__all__ = ["ActionScheduler", "ReservationResult"]

