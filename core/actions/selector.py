"""Computation of the currently available actions for an actor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from core.actions.catalog import ACTION_CATALOG, ActionDef, iter_catalog
from core.actions.intent import TargetSpec
from core.events import topics


class EventBusLike(Protocol):
    def subscribe(self, topic: str, handler: Callable[..., None]) -> None:
        ...

    def publish(self, topic: str, /, **payload: Any) -> None:
        ...


TargetResolver = Callable[[str, Any, Any], Sequence[TargetSpec]]


@dataclass(slots=True)
class ActionOption:
    """Action candidate enriched with gameplay metadata."""

    definition: ActionDef
    valid_targets: list[TargetSpec | TargetResolver] = field(default_factory=list)
    ui_hints: Mapping[str, Any] = field(default_factory=dict)
    predicates_failed: list[str] = field(default_factory=list)

    @property
    def action_id(self) -> str:
        return self.definition.id

    @property
    def is_available(self) -> bool:
        return not self.predicates_failed and bool(self.valid_targets or self._accepts_free_targeting)

    def to_payload(self) -> dict[str, Any]:
        targets_payload: list[Any] = []
        for entry in self.valid_targets:
            if isinstance(entry, TargetSpec):
                targets_payload.append(entry.to_dict())
            else:
                targets_payload.append(entry)

        return {
            "id": self.definition.id,
            "name": self.definition.name,
            "category": self.definition.category,
            "targets": targets_payload,
            "ui_hints": dict(self.ui_hints),
            "tags": list(self.definition.tags),
            "predicates_failed": list(self.predicates_failed),
            "available": self.is_available,
        }

    @property
    def _accepts_free_targeting(self) -> bool:
        return not self.definition.targeting


def compute_available_actions(actor_id: str, ecs: Any, rules_context: Any) -> list[ActionOption]:
    """Return declarative action options for the given actor."""

    options: list[ActionOption] = []

    for action_def in iter_catalog():
        if action_def.reaction_speed and action_def.reaction_speed != "none":
            # Reactions are handled in dedicated windows.
            continue

        option = _evaluate_action(action_def, actor_id, ecs, rules_context)
        options.append(option)

    return options


def _evaluate_action(action_def: ActionDef, actor_id: str, ecs: Any, rules_context: Any) -> ActionOption:
    predicates_failed: list[str] = []
    valid_targets: list[TargetSpec | TargetResolver] = []
    ui_hints: dict[str, Any] = {}

    predicates_failed.extend(
        _check_costs(action_def, actor_id, ecs, rules_context)
    )

    if action_def.id == "move":
        targets, hints, failures = _compute_move_targets(actor_id, ecs, rules_context)
        valid_targets.extend(targets)
        ui_hints.update(hints)
        predicates_failed.extend(failures)
    elif action_def.id == "attack_melee":
        targets, hints, failures = _compute_melee_targets(actor_id, ecs, rules_context)
        valid_targets.extend(targets)
        ui_hints.update(hints)
        predicates_failed.extend(failures)
    elif action_def.id == "attack_ranged":
        targets, hints, failures = _compute_ranged_targets(actor_id, ecs, rules_context)
        valid_targets.extend(targets)
        ui_hints.update(hints)
        predicates_failed.extend(failures)
    elif action_def.id == "discipline_generic":
        ui_hints.setdefault("description", "Invoke a discipline power")

    if not valid_targets and not predicates_failed and action_def.targeting:
        predicates_failed.append("no_valid_targets")

    return ActionOption(
        definition=action_def,
        valid_targets=valid_targets,
        ui_hints=ui_hints,
        predicates_failed=predicates_failed,
    )


def _compute_move_targets(actor_id: str, ecs: Any, rules_context: Any):
    movement_system = getattr(rules_context, "movement_system", None)
    if movement_system is None:
        return [], {}, ["movement_system_unavailable"]

    move_budget = _call_optional(rules_context, "get_movement_budget", actor_id)
    move_distance = _call_optional(rules_context, "get_move_distance", actor_id)
    if move_distance is None:
        move_distance = move_budget

    if not move_distance or move_distance <= 0:
        return [], {}, ["insufficient_movement"]

    reachable: Iterable[tuple[int, int, int]] = movement_system.get_reachable_tiles(actor_id, move_distance)
    targets = [
        TargetSpec.tile((x, y), cost=cost)
        for x, y, cost in reachable
    ]

    if not targets:
        return targets, {"range": move_distance, "mode": "tile"}, ["no_reachable_tiles"]

    hints = {"range": move_distance, "mode": "tile"}
    return targets, hints, []


def _compute_melee_targets(actor_id: str, ecs: Any, rules_context: Any):
    enemies = list(_iter_enemy_ids(rules_context, actor_id))
    if not enemies:
        return [], {}, ["no_enemies"]

    actor_pos = _get_position(actor_id, ecs, rules_context)
    if actor_pos is None:
        return [], {}, ["position_unknown"]

    los_system = getattr(rules_context, "line_of_sight", None)
    valid: list[TargetSpec] = []
    for enemy_id in enemies:
        enemy_pos = _get_position(enemy_id, ecs, rules_context)
        if enemy_pos is None:
            continue
        if _manhattan_distance(actor_pos, enemy_pos) != 1:
            continue
        if los_system and not los_system.has_line_of_sight(actor_id, enemy_id):
            continue
        valid.append(TargetSpec.entity(enemy_id, distance=1))

    if not valid:
        return valid, {"range": 1, "mode": "entity"}, ["no_adjacent_enemies"]

    hints = {"range": 1, "mode": "entity", "weapon": "melee"}
    return valid, hints, []


def _compute_ranged_targets(actor_id: str, ecs: Any, rules_context: Any):
    enemies = list(_iter_enemy_ids(rules_context, actor_id))
    if not enemies:
        return [], {}, ["no_enemies"]

    actor_pos = _get_position(actor_id, ecs, rules_context)
    if actor_pos is None:
        return [], {}, ["position_unknown"]

    max_range = _call_optional(rules_context, "get_ranged_range", actor_id)
    if max_range is None:
        max_range = _call_optional(rules_context, "get_default_ranged_range", actor_id)
    if max_range is None:
        max_range = 6

    if max_range <= 0:
        return [], {}, ["no_ranged_weapon"]

    los_system = getattr(rules_context, "line_of_sight", None)
    valid: list[TargetSpec] = []
    for enemy_id in enemies:
        enemy_pos = _get_position(enemy_id, ecs, rules_context)
        if enemy_pos is None:
            continue
        distance = _manhattan_distance(actor_pos, enemy_pos)
        if distance > max_range:
            continue
        if los_system and not los_system.has_line_of_sight(actor_id, enemy_id):
            continue
        valid.append(TargetSpec.entity(enemy_id, distance=distance))

    if not valid:
        return valid, {"range": max_range, "mode": "entity"}, ["no_targets_in_range"]

    hints = {"range": max_range, "mode": "entity", "weapon": "ranged"}
    return valid, hints, []


def _call_optional(context: Any, attr: str, *args: Any) -> Any:
    candidate = getattr(context, attr, None)
    if callable(candidate):
        return candidate(*args)
    return None


def _iter_enemy_ids(rules_context: Any, actor_id: str) -> Iterable[str]:
    iterable = _call_optional(rules_context, "iter_enemy_ids", actor_id)
    if iterable is None:
        iterable = _call_optional(rules_context, "get_enemy_ids", actor_id)
    if iterable is None:
        return ()
    return iterable


def _coerce_position(value: Any) -> Optional[tuple[int, int]]:
    if value is None or isinstance(value, (str, bytes)):
        return None

    try:
        x, y = value
    except (TypeError, ValueError):
        return None

    try:
        return int(x), int(y)
    except (TypeError, ValueError):
        return None


def _get_position(entity_id: str, ecs: Any, rules_context: Any) -> Optional[tuple[int, int]]:
    getter = getattr(rules_context, "get_position", None)
    if callable(getter):
        position = getter(entity_id)
        coerced = _coerce_position(position)
        if coerced is not None:
            return coerced

    getter = getattr(ecs, "get_position", None)
    if callable(getter):
        position = getter(entity_id)
        coerced = _coerce_position(position)
        if coerced is not None:
            return coerced

    positions = getattr(ecs, "positions", None)
    if isinstance(positions, Mapping):
        value = positions.get(entity_id)
        coerced = _coerce_position(value)
        if coerced is not None:
            return coerced

    return None


def _manhattan_distance(a: Sequence[int], b: Sequence[int]) -> int:
    return sum(abs(int(x) - int(y)) for x, y in zip(a, b))


def _check_costs(action_def: ActionDef, actor_id: str, ecs: Any, rules_context: Any) -> list[str]:
    failures: list[str] = []
    costs = action_def.costs
    cost_items = costs.to_dict().items()
    for resource, required in cost_items:
        if required <= 0:
            continue
        available = _resolve_resource(actor_id, resource, ecs, rules_context)
        if available is None:
            continue
        if available < required:
            failures.append(f"insufficient_{resource}")
    return failures


def _resolve_resource(actor_id: str, resource: str, ecs: Any, rules_context: Any) -> Optional[int]:
    getter_name_variants = [
        f"get_{resource}",
        f"get_{resource}_points",
        f"get_{resource}_pool",
        f"get_{resource}_remaining",
    ]
    for name in getter_name_variants:
        value = _call_optional(rules_context, name, actor_id)
        if value is not None:
            return int(value)

    accessor = getattr(ecs, resource, None)
    if isinstance(accessor, Mapping):
        value = accessor.get(actor_id)
        if value is not None:
            return int(value)

    getter = getattr(ecs, f"get_{resource}", None)
    if callable(getter):
        value = getter(actor_id)
        if value is not None:
            return int(value)

    return None


class ActionSelector:
    """Event-driven wrapper around :func:`compute_available_actions`."""

    def __init__(self, ecs: Any, rules_context: Any) -> None:
        self._ecs = ecs
        self._rules = rules_context
        self._bus: EventBusLike | None = None

    def bind(self, event_bus: EventBusLike) -> None:
        self._bus = event_bus
        event_bus.subscribe(topics.REQUEST_ACTIONS, self._handle_request_actions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _handle_request_actions(self, *, actor_id: str, **payload: Any) -> None:
        if self._bus is None:
            return

        options = compute_available_actions(str(actor_id), self._ecs, self._rules)
        actions_payload = [option.to_payload() for option in options]

        publish_payload = {
            "actor_id": str(actor_id),
            "actions": actions_payload,
        }
        publish_payload.update({k: v for k, v in payload.items() if k not in publish_payload})

        self._bus.publish(topics.ACTIONS_AVAILABLE, **publish_payload)

