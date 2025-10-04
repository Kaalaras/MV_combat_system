from __future__ import annotations

from typing import Any

import pytest

from core.characters.query import get_character_summary
from core.events import topics
from core.inventory.query import get_equipped
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.condition_tracker import ConditionTrackerComponent
from ecs.components.entity_id import EntityIdComponent
from ecs.components.equipment import EquipmentComponent
from ecs.ecs_manager import ECSManager
from entities.character import Character


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish(self, event_type: str, /, **payload: Any) -> None:
        self.events.append((event_type, dict(payload)))

    def subscribe(self, *_: Any, **__: Any) -> None:  # pragma: no cover - compatibility
        return


class DummyWeapon:
    def __init__(self, name: str) -> None:
        self.name = name
        self.attack_traits = ("Attributes.Physical.Strength", "Abilities.Talents.Brawl")


@pytest.fixture()
def ecs_manager() -> ECSManager:
    return ECSManager(event_bus=RecordingBus())


def test_get_equipped_returns_items_and_emits_event(ecs_manager: ECSManager) -> None:
    weapon = DummyWeapon("Sword")
    equipment = EquipmentComponent()
    equipment.weapons["melee"] = weapon
    equipment.equipped_weapon = weapon
    equipment.other_items.append("blood_potion")

    ecs_manager.create_entity(EntityIdComponent("hero"), equipment)

    items = get_equipped("hero", ecs_manager)

    assert weapon in items
    assert "blood_potion" in items

    bus = ecs_manager.event_bus
    assert bus is not None
    assert (topics.INVENTORY_QUERIED, {"actor_id": "hero", "items": tuple(items)}) in bus.events


def test_get_equipped_preserves_duplicate_other_items(ecs_manager: ECSManager) -> None:
    equipment = EquipmentComponent()
    equipment.other_items.extend(["blood_potion", "blood_potion"])

    ecs_manager.create_entity(EntityIdComponent("hero"), equipment)

    items = get_equipped("hero", ecs_manager)

    assert items.count("blood_potion") == 2

    bus = ecs_manager.event_bus
    assert bus is not None
    queried = [payload for topic, payload in bus.events if topic == topics.INVENTORY_QUERIED]
    assert queried
    assert queried[-1]["items"].count("blood_potion") == 2


def test_get_character_summary_merges_traits_and_states(ecs_manager: ECSManager) -> None:
    traits = {
        "Attributes": {"Physical": {"Strength": 3, "Dexterity": 2}},
        "Abilities": {"Talents": {"Brawl": 4}},
        "Disciplines": {"Celerity": 2},
    }
    character = Character(name="Test", clan="Brujah", traits=traits, base_traits=traits)
    character.states.add("roused")

    tracker = ConditionTrackerComponent()
    tracker.dynamic_states.add("hidden")

    ecs_manager.create_entity(
        EntityIdComponent("hero"),
        CharacterRefComponent(character),
        tracker,
    )

    summary = get_character_summary("hero", ecs_manager)

    assert summary["name"] == "Test"
    assert summary["clan"] == "Brujah"
    assert summary["attributes"]["Physical"]["Strength"] == 3
    assert summary["skills"]["Talents"]["Brawl"] == 4
    assert "Celerity" in summary["disciplines"]
    assert "roused" in summary["states"]
    assert "hidden" in summary["states"]


def test_get_character_summary_handles_passive_active_states_attribute(
    ecs_manager: ECSManager,
) -> None:
    character = Character(name="Test", clan="Brujah", traits={}, base_traits={})

    tracker = ConditionTrackerComponent()
    tracker.active_states = {"poisoned"}  # type: ignore[assignment]

    ecs_manager.create_entity(
        EntityIdComponent("hero"),
        CharacterRefComponent(character),
        tracker,
    )

    summary = get_character_summary("hero", ecs_manager)

    assert "poisoned" in summary["states"]
