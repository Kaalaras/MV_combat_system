from core.game_state import GameState
from ecs.components.condition_tracker import ConditionTrackerComponent
from ecs.components.position import PositionComponent


def test_entities_view_returns_same_component_instance():
    game_state = GameState()
    position = PositionComponent(1, 2)

    game_state.add_entity("entity", {"position": position})

    entity_components = game_state.entities["entity"]
    assert entity_components["position"] is position

    for _, components in game_state.entities.items():
        assert "position" in components


def test_get_entity_populates_conditions_from_tracker():
    game_state = GameState()
    tracker = ConditionTrackerComponent()
    tracker.dynamic_states.add("poisoned")
    tracker.conditions["burning"] = object()

    game_state.add_entity(
        "entity",
        {
            "position": PositionComponent(0, 0),
            "condition_tracker": tracker,
        },
    )

    entity_data = game_state.get_entity("entity")

    assert entity_data is not None
    assert entity_data["condition_tracker"] is tracker
    assert entity_data["conditions"] == tracker.active_states()
    assert "position" in entity_data
