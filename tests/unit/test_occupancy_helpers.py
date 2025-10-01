"""Unit tests for ECS occupancy helper utilities."""

from ecs.components.body_footprint import BodyFootprintComponent
from ecs.components.entity_id import EntityIdComponent
from ecs.components.position import PositionComponent
from ecs.ecs_manager import ECSManager
from ecs.helpers.occupancy import collect_blocked_tiles, get_entity_tiles


class TestOccupancyHelpers:
    def setup_method(self) -> None:
        self.ecs = ECSManager()

    def test_zero_sized_position_still_blocks_anchor(self) -> None:
        """Zero-width/height positions should still occupy their anchor tile."""

        entity_id = "zero"
        self.ecs.create_entity(
            EntityIdComponent(entity_id),
            PositionComponent(3, 4, width=0, height=0),
        )

        tiles = get_entity_tiles(self.ecs, entity_id)
        assert tiles == {(3, 4)}

        blocked = collect_blocked_tiles(self.ecs)
        assert (3, 4) in blocked

    def test_body_footprint_offsets_expand_correctly(self) -> None:
        """Custom body footprints should expand into absolute occupied tiles."""

        entity_id = "ogre"
        footprint = BodyFootprintComponent(frozenset({(0, 0), (1, 0), (0, 1)}))
        self.ecs.create_entity(
            EntityIdComponent(entity_id),
            PositionComponent(5, 6),
            footprint,
        )

        tiles = get_entity_tiles(self.ecs, entity_id)
        assert tiles == {(5, 6), (6, 6), (5, 7)}

        blocked = collect_blocked_tiles(self.ecs)
        assert {(5, 6), (6, 6), (5, 7)}.issubset(blocked)

        ignored = collect_blocked_tiles(self.ecs, ignore_entities={entity_id})
        assert {(5, 6), (6, 6), (5, 7)}.isdisjoint(ignored)
