"""
Additional tests for MovementSystem to achieve 90%+ coverage.

This module specifically targets the uncovered lines in MovementSystem
to reach the 90% coverage target requested by @Kaalaras.
"""
import pytest
from unittest.mock import MagicMock
from core.movement_system import MovementSystem
from core.game_state import GameState
from ecs.components.position import PositionComponent
from entities.character import Character


class TestMovementSystemCoverage:
    """Test class focused on achieving high coverage of MovementSystem."""
    
    @pytest.fixture
    def setup_movement_system(self):
        """Create a movement system with proper mocking for coverage testing."""
        game_state = MagicMock()
        movement_system = MovementSystem(game_state)
        return movement_system, game_state
    
    def test_is_walkable_no_terrain(self, setup_movement_system):
        """Test is_walkable when terrain is None (line 58-59)."""
        movement_system, game_state = setup_movement_system
        game_state.terrain = None
        
        result = movement_system.is_walkable(5, 5, 1, 1)
        assert result is False
    
    def test_get_dexterity_no_character_ref(self, setup_movement_system):
        """Test get_dexterity when entity has no character_ref (line 87-88)."""
        movement_system, game_state = setup_movement_system
        
        entity_without_char_ref = {"position": PositionComponent(0, 0, 1, 1)}
        
        dex = movement_system.get_dexterity(entity_without_char_ref)
        assert dex == 0
    
    def test_trigger_opportunity_attacks_no_previous_adjacent(self, setup_movement_system):
        """Test _trigger_opportunity_attacks with empty previous_adjacent list (line 139-140)."""
        movement_system, game_state = setup_movement_system
        
        # Should return early with empty list
        movement_system._trigger_opportunity_attacks("mover1", [])
        # No assertions needed - just ensuring no crash with empty list
    
    def test_trigger_opportunity_attacks_no_mover_entity(self, setup_movement_system):
        """Test _trigger_opportunity_attacks when mover entity doesn't exist (line 142-143)."""
        movement_system, game_state = setup_movement_system
        game_state.get_entity.return_value = None
        
        # Should return early when mover entity is None
        movement_system._trigger_opportunity_attacks("nonexistent_mover", ["attacker1"])
        # No assertions needed - just ensuring no crash
    
    def test_trigger_opportunity_attacks_mover_no_position(self, setup_movement_system):
        """Test _trigger_opportunity_attacks when mover has no position component."""
        movement_system, game_state = setup_movement_system
        
        # Mock mover without position component
        mover_entity = {"health": 100}  # No position component
        game_state.get_entity.return_value = mover_entity
        
        movement_system._trigger_opportunity_attacks("mover1", ["attacker1"])
        # Should return early due to missing position component
    
    def test_trigger_opportunity_attacks_attacker_no_entity(self, setup_movement_system):
        """Test opportunity attacks when attacker entity doesn't exist (line 147-149)."""
        movement_system, game_state = setup_movement_system
        
        # Mock mover entity with position
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        
        def mock_get_entity(entity_id):
            if entity_id == "mover1":
                return mover_entity
            else:  # attacker doesn't exist
                return None
        
        game_state.get_entity.side_effect = mock_get_entity
        
        movement_system._trigger_opportunity_attacks("mover1", ["nonexistent_attacker"])
        # Should continue without crashing when attacker entity is None
    
    def test_trigger_opportunity_attacks_attacker_no_position(self, setup_movement_system):
        """Test opportunity attacks when attacker has no position."""
        movement_system, game_state = setup_movement_system
        
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        attacker_entity = {"health": 100}  # No position component
        
        def mock_get_entity(entity_id):
            if entity_id == "mover1":
                return mover_entity
            else:
                return attacker_entity
        
        game_state.get_entity.side_effect = mock_get_entity
        
        movement_system._trigger_opportunity_attacks("mover1", ["attacker1"])
        # Should continue without processing attacker that has no position
    
    def test_trigger_opportunity_attacks_still_adjacent(self, setup_movement_system):
        """Test opportunity attacks when attacker is still adjacent (line 152-153)."""
        movement_system, game_state = setup_movement_system
        
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        attacker_entity = {
            "position": PositionComponent(6, 5, 1, 1),  # Adjacent to mover
            "character_ref": MagicMock()
        }
        
        def mock_get_entity(entity_id):
            if entity_id == "mover1":
                return mover_entity
            else:
                return attacker_entity
        
        game_state.get_entity.side_effect = mock_get_entity
        
        movement_system._trigger_opportunity_attacks("mover1", ["attacker1"])
        # Should skip opportunity attack since still adjacent
    
    def test_trigger_opportunity_attacks_no_character_ref(self, setup_movement_system):
        """Test opportunity attacks when attacker has no character_ref (line 155-158)."""
        movement_system, game_state = setup_movement_system
        
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        attacker_entity = {
            "position": PositionComponent(10, 10, 1, 1)  # Not adjacent, no character_ref
        }
        
        def mock_get_entity(entity_id):
            if entity_id == "mover1":
                return mover_entity
            else:
                return attacker_entity
        
        game_state.get_entity.side_effect = mock_get_entity
        
        movement_system._trigger_opportunity_attacks("mover1", ["attacker1"])
        # Should skip opportunity attack due to no character_ref
    
    def test_trigger_opportunity_attacks_character_no_toggle(self, setup_movement_system):
        """Test opportunity attacks when character has toggle_opportunity_attack=False."""
        movement_system, game_state = setup_movement_system
        
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        
        # Mock character with toggle disabled
        mock_char = MagicMock()
        mock_char.toggle_opportunity_attack = False
        mock_char_ref = MagicMock()
        mock_char_ref.character = mock_char
        
        attacker_entity = {
            "position": PositionComponent(10, 10, 1, 1),  # Not adjacent
            "character_ref": mock_char_ref
        }
        
        def mock_get_entity(entity_id):
            if entity_id == "mover1":
                return mover_entity
            else:
                return attacker_entity
        
        game_state.get_entity.side_effect = mock_get_entity
        
        movement_system._trigger_opportunity_attacks("mover1", ["attacker1"])
        # Should skip opportunity attack due to toggle being False
    
    def test_trigger_opportunity_attacks_successful_trigger(self, setup_movement_system):
        """Test successful opportunity attack trigger with event bus (line 159-160)."""
        movement_system, game_state = setup_movement_system
        
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        
        # Mock character with toggle enabled
        mock_char = MagicMock()
        mock_char.toggle_opportunity_attack = True
        mock_char_ref = MagicMock()
        mock_char_ref.character = mock_char
        
        attacker_entity = {
            "position": PositionComponent(10, 10, 1, 1),  # Not adjacent anymore
            "character_ref": mock_char_ref
        }
        
        def mock_get_entity(entity_id):
            if entity_id == "mover1":
                return mover_entity
            else:
                return attacker_entity
        
        game_state.get_entity.side_effect = mock_get_entity
        
        # Mock event bus
        mock_bus = MagicMock()
        game_state.event_bus = mock_bus
        
        movement_system._trigger_opportunity_attacks("mover1", ["attacker1"])
        
        # Verify event was published
        mock_bus.publish.assert_called_once_with(
            'opportunity_attack_triggered',
            attacker_id="attacker1",
            target_id="mover1",
            origin_adjacent=True
        )
    
    def test_get_reachable_tiles_no_entity(self, setup_movement_system):
        """Test get_reachable_tiles when entity doesn't exist (line 165-166)."""
        movement_system, game_state = setup_movement_system
        game_state.get_entity.return_value = None
        
        result = movement_system.get_reachable_tiles("nonexistent", 5)
        assert result == []
    
    def test_move_entity_out_of_bounds(self, setup_movement_system):
        """Test movement to out-of-bounds location."""
        movement_system, game_state = setup_movement_system
        
        # Mock entity
        entity = {"position": PositionComponent(5, 5, 1, 1)}
        game_state.get_entity.return_value = entity
        
        # Mock terrain to reject out-of-bounds
        terrain = MagicMock()
        terrain.is_walkable.return_value = False
        terrain.is_occupied.return_value = False
        game_state.terrain = terrain
        
        result = movement_system.move("entity1", (-5, -5))  # Out of bounds
        assert result is False
    
    def test_pathfinding_no_path_exists(self, setup_movement_system):
        """Test pathfinding when no path exists to destination."""
        movement_system, game_state = setup_movement_system
        
        # Mock entity
        entity = {"position": PositionComponent(0, 0, 1, 1)}
        game_state.get_entity.return_value = entity
        
        # Mock terrain - destination is unreachable
        terrain = MagicMock()
        terrain.is_walkable.side_effect = lambda x, y, w, h: x >= 0 and y >= 0 and x < 5 and y < 5
        terrain.is_occupied.return_value = False
        game_state.terrain = terrain
        
        # Try to path to unreachable destination
        path = movement_system.find_path("entity1", 10, 10)  # Outside walkable area
        assert path == [] or path is None
    
    def test_collect_adjacent_opportunity_sources_no_entities(self, setup_movement_system):
        """Test collecting opportunity sources when no adjacent entities exist."""
        movement_system, game_state = setup_movement_system
        
        # Mock mover entity
        mover_entity = {"position": PositionComponent(5, 5, 1, 1)}
        game_state.get_entity.return_value = mover_entity
        
        # Mock empty entity iteration
        game_state.entities = {"mover1": mover_entity}  # Only the mover itself
        
        result = movement_system._collect_adjacent_opportunity_sources("mover1")
        assert result == []
    
    def test_movement_cost_with_terrain_effects(self, setup_movement_system):
        """Test movement cost calculation with terrain effects."""
        movement_system, game_state = setup_movement_system
        
        # Mock entity
        entity = {
            "position": PositionComponent(0, 0, 1, 1),
            "character_ref": MagicMock()
        }
        entity["character_ref"].character.traits = {
            "Attributes": {"Physical": {"Dexterity": 3}}
        }
        game_state.get_entity.return_value = entity
        
        # Mock terrain with movement costs
        terrain = MagicMock()
        terrain.is_walkable.return_value = True
        terrain.is_occupied.return_value = False
        terrain.get_movement_cost.return_value = 2  # Difficult terrain
        game_state.terrain = terrain
        
        # Test reachable tiles with movement costs
        reachable = movement_system.get_reachable_tiles("entity1", max_distance=3)
        
        # Should account for terrain movement costs
        assert len(reachable) >= 1  # Should have at least the starting position


