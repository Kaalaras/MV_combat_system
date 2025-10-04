"""Utilities for wiring the declarative action pipeline in tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from core.actions.intent import ActionIntent, TargetSpec
from core.actions.selector import ActionSelector
from core.actions.validation import IntentValidator
from core.actions.scheduler import ActionScheduler
from core.actions.performers import ActionPerformer
from core.event_bus import EventBus
from core.events import topics
from core.reactions.manager import ReactionManager


class LoggedEventBus(EventBus):
    """Event bus that records every publication for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.log: list[tuple[str, dict[str, Any]]] = []

    def publish(self, event_type: str, **kwargs: Any) -> None:  # type: ignore[override]
        self.log.append((event_type, dict(kwargs)))
        super().publish(event_type, **kwargs)


@dataclass
class SimpleMovementSystem:
    reachable: list[tuple[int, int, int]] = field(
        default_factory=lambda: [(1, 0, 1), (0, 1, 1)]
    )
    moves: list[tuple[str, tuple[int, int]]] = field(default_factory=list)

    def get_reachable_tiles(self, actor_id: str, distance: int) -> list[tuple[int, int, int]]:
        return list(self.reachable)

    def move(self, actor_id: str, destination: tuple[int, int], **_: Any) -> bool:
        self.moves.append((actor_id, tuple(destination)))
        return True


@dataclass
class SimpleLineOfSight:
    visible: set[tuple[str, str]]

    def has_line_of_sight(self, source_id: str, target_id: str) -> bool:
        return (source_id, target_id) in self.visible


class SimpleECS:
    def __init__(self) -> None:
        self.positions: Dict[str, tuple[int, int]] = {
            "hero": (0, 0),
            "ghoul": (0, 1),
        }
        self.action_points: Dict[str, int] = {"hero": 2, "ghoul": 1}
        self.ammunition: Dict[str, int] = {"hero": 3, "ghoul": 0}
        self.entities: Dict[str, int] = {"hero": 1, "ghoul": 2}
        self._components: Dict[int, Dict[type, Any]] = {}

    def resolve_entity(self, entity_id: str) -> Optional[int]:
        return self.entities.get(entity_id)

    def try_get_component(self, internal_id: int, component_type: type) -> Any:
        return self._components.get(internal_id, {}).get(component_type)

    def add_component(self, internal_id: int, component: Any) -> None:
        self._components.setdefault(internal_id, {})[type(component)] = component


class SimpleRules:
    def __init__(self, ecs: SimpleECS) -> None:
        self.ecs = ecs
        self.movement_system = SimpleMovementSystem()
        self.line_of_sight = SimpleLineOfSight(
            {("hero", "ghoul"), ("ghoul", "hero")}
        )
        self.attacks: list[dict[str, Any]] = []

    def get_move_distance(self, actor_id: str) -> int:
        return 4

    def iter_enemy_ids(self, actor_id: str) -> Iterable[str]:
        return [enemy for enemy in self.ecs.entities if enemy != actor_id]

    def get_position(self, entity_id: str) -> Optional[tuple[int, int]]:
        return self.ecs.positions.get(entity_id)

    def get_action_points(self, actor_id: str) -> int:
        return self.ecs.action_points.get(actor_id, 0)

    def get_ammunition(self, actor_id: str) -> int:
        return self.ecs.ammunition.get(actor_id, 0)

    def get_ranged_range(self, actor_id: str) -> int:
        return 6

    def resolve_attack(self, attacker: str, target: str, **_: Any) -> dict[str, Any]:
        record = {"attacker": attacker, "target": target, "hit": True, "damage": 1}
        self.attacks.append(record)
        return record

    def is_actor_controlled_by(self, actor_id: str, player_id: str) -> bool:
        return True

    def iter_reaction_options(self, action_def: Any, intent: Any) -> Iterable[dict[str, Any]]:
        return ()


class AutoController:
    """Minimal controller that mirrors player-driven input behaviour."""

    def __init__(
        self,
        *,
        default_action: str = "move",
        controlled_actors: Iterable[str] | None = None,
    ) -> None:
        self._bus: LoggedEventBus | None = None
        self._default_action = default_action
        self._controlled = set(controlled_actors or [])
        self.last_requested: Optional[str] = None
        self.performed: list[str] = []
        self.last_actions: tuple[dict[str, Any], ...] | None = None

    def bind(self, bus: LoggedEventBus) -> None:
        self._bus = bus
        bus.subscribe(topics.REQUEST_ACTIONS, self._handle_request)
        bus.subscribe(topics.ACTIONS_AVAILABLE, self._handle_actions)
        bus.subscribe(topics.REACTION_WINDOW_OPENED, self._handle_reactions)

    def on_request_actions(self, actor_id: str) -> None:
        if not self._controls(actor_id):
            return
        self.last_requested = actor_id

    def _handle_request(self, *, actor_id: str, **_: Any) -> None:
        self.on_request_actions(actor_id)

    def _handle_actions(self, *, actor_id: str, actions: Iterable[dict[str, Any]], **_: Any) -> None:
        if self._bus is None or not self._controls(actor_id):
            return
        if self.last_requested and self.last_requested != actor_id:
            return
        self.last_requested = actor_id
        actions_list = list(actions)
        if not actions_list:
            return
        self.last_actions = tuple(actions_list)
        selection = next(
            (action for action in actions_list if action.get("id") == self._default_action),
            actions_list[0],
        )
        targets_payload = selection.get("targets", [])
        targets = tuple(TargetSpec.from_dict(target) for target in targets_payload)
        intent = ActionIntent(
            actor_id=actor_id,
            action_id=str(selection.get("id")),
            targets=targets,
        )
        self.performed.append(intent.action_id)
        self._bus.publish(
            topics.INTENT_SUBMITTED,
            intent=intent.to_dict(),
            intent_obj=intent,
        )

    def _handle_reactions(self, *, actor_id: str, window_id: str, **_: Any) -> None:
        if self._bus is None or not self._controls(actor_id):
            return
        self._bus.publish(
            topics.REACTION_DECLARED,
            actor_id=actor_id,
            passed=True,
            reaction=None,
            window_id=window_id,
        )

    def _controls(self, actor_id: str) -> bool:
        return not self._controlled or actor_id in self._controlled


def build_pipeline(*, default_action: str = "move") -> dict[str, Any]:
    """Create a fully wired intent pipeline ready for tests."""

    bus = LoggedEventBus()
    ecs = SimpleECS()
    rules = SimpleRules(ecs)

    controller = AutoController(default_action=default_action, controlled_actors={"hero"})
    controller.bind(bus)

    selector = ActionSelector(ecs, rules)
    validator = IntentValidator(ecs, rules)
    scheduler = ActionScheduler(ecs)
    reactions = ReactionManager(rules)
    performer = ActionPerformer(rules)

    selector.bind(bus)
    validator.bind(bus)
    scheduler.bind(bus)
    reactions.bind(bus)
    performer.bind(bus)

    def end_turn_on_resolve(*, actor_id: str, **_: Any) -> None:
        bus.publish(topics.END_TURN, actor_id=actor_id)

    bus.subscribe(topics.ACTION_RESOLVED, end_turn_on_resolve)

    return {
        "bus": bus,
        "ecs": ecs,
        "rules": rules,
        "controller": controller,
        "selector": selector,
        "validator": validator,
        "scheduler": scheduler,
        "reactions": reactions,
        "performer": performer,
    }


__all__ = [
    "AutoController",
    "LoggedEventBus",
    "SimpleECS",
    "SimpleRules",
    "build_pipeline",
]
