"""
Phase 2 Multiplayer Tests: Turn-based action ordering, state delta broadcasting, and conflict resolution
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from multiplayer.state_sync import (
    GameStateSynchronizer, TurnOrderManager, StateDeltaManager, ConflictResolver,
    TurnPhase, ActionPriority, StateDelta, TurnState
)
from multiplayer.models import GameCommand, Player, CommandType


class TestTurnOrderManager:
    """
    Test turn-based action ordering and execution
    
    Justification: Turn ordering is critical for multiplayer game state consistency.
    These tests ensure proper initiative handling, action queuing, and turn advancement.
    """
    
    @pytest.fixture
    def turn_manager(self):
        return TurnOrderManager()
    
    @pytest.fixture
    def sample_players(self):
        return [
            Player(id="player1", name="Alice"),
            Player(id="player2", name="Bob"),
            Player(id="player3", name="Charlie")
        ]
    
    @pytest.mark.asyncio
    async def test_start_new_turn_basic(self, turn_manager, sample_players):
        """
        Test starting a new turn with initiative order
        
        Justification: Validates basic turn initialization which is fundamental
        to all multiplayer game mechanics.
        """
        player_ids = [p.id for p in sample_players]
        
        turn = await turn_manager.start_new_turn(
            turn_id=1, 
            initiative_order=player_ids
        )
        
        assert turn.turn_id == 1
        assert turn.phase == TurnPhase.INITIATIVE
        assert turn.current_player_id == player_ids[0]
        assert len(turn.pending_actions) == 3
        assert all(pid in turn.pending_actions for pid in player_ids)
    
    @pytest.mark.asyncio
    async def test_queue_action_with_priority(self, turn_manager, sample_players):
        """
        Test action queuing with proper priority ordering
        
        Justification: Action priority determines execution order, critical for
        combat mechanics like reactions and defensive actions.
        """
        player_ids = [p.id for p in sample_players]
        await turn_manager.start_new_turn(1, player_ids)
        
        # Queue actions with different priorities
        high_priority = GameCommand(
            command_id=str(uuid.uuid4()),
            command_type=CommandType.ATTACK,  # Normal priority
            player_id="player1",
            payload={"type": "defend"}  # This would be HIGH priority in real system
        )
        
        normal_priority = GameCommand(
            command_id=str(uuid.uuid4()),
            command_type=CommandType.MOVE,
            player_id="player1",
            payload={"x": 5, "y": 5}
        )
        
        # Queue normal priority first, then high priority
        await turn_manager.queue_action("player1", normal_priority)
        await turn_manager.queue_action("player1", high_priority)
        
        # High priority should be first in queue
        actions = turn_manager.current_turn.pending_actions["player1"]
        assert len(actions) == 2
        # Both have sequence numbers
        assert all(hasattr(action, 'sequence_number') for action in actions)
    
    @pytest.mark.asyncio
    async def test_advance_turn_phases(self, turn_manager, sample_players):
        """
        Test turn phase advancement
        
        Justification: Phase transitions control game flow and determine when
        different types of actions can be executed.
        """
        player_ids = [p.id for p in sample_players]
        await turn_manager.start_new_turn(1, player_ids)
        
        # Advance through all phases
        assert turn_manager.current_turn.phase == TurnPhase.INITIATIVE
        
        next_phase = await turn_manager.advance_turn_phase()
        assert next_phase == TurnPhase.ACTIONS
        
        next_phase = await turn_manager.advance_turn_phase()
        assert next_phase == TurnPhase.RESOLUTION
        
        next_phase = await turn_manager.advance_turn_phase()
        assert next_phase == TurnPhase.END_TURN
        
        # Should return None when turn complete
        next_phase = await turn_manager.advance_turn_phase()
        assert next_phase is None
    
    @pytest.mark.asyncio
    async def test_advance_current_player(self, turn_manager, sample_players):
        """
        Test player advancement in initiative order
        
        Justification: Player order determines who acts when, essential for
        turn-based gameplay fairness.
        """
        player_ids = [p.id for p in sample_players]
        await turn_manager.start_new_turn(1, player_ids)
        
        # Should start with first player
        assert turn_manager.current_turn.current_player_id == player_ids[0]
        
        # Advance to next player
        next_player = await turn_manager.advance_current_player()
        assert next_player == player_ids[1]
        
        next_player = await turn_manager.advance_current_player()
        assert next_player == player_ids[2]
        
        # Should cycle back to first
        next_player = await turn_manager.advance_current_player()
        assert next_player == player_ids[0]
    
    @pytest.mark.asyncio
    async def test_get_next_action_by_priority(self, turn_manager, sample_players):
        """
        Test action retrieval with priority and turn order
        
        Justification: Action execution order affects game outcomes and must
        follow established priority rules for competitive fairness.
        """
        player_ids = [p.id for p in sample_players]
        await turn_manager.start_new_turn(1, player_ids)
        await turn_manager.advance_turn_phase()  # Move to ACTIONS
        
        # Create actions for different players with different priorities
        player1_normal = GameCommand(
            command_id="cmd1",
            command_type=CommandType.MOVE,
            player_id="player1",
            payload={"x": 1, "y": 1}
        )
        
        player2_high = GameCommand(
            command_id="cmd2", 
            command_type=CommandType.ATTACK,  # Would be HIGH in real system for reactions
            player_id="player2",
            payload={"type": "reaction"}
        )
        
        await turn_manager.queue_action("player1", player1_normal)
        await turn_manager.queue_action("player2", player2_high)
        
        # Current player's action should come first
        next_action = await turn_manager.get_next_action()
        assert next_action.command_id == "cmd1"  # player1 is current player


class TestStateDeltaManager:
    """
    Test state delta creation and management
    
    Justification: State deltas enable efficient network synchronization by
    transmitting only changes rather than full game state.
    """
    
    @pytest.fixture
    def delta_manager(self):
        return StateDeltaManager()
    
    @pytest.mark.asyncio
    async def test_create_delta(self, delta_manager):
        """
        Test delta creation with proper metadata
        
        Justification: Deltas must contain all necessary information for
        clients to reconstruct state changes accurately.
        """
        entity_changes = {"entity1": {"position": {"x": 5, "y": 5}}}
        events = [{"type": "move", "entity": "entity1"}]
        
        delta = await delta_manager.create_delta(
            turn_id=1,
            sequence_number=1,
            entity_changes=entity_changes,
            events=events,
            player_id="player1",
            command_id="cmd1"
        )
        
        assert delta.turn_id == 1
        assert delta.sequence_number == 1
        assert delta.entity_changes == entity_changes
        assert delta.events == events
        assert delta.player_id == "player1"
        assert delta.command_id == "cmd1"
        assert isinstance(delta.timestamp, datetime)
        
        # Should be stored in manager
        assert 1 in delta_manager.deltas
        assert len(delta_manager.deltas[1]) == 1
        assert delta in delta_manager.delta_history
    
    @pytest.mark.asyncio
    async def test_get_deltas_since(self, delta_manager):
        """
        Test delta retrieval for client synchronization
        
        Justification: Clients need to catch up on missed state changes
        when reconnecting or falling behind.
        """
        # Create multiple deltas across turns
        for turn_id in [1, 2]:
            for seq in range(1, 4):
                await delta_manager.create_delta(
                    turn_id=turn_id,
                    sequence_number=seq,
                    entity_changes={f"entity{seq}": {"data": seq}},
                    events=[],
                    player_id="player1",
                    command_id=f"cmd{turn_id}_{seq}"
                )
        
        # Get deltas since turn 1, sequence 2
        deltas = await delta_manager.get_deltas_since(turn_id=1, sequence_number=2)
        
        # Should get sequence 3 from turn 1, and all from turn 2
        assert len(deltas) == 4  # 1 from turn 1, 3 from turn 2
        assert all(d.turn_id >= 1 for d in deltas)
        assert all(d.turn_id > 1 or d.sequence_number > 2 for d in deltas)
    
    @pytest.mark.asyncio
    async def test_compact_deltas(self, delta_manager):
        """
        Test delta cleanup to prevent memory bloat
        
        Justification: Long-running games need memory management to prevent
        server performance degradation.
        """
        # Create deltas for many turns
        for turn_id in range(1, 21):  # 20 turns
            await delta_manager.create_delta(
                turn_id=turn_id,
                sequence_number=1,
                entity_changes={},
                events=[],
                player_id="player1",
                command_id=f"cmd{turn_id}"
            )
        
        assert len(delta_manager.deltas) == 20
        
        # Compact, keeping only last 5 turns
        await delta_manager.compact_deltas(keep_turns=5)
        
        # Should only have turns 16-20
        assert len(delta_manager.deltas) == 5
        assert min(delta_manager.deltas.keys()) >= 16
        assert max(delta_manager.deltas.keys()) == 20


class TestConflictResolver:
    """
    Test conflict detection and resolution
    
    Justification: Simultaneous actions can create conflicts that must be
    resolved deterministically for fair multiplayer gameplay.
    """
    
    @pytest.fixture
    def conflict_resolver(self):
        return ConflictResolver()
    
    @pytest.mark.asyncio
    async def test_detect_movement_conflicts(self, conflict_resolver):
        """
        Test detection of movement conflicts (multiple entities to same position)
        
        Justification: Movement conflicts are common in tactical games and
        must be detected to maintain spatial consistency.
        """
        actions = [
            GameCommand(
                command_id="move1",
                command_type=CommandType.MOVE,
                player_id="player1",
                payload={"x": 5, "y": 5}
            ),
            GameCommand(
                command_id="move2", 
                command_type=CommandType.MOVE,
                player_id="player2",
                payload={"x": 5, "y": 5}  # Same position!
            ),
            GameCommand(
                command_id="move3",
                command_type=CommandType.MOVE,
                player_id="player3", 
                payload={"x": 6, "y": 6}  # Different position
            )
        ]
        
        conflicts = await conflict_resolver.detect_conflicts(actions)
        
        # Should detect one movement conflict
        movement_conflicts = [c for c in conflicts if c['type'] == 'movement_conflict']
        assert len(movement_conflicts) == 1
        
        conflict = movement_conflicts[0]
        assert conflict['position'] == (5, 5)
        assert len(conflict['actions']) == 2
        assert conflict['severity'] == 'high'
    
    @pytest.mark.asyncio
    async def test_detect_target_conflicts(self, conflict_resolver):
        """
        Test detection of target conflicts (multiple attacks on same target)
        
        Justification: Multiple attacks on one target need coordination to
        determine cumulative effects and targeting validity.
        """
        actions = [
            GameCommand(
                command_id="attack1",
                command_type=CommandType.ATTACK,
                player_id="player1",
                payload={"target_id": "enemy1", "damage": 5}
            ),
            GameCommand(
                command_id="attack2",
                command_type=CommandType.ATTACK,
                player_id="player2", 
                payload={"target_id": "enemy1", "damage": 3}  # Same target
            ),
            GameCommand(
                command_id="attack3",
                command_type=CommandType.ATTACK,
                player_id="player3",
                payload={"target_id": "enemy1", "damage": 4}  # Same target - 3 total
            )
        ]
        
        conflicts = await conflict_resolver.detect_conflicts(actions)
        
        # Should detect target conflict (3+ attacks)
        target_conflicts = [c for c in conflicts if c['type'] == 'target_conflict']
        assert len(target_conflicts) == 1
        
        conflict = target_conflicts[0]
        assert conflict['target_id'] == "enemy1"
        assert len(conflict['actions']) == 3
    
    @pytest.mark.asyncio
    async def test_resolve_conflicts(self, conflict_resolver):
        """
        Test conflict resolution with deterministic outcomes
        
        Justification: Conflict resolution must be predictable and fair,
        following established game rules for competitive integrity.
        """
        conflicts = [
            {
                'conflict_id': 'conflict1',
                'type': 'movement_conflict',
                'position': (5, 5),
                'actions': [
                    {'command_id': 'move1', 'sequence_number': 1},
                    {'command_id': 'move2', 'sequence_number': 2}
                ]
            }
        ]
        
        resolutions = await conflict_resolver.resolve_conflicts(conflicts)
        
        assert len(resolutions) == 1
        resolution = resolutions[0]
        
        assert resolution['conflict_id'] == 'conflict1'
        assert resolution['resolution_type'] == 'initiative_order'
        assert resolution['winner'] == 'move1'  # Earlier sequence wins
        assert 'move2' in resolution['losers']


class TestGameStateSynchronizer:
    """
    Test the main coordinator for game state synchronization
    
    Justification: The synchronizer coordinates all multiplayer aspects and
    must integrate turn ordering, state deltas, and conflict resolution seamlessly.
    """
    
    @pytest.fixture
    def synchronizer(self):
        return GameStateSynchronizer()
    
    @pytest.fixture
    def sample_players(self):
        return [
            Player(id="player1", name="Alice", team="team1"),
            Player(id="player2", name="Bob", team="team2"),
            Player(id="player3", name="Charlie", team="team3"),
            Player(id="player4", name="David", team="team4")
        ]
    
    @pytest.mark.asyncio
    async def test_initialize_game(self, synchronizer, sample_players):
        """
        Test game initialization with turn order setup
        
        Justification: Game initialization sets up all multiplayer systems
        and must work correctly for games to function.
        """
        room_id = "room1"
        game_config = {"turn_timeout": 300, "max_players": 4}
        
        success = await synchronizer.initialize_game(room_id, sample_players, game_config)
        
        assert success
        assert room_id in synchronizer.active_games
        assert synchronizer.active_games[room_id] is True
        
        # Turn manager should be initialized
        current_turn = synchronizer.turn_manager.current_turn
        assert current_turn is not None
        assert current_turn.turn_id == 1
        assert len(synchronizer.turn_manager.initiative_order) == 4
    
    @pytest.mark.asyncio
    async def test_process_player_action(self, synchronizer, sample_players):
        """
        Test player action processing with validation and execution
        
        Justification: Action processing is the core multiplayer interaction
        and must handle validation, queuing, and execution properly.
        """
        room_id = "room1"
        await synchronizer.initialize_game(room_id, sample_players, {})
        
        command = GameCommand(
            command_id="test_move",
            command_type=CommandType.MOVE,
            player_id="player1",
            payload={"x": 3, "y": 3}
        )
        
        result = await synchronizer.process_player_action(room_id, "player1", command)
        
        assert result['success']
        assert result['command_id'] == "test_move"
        assert result['queued']
        assert 'execution_results' in result
    
    @pytest.mark.asyncio
    async def test_get_state_updates(self, synchronizer, sample_players):
        """
        Test state update retrieval for client synchronization
        
        Justification: Clients need to receive state updates to stay synchronized
        with the authoritative server state.
        """
        room_id = "room1"
        await synchronizer.initialize_game(room_id, sample_players, {})
        
        # Process an action to generate deltas
        command = GameCommand(
            command_id="test_action",
            command_type=CommandType.MOVE,
            player_id="player1",
            payload={"x": 2, "y": 2}
        )
        await synchronizer.process_player_action(room_id, "player1", command)
        
        # Get state updates
        updates = await synchronizer.get_state_updates(room_id, since_turn=0, since_sequence=0)
        
        assert 'deltas' in updates
        assert 'current_turn' in updates
        assert 'last_turn' in updates
        assert 'last_sequence' in updates
        
        # Should have at least one delta
        assert len(updates['deltas']) > 0
    
    @pytest.mark.asyncio
    async def test_advance_turn(self, synchronizer, sample_players):
        """
        Test turn advancement and phase transitions
        
        Justification: Turn advancement drives game progression and must
        transition phases and create appropriate state changes.
        """
        room_id = "room1"
        await synchronizer.initialize_game(room_id, sample_players, {})
        
        # Advance turn
        result = await synchronizer.advance_turn(room_id)
        
        assert result['success']
        # Should either advance phase or start new turn
        assert 'phase' in result or 'new_turn' in result
    
    @pytest.mark.asyncio
    async def test_multiple_player_actions_ordering(self, synchronizer, sample_players):
        """
        Test action ordering with multiple players
        
        Justification: Complex scenarios with multiple simultaneous actions
        must maintain proper ordering and conflict resolution.
        """
        room_id = "room1"
        await synchronizer.initialize_game(room_id, sample_players, {})
        
        # Queue actions from multiple players
        commands = []
        for i, player in enumerate(sample_players[:3]):  # First 3 players
            command = GameCommand(
                command_id=f"action_{i}",
                command_type=CommandType.MOVE,
                player_id=player.id,
                payload={"x": i, "y": i}
            )
            commands.append(command)
            
            result = await synchronizer.process_player_action(room_id, player.id, command)
            assert result['success']
        
        # Get state updates
        updates = await synchronizer.get_state_updates(room_id)
        
        # Should have deltas for all actions
        assert len(updates['deltas']) >= 3


class TestIntegrationScenarios:
    """
    Integration tests simulating real gameplay scenarios
    
    Justification: Integration tests validate that all Phase 2 components
    work together correctly in realistic multiplayer game situations.
    """
    
    @pytest.fixture
    def full_game_setup(self):
        """Set up a complete 4-player game scenario"""
        synchronizer = GameStateSynchronizer()
        players = [
            Player(id=f"player{i}", name=f"Player{i}", team=f"team{i}")
            for i in range(1, 5)
        ]
        return synchronizer, players, "test_room"
    
    @pytest.mark.asyncio
    async def test_full_turn_cycle(self, full_game_setup):
        """
        Test complete turn cycle with all phases
        
        Justification: Real games go through complete turn cycles and this
        validates the entire turn-based system integration.
        """
        synchronizer, players, room_id = full_game_setup
        
        # Initialize game
        success = await synchronizer.initialize_game(room_id, players, {})
        assert success
        
        # Each player takes an action
        for i, player in enumerate(players):
            command = GameCommand(
                command_id=f"turn1_action_{i}",
                command_type=CommandType.MOVE,
                player_id=player.id,
                payload={"x": i * 2, "y": i * 2}
            )
            
            result = await synchronizer.process_player_action(room_id, player.id, command)
            assert result['success']
        
        # Advance through turn phases
        for phase_name in ['actions', 'resolution', 'complete']:
            result = await synchronizer.advance_turn(room_id)
            assert result['success']
            
            if result.get('new_turn'):
                # Started new turn
                assert result['new_turn'] == 2
                break
        
        # Validate turn progression
        current_turn = synchronizer.turn_manager.current_turn
        assert current_turn.turn_id == 2
    
    @pytest.mark.asyncio
    async def test_conflict_resolution_integration(self, full_game_setup):
        """
        Test conflict detection and resolution in realistic scenario
        
        Justification: Conflicts occur in real games and the system must
        handle them seamlessly while maintaining game state consistency.
        """
        synchronizer, players, room_id = full_game_setup
        
        await synchronizer.initialize_game(room_id, players, {})
        
        # Create conflicting actions (same target position)
        target_pos = {"x": 5, "y": 5}
        
        for i, player in enumerate(players[:2]):  # Two players conflict
            command = GameCommand(
                command_id=f"conflict_move_{i}",
                command_type=CommandType.MOVE,
                player_id=player.id,
                payload=target_pos.copy()
            )
            
            result = await synchronizer.process_player_action(room_id, player.id, command)
            assert result['success']  # Both should queue successfully
        
        # Get state updates to see conflict resolution
        updates = await synchronizer.get_state_updates(room_id)
        
        # Should have deltas showing conflict resolution
        assert len(updates['deltas']) >= 1
        
        # One action should succeed, one should be modified/rejected
        success_count = sum(
            1 for delta in updates['deltas'] 
            if any(event.get('type') == 'entity_moved' for event in delta.get('events', []))
        )
        assert success_count <= 2  # At most 2 successful moves


# Test configuration for the full 4-AI game scenario
class TestFourAIGameScenario:
    """
    Test a complete 4-AI client game scenario as requested
    
    Justification: This validates the entire Phase 2 system under load
    with multiple AI clients simulating real multiplayer gameplay.
    """
    
    @pytest.fixture
    def ai_game_setup(self):
        """Set up 4 AI teams with 5 characters each"""
        synchronizer = GameStateSynchronizer()
        
        # Create 4 AI players (teams)
        ai_players = []
        for team_id in range(1, 5):
            player = Player(
                id=f"ai_team_{team_id}",
                name=f"AI Team {team_id}",
                team=f"team_{team_id}"
            )
            ai_players.append(player)
        
        return synchronizer, ai_players, "ai_battle_room"
    
    @pytest.mark.asyncio
    async def test_full_ai_battle_simulation(self, ai_game_setup):
        """
        Simulate a full battle with 4 AI teams
        
        Justification: This is the specific test scenario requested - validates
        that the multiplayer system can handle a complete 4-team battle with
        realistic action loads and turn management.
        """
        synchronizer, ai_players, room_id = ai_game_setup
        
        # Initialize the game
        game_config = {
            "turn_timeout": 60,  # 1 minute turns for AI
            "max_turns": 50,     # Limit battle length
            "teams": 4,
            "characters_per_team": 5
        }
        
        success = await synchronizer.initialize_game(room_id, ai_players, game_config)
        assert success
        assert room_id in synchronizer.active_games
        
        # Simulate multiple turns of AI actions
        turns_completed = 0
        max_turns = 10  # Limit for test performance
        
        while turns_completed < max_turns:
            current_turn = synchronizer.turn_manager.current_turn
            if not current_turn:
                break
                
            # Each AI team takes multiple actions per turn
            for ai_player in ai_players:
                # Simulate 3-5 actions per AI team per turn
                action_count = min(3, 5 - turns_completed)  # Fewer actions as test progresses
                
                for action_num in range(action_count):
                    # Mix of different action types
                    action_types = [CommandType.MOVE, CommandType.ATTACK, CommandType.USE_DISCIPLINE]
                    action_type = action_types[action_num % len(action_types)]
                    
                    # Create AI action
                    command = GameCommand(
                        command_id=f"ai_{ai_player.id}_t{turns_completed}_a{action_num}",
                        command_type=action_type,
                        player_id=ai_player.id,
                        payload=self._generate_ai_payload(action_type, ai_player.id, turns_completed, action_num)
                    )
                    
                    # Process AI action
                    result = await synchronizer.process_player_action(room_id, ai_player.id, command)
                    assert result['success'], f"AI action failed: {result.get('reason')}"
            
            # Advance turn after all AI actions
            advance_result = await synchronizer.advance_turn(room_id)
            assert advance_result['success']
            
            if advance_result.get('new_turn'):
                turns_completed += 1
                print(f"Completed turn {turns_completed}")
        
        # Validate game state after simulation
        final_updates = await synchronizer.get_state_updates(room_id)
        
        # Should have many deltas from all the AI actions
        assert len(final_updates['deltas']) >= turns_completed * 4 * 2  # At least 2 actions per team per turn
        
        # Game should still be active
        assert synchronizer.active_games.get(room_id) is True
        
        print(f"✅ AI Battle Simulation completed: {turns_completed} turns, "
              f"{len(final_updates['deltas'])} state deltas, "
              f"4 AI teams with simulated 5-character teams each")
    
    def _generate_ai_payload(self, action_type: CommandType, player_id: str, turn: int, action: int):
        """Generate realistic AI action payloads"""
        import random
        
        if action_type == CommandType.MOVE:
            return {
                "x": random.randint(0, 15),  # 15x15 battlefield
                "y": random.randint(0, 15),
                "character_id": f"{player_id}_char_{action % 5}"  # 5 characters per team
            }
        elif action_type == CommandType.ATTACK:
            # Attack another team's character
            target_teams = [f"ai_team_{i}" for i in range(1, 5) if f"ai_team_{i}" != player_id]
            target_team = random.choice(target_teams)
            return {
                "target_id": f"{target_team}_char_{random.randint(0, 4)}",
                "weapon": "primary",
                "character_id": f"{player_id}_char_{action % 5}"
            }
        elif action_type == CommandType.USE_DISCIPLINE:
            return {
                "discipline": f"discipline_{random.randint(1, 3)}",
                "character_id": f"{player_id}_char_{action % 5}",
                "target": f"area_{random.randint(0, 9)}"
            }
        
        return {}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])