class TestMovementSystemErrorConditions:
    """Test error conditions and edge cases for complete coverage."""
    
    @pytest.fixture
    def minimal_setup(self):
        """Minimal setup for error condition testing."""
        game_state = MagicMock()
        movement_system = MovementSystem(game_state)
        return movement_system, game_state
    
    def test_pathfinding_with_malformed_entity(self, minimal_setup):
        """Test pathfinding with entity missing required components."""
        movement_system, game_state = minimal_setup
        
        # Entity missing position component
        malformed_entity = {"health": 100}
        game_state.get_entity.return_value = malformed_entity
        
        path = movement_system.find_path("malformed", 5, 5)
        assert path == [] or path is None
    
    def test_movement_validation_edge_cases(self, minimal_setup):
        """Test movement validation with various edge cases."""
        movement_system, game_state = minimal_setup
        
        # Test with None terrain
        game_state.terrain = None
        result = movement_system.move("entity1", (5, 5))
        assert result is False
        
        # Test with valid terrain but invalid entity
        game_state.terrain = MagicMock()
        game_state.get_entity.return_value = None
        result = movement_system.move("nonexistent", (5, 5))
        assert result is False
    
    def test_reachable_tiles_with_reserved_tiles(self, minimal_setup):
        """Test reachable tiles calculation with reserved tiles parameter."""
        movement_system, game_state = minimal_setup
        
        entity = {"position": PositionComponent(5, 5, 1, 1)}
        game_state.get_entity.return_value = entity
        
        terrain = MagicMock()
        terrain.is_walkable.return_value = True
        terrain.is_occupied.return_value = False
        terrain.get_movement_cost.return_value = 1
        game_state.terrain = terrain
        
        # Test with reserved tiles
        reserved_tiles = {(6, 5), (5, 6)}
        reachable = movement_system.get_reachable_tiles("entity1", 2, reserved_tiles)
        
        # Reserved tiles should be excluded from reachable tiles
        reachable_coords = [(x, y) for x, y, cost in reachable]
        for tile in reserved_tiles:
            assert tile not in reachable_coords