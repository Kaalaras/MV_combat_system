"""Validation layer turning submitted intents into executable actions.

This module is the single entry point between the declarative intent layer and
the execution pipeline.  It validates the incoming :class:`ActionIntent`
instances against lightweight rules (resources, status flags, targeting, ...)
without mutating any game state.  When bound to an event bus it reacts to
``INTENT_SUBMITTED`` events and publishes either ``INTENT_VALIDATED`` or
``INTENT_REJECTED`` accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple

from core.actions.catalog import ACTION_CATALOG, ActionDef
from core.actions.intent import ActionIntent, CostSpec
from core.events import topics


RESOURCE_GETTER_PATTERNS = (
    "get_{resource}",
    "get_{resource}_points",
    "get_{resource}_pool",
    "get_{resource}_remaining",
)


class EventBusLike(Protocol):
    """Minimal protocol required to interact with the project event bus."""

    def subscribe(self, topic: str, handler: Callable[..., None]) -> None:
        ...

    def publish(self, topic: str, /, **payload: Any) -> None:
        ...


@dataclass(frozen=True)
class ValidationResult:
    """Container returned by :func:`validate_intent`."""

    ok: bool
    reason: Optional[str]
    intent: ActionIntent


def validate_intent(
    intent: ActionIntent | Mapping[str, Any],
    ecs: Any,
    rules_ctx: Any,
) -> Tuple[bool, Optional[str], ActionIntent]:
    """Validate an :class:`ActionIntent` without mutating any game state.

    Parameters
    ----------
    intent:
        The incoming intent or its serialised representation.
    ecs:
        ECS façade used for lightweight queries (component lookups, entity
        resolution).  It is *not* mutated by this routine.
    rules_ctx:
        Rules helper providing convenience accessors (movement budget,
        ownership, cooldowns, ...).
    """

    normalised = _coerce_intent(intent)
    action_def = ACTION_CATALOG.get(normalised.action_id)
    if action_def is None:
        return False, "unknown_action", normalised

    reason = _verify_actor(normalised, ecs, rules_ctx)
    if reason is not None:
        return False, reason, normalised

    reason = _verify_action_state(normalised, action_def, ecs, rules_ctx)
    if reason is not None:
        return False, reason, normalised

    reason = _verify_costs(normalised, action_def, ecs, rules_ctx)
    if reason is not None:
        return False, reason, normalised

    reason = _verify_targets(normalised, action_def, ecs, rules_ctx)
    if reason is not None:
        return False, reason, normalised

    reason = _verify_cooldowns(normalised, action_def, rules_ctx)
    if reason is not None:
        return False, reason, normalised

    return True, None, normalised


class IntentValidator:
    """Event-driven wrapper around :func:`validate_intent`."""

    def __init__(self, ecs: Any, rules_ctx: Any) -> None:
        self._ecs = ecs
        self._rules = rules_ctx
        self._bus: EventBusLike | None = None

    def bind(self, bus: EventBusLike) -> None:
        """Subscribe to the intent submission topic on ``bus``."""

        self._bus = bus
        bus.subscribe(topics.INTENT_SUBMITTED, self._handle_intent_submitted)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _handle_intent_submitted(self, *, intent: Any, **extra: Any) -> None:
        if self._bus is None:
            return

        ok, reason, normalised = validate_intent(intent, self._ecs, self._rules)
        payload = {
            "intent": normalised.to_dict(),
            "intent_obj": normalised,
        }
        payload.update(extra)

        if ok:
            payload.setdefault("reason", None)
            self._bus.publish(topics.INTENT_VALIDATED, **payload)
        else:
            payload["reason"] = reason
            self._bus.publish(topics.INTENT_REJECTED, **payload)


# ----------------------------------------------------------------------
# Validation helpers
# ----------------------------------------------------------------------


def _coerce_intent(intent: ActionIntent | Mapping[str, Any]) -> ActionIntent:
    if isinstance(intent, ActionIntent):
        return intent
    if isinstance(intent, Mapping):
        return ActionIntent.from_dict(intent)
    raise TypeError("intent must be an ActionIntent or mapping payload")


def _verify_actor(intent: ActionIntent, ecs: Any, rules_ctx: Any) -> Optional[str]:
    actor_id = intent.actor_id
    if not actor_id:
        return "missing_actor"

    if not _entity_exists(actor_id, ecs):
        return "unknown_actor"

    owner = intent.source_player_id
    if owner:
        checker = getattr(rules_ctx, "is_actor_controlled_by", None)
        if callable(checker) and not checker(actor_id, owner):
            return "unauthorised_actor"

    forbidden_state = getattr(rules_ctx, "is_action_locked", None)
    if callable(forbidden_state) and forbidden_state(actor_id):
        return "actor_locked"

    return None


def _verify_action_state(
    intent: ActionIntent,
    action_def: ActionDef,
    ecs: Any,
    rules_ctx: Any,
) -> Optional[str]:
    checker = getattr(rules_ctx, "is_action_allowed", None)
    if callable(checker):
        allowed = checker(intent.actor_id, action_def.id, intent=intent, ecs=ecs)
        if allowed is False:
            return "action_forbidden"

    blockers = getattr(rules_ctx, "get_blocked_actions", None)
    if callable(blockers):
        blocked = blockers(intent.actor_id)
        blocked_ids = _normalize_blocked_actions(blocked)
        if blocked_ids and action_def.id in blocked_ids:
            return "action_blocked"

    for prereq in action_def.prereqs:
        if isinstance(prereq, str):
            predicate = getattr(rules_ctx, prereq, None)
            if callable(predicate):
                try:
                    result = predicate(
                        intent.actor_id,
                        intent=intent,
                        ecs=ecs,
                        rules=rules_ctx,
                    )
                except TypeError:
                    result = predicate(intent.actor_id)
                if not result:
                    return f"prereq_failed:{prereq}"
            continue

        if callable(prereq):
            try:
                result = prereq(actor_id=intent.actor_id, intent=intent, ecs=ecs, rules=rules_ctx)
            except TypeError:
                result = prereq(intent.actor_id)
            if not result:
                name = getattr(prereq, "__name__", "prereq")
                return f"prereq_failed:{name}"

    return None


def _verify_costs(
    intent: ActionIntent,
    action_def: ActionDef,
    ecs: Any,
    rules_ctx: Any,
) -> Optional[str]:
    costs = action_def.costs
    if not isinstance(costs, CostSpec):
        return None

    for resource, required in costs.to_dict().items():
        if required <= 0:
            continue
        available = _resolve_resource(intent.actor_id, resource, ecs, rules_ctx)
        if available is None:
            continue
        if available < required:
            return f"insufficient_{resource}"
    return None


def _verify_targets(
    intent: ActionIntent,
    action_def: ActionDef,
    ecs: Any,
    rules_ctx: Any,
) -> Optional[str]:
    expected = tuple(action_def.targeting or ())
    provided = intent.targets

    if not expected:
        if provided:
            return "unexpected_targets"
        return None

    allowed_kinds: set[str] = set()
    required_count = 0
    for descriptor in expected:
        if isinstance(descriptor, Mapping):
            kind = str(descriptor.get("kind", descriptor.get("type", ""))).lower()
        else:
            kind = str(descriptor).lower()
        if not kind:
            continue
        allowed_kinds.add(kind)
        required_count += 1

    if required_count and len(provided) < required_count:
        return "missing_targets"

    for target in provided:
        if target.kind.lower() not in allowed_kinds:
            return "invalid_target_kind"
        if target.kind == "entity":
            if not target.reference:
                return "invalid_target_reference"
            if not _entity_exists(target.reference, ecs):
                return "invalid_target_reference"

    validator = getattr(rules_ctx, "validate_targets", None)
    if callable(validator):
        try:
            verdict = validator(intent, action_def, ecs=ecs)
        except TypeError:
            verdict = validator(intent, action_def)
        if isinstance(verdict, tuple):
            ok, reason = verdict
            if not ok:
                return reason or "invalid_targets"
        elif verdict is False:
            return "invalid_targets"

    return None


def _verify_cooldowns(
    intent: ActionIntent,
    action_def: ActionDef,
    rules_ctx: Any,
) -> Optional[str]:
    checker = getattr(rules_ctx, "is_on_cooldown", None)
    if callable(checker):
        on_cooldown = checker(intent.actor_id, action_def.id)
        if on_cooldown:
            return "on_cooldown"

    getter = getattr(rules_ctx, "get_cooldown", None)
    if callable(getter):
        cooldown_value = getter(intent.actor_id, action_def.id)
        if cooldown_value:
            try:
                if int(cooldown_value) > 0:
                    return "on_cooldown"
            except (TypeError, ValueError):
                pass

    return None


def _normalize_blocked_actions(blocked: Any) -> set[str]:
    if not blocked:
        return set()
    if isinstance(blocked, Mapping):
        entries = blocked.values()
    elif isinstance(blocked, str):
        entries = (blocked,)
    else:
        try:
            entries = tuple(blocked)
        except TypeError:
            entries = (blocked,)
    return {str(entry) for entry in entries}


def _entity_exists(entity_id: str, ecs: Any) -> bool:
    if ecs is None:
        return True

    resolver = getattr(ecs, "resolve_entity", None)
    if callable(resolver):
        if resolver(entity_id) is not None:
            return True

    has_entity = getattr(ecs, "has_entity", None)
    if callable(has_entity):
        try:
            if has_entity(entity_id):
                return True
        except TypeError:
            pass

    entities = getattr(ecs, "entities", None)
    if isinstance(entities, Mapping) and entity_id in entities:
        return True

    roster = getattr(ecs, "roster", None)
    if isinstance(roster, Mapping) and entity_id in roster:
        return True

    return False


def _resolve_resource(
    actor_id: str,
    resource: str,
    ecs: Any,
    rules_ctx: Any,
) -> Optional[int]:
    getter_names = tuple(pattern.format(resource=resource) for pattern in RESOURCE_GETTER_PATTERNS)
    for name in getter_names:
        accessor = getattr(rules_ctx, name, None)
        if callable(accessor):
            value = accessor(actor_id)
            if value is not None:
                return int(value)

    mapping = getattr(ecs, resource, None)
    if isinstance(mapping, Mapping):
        value = mapping.get(actor_id)
        if value is not None:
            return int(value)

    getter = getattr(ecs, f"get_{resource}", None)
    if callable(getter):
        value = getter(actor_id)
        if value is not None:
            return int(value)

    return None


__all__ = ["validate_intent", "IntentValidator", "ValidationResult"]

