import unittest
from typing import Any, Dict, List, Optional, Tuple

from core.event_bus import EventBus
from ecs.components.character_ref import CharacterRefComponent
from ecs.components.entity_id import EntityIdComponent
from ecs.components.initiative import InitiativeComponent
from ecs.ecs_manager import ECSManager
from ecs.systems.turn_order_system import TurnOrderSystem


class _DummyCharacter:
    def __init__(self, name, self_control, instinct, wits, initiative_mod=0, is_dead=False):
        self.name = name
        self.traits = {
            "Virtues": {"Self-Control": self_control, "Instinct": instinct},
            "Attributes": {"Mental": {"Wits": wits}},
        }
        self.initiative_mod = initiative_mod
        self.is_dead = is_dead


class TurnOrderSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event_bus = EventBus()
        self.ecs_manager = ECSManager(self.event_bus)

    def _create_entity(
        self,
        entity_id: str,
        character: _DummyCharacter,
        *,
        bonus: int = 0,
        override: Optional[int] = None,
        enabled: bool = True,
    ) -> int:
        return self.ecs_manager.create_entity(
            EntityIdComponent(entity_id),
            CharacterRefComponent(character),
            InitiativeComponent(bonus=bonus, override=override, enabled=enabled),
        )

    def test_turn_order_uses_component_data(self) -> None:
        events: List[Tuple[str, Dict[str, Any]]] = []
        self.event_bus.subscribe("round_started", lambda **d: events.append(("round_started", d)))
        self.event_bus.subscribe("turn_started", lambda **d: events.append(("turn_started", d)))

        self._create_entity(
            "alpha",
            _DummyCharacter("Alpha", self_control=2, instinct=1, wits=3, initiative_mod=1),
            bonus=1,
        )
        self._create_entity(
            "bravo",
            _DummyCharacter("Bravo", self_control=1, instinct=5, wits=2),
        )
        # Dead entities are excluded from turn order calculations.
        self._create_entity(
            "charlie",
            _DummyCharacter("Charlie", self_control=3, instinct=3, wits=3, is_dead=True),
        )

        system = TurnOrderSystem(self.ecs_manager, self.event_bus)

        self.assertEqual(system.get_turn_order(), ["alpha", "bravo"])
        self.assertEqual(
            system.calculate_initiative(
                CharacterRefComponent(_DummyCharacter("Temp", 1, 1, 1)),
                InitiativeComponent(),
            ),
            2,
        )

        # Initial round publication should fire once for the round and once for the first turn.
        self.assertEqual(events[0][0], "round_started")
        self.assertEqual(events[0][1]["round_number"], 1)
        self.assertEqual(events[1][0], "turn_started")
        self.assertEqual(events[1][1]["entity_id"], "alpha")

    def test_next_turn_publishes_lifecycle_events(self) -> None:
        events: List[Tuple[str, Dict[str, Any]]] = []
        for event_name in ("round_started", "turn_started", "turn_ended"):
            self.event_bus.subscribe(event_name, lambda en=event_name, **d: events.append((en, d)))

        self._create_entity(
            "alpha",
            _DummyCharacter("Alpha", self_control=2, instinct=1, wits=3),
            override=10,
        )
        self._create_entity(
            "bravo",
            _DummyCharacter("Bravo", self_control=1, instinct=5, wits=2),
            override=5,
        )

        system = TurnOrderSystem(self.ecs_manager, self.event_bus)

        # Ignore initial publications from constructor for this portion of the test.
        events.clear()
        system.next_turn()

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0][0], "turn_ended")
        self.assertEqual(events[0][1]["entity_id"], "alpha")
        self.assertEqual(events[1][0], "turn_started")
        self.assertEqual(events[1][1]["entity_id"], "bravo")

        events.clear()
        system.next_turn()

        # Advancing past the final entity should publish an end event followed by a new round.
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[0][0], "turn_ended")
        round_events = [evt for evt in events if evt[0] == "round_started"]
        self.assertTrue(round_events)
        self.assertEqual(round_events[0][1]["round_number"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
