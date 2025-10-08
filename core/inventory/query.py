"""Read-only inventory query helpers."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, TypeAlias

from core.events import topics
from core.event_bus import Topic


ItemRef: TypeAlias = Any


class _EventBusLike(Protocol):
    def publish(
        self, event_type: Topic, payload: Mapping[str, Any] | None = None, /, **kwargs: Any
    ) -> None:
        ...


def get_equipped(actor_id: str, ecs: Any) -> list[ItemRef]:
    """Return equipped item references for ``actor_id`` and emit an event.

    The function inspects the ECS for an :class:`EquipmentComponent` tied to the
    provided ``actor_id``.  It returns a list of item references (weapons, armor,
    miscellaneous gear) without mutating any underlying state.  Regardless of the
    outcome, an :data:`~core.events.topics.INVENTORY_QUERIED` event is published so
    that UI bridges can mirror the same data surfaced to the CLI.
    """

    manager = _locate_ecs_manager(ecs)
    if manager is None:
        items: list[ItemRef] = []
        _publish_inventory_event(actor_id, items, ecs)
        return items

    try:
        from ecs.components.equipment import EquipmentComponent
    except ImportError:  # pragma: no cover - optional dependency guard
        items = []
        _publish_inventory_event(actor_id, items, manager)
        return items

    components = manager.get_components_for_entity(actor_id, EquipmentComponent)
    if not components:
        items = []
        _publish_inventory_event(actor_id, items, manager)
        return items

    equipment = components[0]
    items = _collect_equipment_items(equipment)
    _publish_inventory_event(actor_id, items, manager)
    return items


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_equipment_items(equipment: Any) -> list[ItemRef]:
    items: list[ItemRef] = []
    seen_identities: set[int] = set()

    def _append(item: Any, *, dedupe: bool) -> None:
        if item is None:
            return

        if dedupe:
            identity = id(item)
            if identity in seen_identities:
                return
            seen_identities.add(identity)

        items.append(item)

    _append(getattr(equipment, "equipped_weapon", None), dedupe=True)

    weapons = getattr(equipment, "weapons", {})
    for weapon in weapons.values():
        _append(weapon, dedupe=True)
    _append(getattr(equipment, "armor", None), dedupe=True)

    other_items = getattr(equipment, "other_items", None)
    if isinstance(other_items, Sequence):
        for item in other_items:
            _append(item, dedupe=False)

    return items


def _publish_inventory_event(actor_id: str, items: Sequence[ItemRef], source: Any) -> None:
    event_bus = _locate_event_bus(source)
    if event_bus is None:
        return

    publish = getattr(event_bus, "publish", None)
    if callable(publish):
        publish(topics.INVENTORY_QUERIED, actor_id=actor_id, items=tuple(items))


def _locate_ecs_manager(ecs: Any) -> Any:
    if hasattr(ecs, "resolve_entity"):
        return ecs

    candidate = getattr(ecs, "ecs_manager", None)
    if candidate is not None and hasattr(candidate, "resolve_entity"):
        return candidate

    return None


def _locate_event_bus(source: Any) -> Optional[_EventBusLike]:
    if source is None:
        return None

    event_bus = getattr(source, "event_bus", None)
    if event_bus is not None:
        return event_bus  # type: ignore[return-value]

    if hasattr(source, "game_state"):
        game_state = getattr(source, "game_state")
        return _locate_event_bus(game_state)

    if hasattr(source, "ecs_manager"):
        manager = getattr(source, "ecs_manager")
        return _locate_event_bus(manager)

    return None


__all__ = ["ItemRef", "get_equipped"]
