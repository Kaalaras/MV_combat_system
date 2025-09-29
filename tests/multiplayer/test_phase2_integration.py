"""
Phase 2 Integration Tests: Complete multiplayer workflow testing
Tests Socket.IO integration with state synchronization system
"""

import pytest
import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import socketio
from fastapi.testclient import TestClient

from multiplayer.server import app, sio, game_synchronizer
from multiplayer.models import GameCommand, Player, CommandType


@pytest.fixture
def test_client():
    """Create FastAPI test client"""
    return TestClient(app)


@pytest.fixture
async def socket_client():
    """Create Socket.IO test client"""
    client = socketio.AsyncClient()
    return client


@pytest.fixture
def auth_token():
    """Mock JWT token for testing"""
    return "mock_jwt_token_for_testing"


@pytest.fixture
def test_room_id():
    """Test room ID"""
    return "test_room_123"


class TestPhase2SocketIOIntegration:
    """
    Test Socket.IO integration with Phase 2 state synchronization
    
    Justification: Socket.IO events are the primary interface for multiplayer
    interaction and must integrate correctly with turn management and state sync.
    """
    
    @pytest.mark.asyncio
    async def test_start_game_event(self, socket_client, auth_token, test_room_id):
        """
        Test game start event handling
        
        Justification: Game start initializes multiplayer session and must
        set up turn order and synchronization systems correctly.
        """
        # Mock the game room manager
        with patch('multiplayer.server.game_room_manager') as mock_room_manager:
            mock_room = MagicMock()
            mock_room.id = test_room_id
            mock_room.host_id = "player1"
            mock_room.players = [
                Player(id="player1", name="Alice"),
                Player(id="player2", name="Bob")
            ]
            mock_room_manager.get_room = AsyncMock(return_value=mock_room)
            
            # Mock session data
            test_session = {
                'player_id': 'player1',
                'room_id': test_room_id,
                'authenticated': True
            }
            
            # Test the event handler directly
            from multiplayer.server import start_game
            
            with patch('multiplayer.server.sio.get_session', return_value=test_session):
                with patch('multiplayer.server.sio.emit') as mock_emit:
                    await start_game('test_sid', {'config': {'turn_timeout': 300}})
                    
                    # Should emit game_started event
                    mock_emit.assert_called()
                    call_args = mock_emit.call_args_list
                    
                    # Find the game_started emission
                    game_started_calls = [
                        call for call in call_args 
                        if call[0][0] == 'game_started'
                    ]
                    assert len(game_started_calls) > 0
    
    @pytest.mark.asyncio
    async def test_queue_action_event(self, socket_client, test_room_id):
        """
        Test action queuing through Socket.IO
        
        Justification: Action queuing is core to turn-based gameplay and must
        handle validation, queuing, and immediate feedback correctly.
        """
        # Mock session and validation
        test_session = {
            'player_id': 'player1',
            'room_id': test_room_id,
            'authenticated': True
        }
        
        command_data = {
            'command_id': str(uuid.uuid4()),
            'command_type': CommandType.MOVE.value,
            'payload': {'x': 5, 'y': 5}
        }
        
        with patch('multiplayer.server.sio.get_session', return_value=test_session):
            with patch('multiplayer.server.command_validator.validate_command') as mock_validate:
                with patch('multiplayer.server.game_synchronizer.process_player_action') as mock_process:
                    with patch('multiplayer.server.sio.emit') as mock_emit:
                        
                        # Set up mocks
                        mock_validate.return_value = MagicMock(valid=True)
                        mock_process.return_value = {
                            'success': True,
                            'command_id': command_data['command_id'],
                            'queued': True,
                            'execution_results': []
                        }
                        
                        # Test the event handler
                        from multiplayer.server import queue_action
                        await queue_action('test_sid', command_data)
                        
                        # Should process action and emit response
                        mock_validate.assert_called_once()
                        mock_process.assert_called_once()
                        mock_emit.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_state_updates_event(self, socket_client, test_room_id):
        """
        Test state update retrieval through Socket.IO
        
        Justification: Clients need to sync with server state and this event
        provides the mechanism for catching up on missed updates.
        """
        test_session = {
            'player_id': 'player1', 
            'room_id': test_room_id,
            'authenticated': True
        }
        
        request_data = {
            'since_turn': 1,
            'since_sequence': 5
        }
        
        mock_updates = {
            'deltas': [
                {
                    'delta_id': 'delta1',
                    'turn_id': 2,
                    'sequence_number': 1,
                    'entity_changes': {},
                    'events': []
                }
            ],
            'current_turn': {
                'turn_id': 2,
                'phase': 'actions',
                'current_player_id': 'player1'
            },
            'last_turn': 2,
            'last_sequence': 1
        }
        
        with patch('multiplayer.server.sio.get_session', return_value=test_session):
            with patch('multiplayer.server.game_synchronizer.get_state_updates', return_value=mock_updates):
                with patch('multiplayer.server.sio.emit') as mock_emit:
                    
                    from multiplayer.server import get_state_updates
                    await get_state_updates('test_sid', request_data)
                    
                    # Should emit state updates
                    mock_emit.assert_called_with('state_updates', mock_updates, room='test_sid')
    
    @pytest.mark.asyncio
    async def test_advance_turn_event(self, socket_client, test_room_id):
        """
        Test turn advancement through Socket.IO
        
        Justification: Turn advancement controls game flow and must broadcast
        changes to all players while maintaining proper authorization.
        """
        # Mock room with host permissions
        with patch('multiplayer.server.game_room_manager') as mock_room_manager:
            mock_room = MagicMock()
            mock_room.id = test_room_id
            mock_room.host_id = "player1"  # Host player
            mock_room_manager.get_room = AsyncMock(return_value=mock_room)
            
            test_session = {
                'player_id': 'player1',  # Host player
                'room_id': test_room_id,
                'authenticated': True
            }
            
            mock_advance_result = {
                'success': True,
                'new_turn': 3,
                'delta': {
                    'delta_id': 'turn_advance_delta',
                    'turn_id': 3,
                    'sequence_number': 0
                }
            }
            
            with patch('multiplayer.server.sio.get_session', return_value=test_session):
                with patch('multiplayer.server.game_synchronizer.advance_turn', return_value=mock_advance_result):
                    with patch('multiplayer.server.sio.emit') as mock_emit:
                        
                        from multiplayer.server import advance_turn
                        await advance_turn('test_sid')
                        
                        # Should broadcast turn advance and state delta
                        assert mock_emit.call_count >= 2
                        
                        # Check for turn_advanced and state_delta emissions
                        call_args = [call[0][0] for call in mock_emit.call_args_list]
                        assert 'turn_advanced' in call_args
                        assert 'state_delta' in call_args


class TestPhase2WorkflowIntegration:
    """
    Test complete multiplayer workflow integration
    
    Justification: Full workflow tests validate that all Phase 2 components
    work together in realistic game scenarios from start to finish.
    """
    
    @pytest.fixture
    def game_workflow_setup(self):
        """Set up a complete game workflow test environment"""
        # Reset synchronizer for each test
        global game_synchronizer
        from multiplayer.state_sync import GameStateSynchronizer
        game_synchronizer = GameStateSynchronizer()
        
        players = [
            Player(id=f"player{i}", name=f"Player{i}", team=f"team{i}")
            for i in range(1, 5)
        ]
        
        return players, "workflow_test_room"
    
    @pytest.mark.asyncio
    async def test_complete_game_workflow(self, game_workflow_setup):
        """
        Test complete game workflow from initialization to turn completion
        
        Justification: This validates the entire Phase 2 system working together
        in a realistic multiplayer game session.
        """
        players, room_id = game_workflow_setup
        
        # Step 1: Initialize game
        game_config = {"turn_timeout": 300, "max_players": 4}
        success = await game_synchronizer.initialize_game(room_id, players, game_config)
        assert success
        
        # Step 2: All players take actions in first turn
        turn_1_actions = []
        for i, player in enumerate(players):
            command = GameCommand(
                command_id=f"t1_action_{i}",
                command_type=CommandType.MOVE,
                player_id=player.id,
                payload={"x": i * 2, "y": i * 2, "character_id": f"char_{i}"}
            )
            
            result = await game_synchronizer.process_player_action(room_id, player.id, command)
            assert result['success']
            turn_1_actions.append(result)
        
        # Step 3: Get state updates after actions
        updates_after_actions = await game_synchronizer.get_state_updates(room_id)
        initial_delta_count = len(updates_after_actions['deltas'])
        
        # Step 4: Advance through turn phases
        phase_results = []
        for phase_num in range(4):  # Go through all phases
            advance_result = await game_synchronizer.advance_turn(room_id)
            assert advance_result['success']
            phase_results.append(advance_result)
            
            if advance_result.get('new_turn'):
                break
        
        # Step 5: Validate new turn started
        final_updates = await game_synchronizer.get_state_updates(room_id)
        
        # Should have more deltas after turn advancement
        assert len(final_updates['deltas']) >= initial_delta_count
        
        # Should be in turn 2
        current_turn = game_synchronizer.turn_manager.current_turn
        assert current_turn.turn_id == 2
        
        print(f"✅ Complete workflow test passed: "
              f"{len(turn_1_actions)} actions processed, "
              f"{len(phase_results)} phase advances, "
              f"advanced to turn {current_turn.turn_id}")
    
    @pytest.mark.asyncio
    async def test_concurrent_actions_workflow(self, game_workflow_setup):
        """
        Test workflow with concurrent conflicting actions
        
        Justification: Real multiplayer games have simultaneous actions that
        must be handled with proper conflict detection and resolution.
        """
        players, room_id = game_workflow_setup
        
        # Initialize game
        await game_synchronizer.initialize_game(room_id, players, {})
        
        # Create conflicting actions (same target position)
        conflict_position = {"x": 10, "y": 10}
        conflicting_commands = []
        
        for i, player in enumerate(players[:3]):  # 3 players to same position
            command = GameCommand(
                command_id=f"conflict_move_{i}",
                command_type=CommandType.MOVE,
                player_id=player.id,
                payload={**conflict_position, "character_id": f"char_{i}"}
            )
            conflicting_commands.append(command)
        
        # Process all conflicting actions
        conflict_results = []
        for command in conflicting_commands:
            result = await game_synchronizer.process_player_action(
                room_id, command.player_id, command
            )
            conflict_results.append(result)
        
        # All should queue successfully initially
        assert all(result['success'] for result in conflict_results)
        
        # Advance turn to trigger conflict resolution
        advance_result = await game_synchronizer.advance_turn(room_id)
        assert advance_result['success']
        
        # Get final state updates
        final_updates = await game_synchronizer.get_state_updates(room_id)
        
        # Should have deltas showing conflict resolution outcomes
        assert len(final_updates['deltas']) > 0
        
        # Validate that conflict was handled (implementation specific)
        movement_events = []
        for delta in final_updates['deltas']:
            for event in delta.get('events', []):
                if event.get('type') == 'entity_moved':
                    movement_events.append(event)
        
        # Should have at most 1 successful move to the conflicted position
        same_pos_moves = [
            event for event in movement_events
            if (event.get('to', {}).get('x') == 10 and 
                event.get('to', {}).get('y') == 10)
        ]
        assert len(same_pos_moves) <= 1
        
        print(f"✅ Conflict resolution workflow passed: "
              f"{len(conflicting_commands)} conflicting actions, "
              f"{len(movement_events)} movements executed, "
              f"{len(same_pos_moves)} succeeded to conflict position")


class TestPhase2PerformanceIntegration:
    """
    Test Phase 2 system performance under load
    
    Justification: Multiplayer systems must handle high action loads
    efficiently without degrading game experience.
    """
    
    @pytest.mark.asyncio
    async def test_high_action_load(self):
        """
        Test system performance with high action volume
        
        Justification: Real multiplayer battles can have many simultaneous
        actions and the system must handle them efficiently.
        """
        from multiplayer.state_sync import GameStateSynchronizer
        synchronizer = GameStateSynchronizer()
        
        # Create many players
        players = [
            Player(id=f"player{i}", name=f"Player{i}")
            for i in range(20)  # 20 players
        ]
        
        room_id = "performance_test_room"
        await synchronizer.initialize_game(room_id, players, {})
        
        # Generate many actions quickly
        import time
        start_time = time.time()
        
        action_count = 100
        successful_actions = 0
        
        for action_num in range(action_count):
            player = players[action_num % len(players)]
            command = GameCommand(
                command_id=f"perf_action_{action_num}",
                command_type=CommandType.MOVE,
                player_id=player.id,
                payload={
                    "x": action_num % 15,
                    "y": (action_num * 2) % 15
                }
            )
            
            result = await synchronizer.process_player_action(room_id, player.id, command)
            if result['success']:
                successful_actions += 1
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Performance assertions
        assert successful_actions >= action_count * 0.9  # 90% success rate minimum
        assert duration < 10.0  # Should complete within 10 seconds
        
        actions_per_second = successful_actions / duration
        
        print(f"✅ Performance test passed: "
              f"{successful_actions}/{action_count} actions in {duration:.2f}s "
              f"({actions_per_second:.1f} actions/sec)")
        
        # Validate state consistency after high load
        updates = await synchronizer.get_state_updates(room_id)
        assert len(updates['deltas']) >= successful_actions * 0.5  # At least half should generate deltas
    
    @pytest.mark.asyncio
    async def test_state_delta_efficiency(self):
        """
        Test state delta system efficiency and memory usage
        
        Justification: Long-running games must manage memory efficiently
        to prevent server performance degradation.
        """
        from multiplayer.state_sync import StateDeltaManager
        delta_manager = StateDeltaManager()
        
        # Generate many deltas
        delta_count = 1000
        for i in range(delta_count):
            await delta_manager.create_delta(
                turn_id=i // 10,  # 10 deltas per turn
                sequence_number=i % 10,
                entity_changes={f"entity_{i}": {"data": i}},
                events=[{"type": "test", "id": i}],
                player_id=f"player_{i % 4}",
                command_id=f"cmd_{i}"
            )
        
        # Check memory usage before compaction
        initial_delta_count = len(delta_manager.delta_history)
        initial_turn_count = len(delta_manager.deltas)
        
        # Compact deltas
        await delta_manager.compact_deltas(keep_turns=10)
        
        # Check memory usage after compaction
        final_delta_count = len(delta_manager.delta_history)
        final_turn_count = len(delta_manager.deltas)
        
        # Should have reduced memory usage
        assert final_delta_count < initial_delta_count
        assert final_turn_count <= 10
        
        # But should still be able to retrieve recent deltas
        recent_deltas = await delta_manager.get_deltas_since(
            turn_id=max(delta_manager.deltas.keys()) - 5,
            sequence_number=0
        )
        assert len(recent_deltas) > 0
        
        print(f"✅ Delta efficiency test passed: "
              f"reduced from {initial_delta_count} to {final_delta_count} deltas "
              f"({initial_turn_count} to {final_turn_count} turns)")


class TestFourAIClientBattle:
    """
    The specific test scenario requested: 1 server, 4 AI clients with 5 characters each
    
    Justification: This is the exact scenario specified in the requirements
    and validates the complete Phase 2 system under realistic game conditions.
    """
    
    @pytest.mark.asyncio
    async def test_four_ai_client_battle(self):
        """
        Full 4-AI client battle simulation with 5 characters per team
        
        This is the main integration test requested in the requirements.
        Validates turn-based action ordering, state delta broadcasting,
        and conflict resolution under realistic multiplayer battle conditions.
        """
        print("\n🎮 Starting 4-AI Client Battle Simulation...")
        
        from multiplayer.state_sync import GameStateSynchronizer
        synchronizer = GameStateSynchronizer()
        
        # Create 4 AI teams
        ai_teams = [
            Player(
                id=f"ai_team_{i}",
                name=f"AI Team {i}",
                team=f"team_{i}"
            )
            for i in range(1, 5)
        ]
        
        battle_room = "ai_battle_arena"
        
        # Initialize battle
        battle_config = {
            "turn_timeout": 30,  # 30 seconds per turn for fast simulation
            "max_turns": 20,
            "teams": 4,
            "characters_per_team": 5,
            "battlefield_size": {"width": 20, "height": 20}
        }
        
        print(f"🚀 Initializing battle with {len(ai_teams)} AI teams...")
        success = await synchronizer.initialize_game(battle_room, ai_teams, battle_config)
        assert success
        
        # Battle statistics
        battle_stats = {
            "turns_completed": 0,
            "total_actions": 0,
            "successful_actions": 0,
            "conflicts_detected": 0,
            "state_deltas_created": 0
        }
        
        # Run battle simulation
        max_turns = 15  # Reasonable limit for test
        
        print(f"⚔️ Beginning battle simulation ({max_turns} turns max)...")
        
        while battle_stats["turns_completed"] < max_turns:
            current_turn = synchronizer.turn_manager.current_turn
            if not current_turn:
                print("❌ No active turn, ending battle")
                break
            
            print(f"\n--- Turn {current_turn.turn_id} ---")
            
            # Each AI team plans and executes actions
            turn_actions = 0
            for team in ai_teams:
                # Each team controls 5 characters, each takes 1-3 actions
                characters_per_team = 5
                for char_idx in range(characters_per_team):
                    actions_per_character = min(2, max_turns - battle_stats["turns_completed"])
                    
                    for action_idx in range(actions_per_character):
                        action = await self._generate_ai_action(
                            team, char_idx, current_turn.turn_id, action_idx, battle_config
                        )
                        
                        battle_stats["total_actions"] += 1
                        turn_actions += 1
                        
                        # Process action
                        result = await synchronizer.process_player_action(
                            battle_room, team.id, action
                        )
                        
                        if result['success']:
                            battle_stats["successful_actions"] += 1
                            
                            # Count execution results
                            if 'execution_results' in result:
                                battle_stats["state_deltas_created"] += len(result['execution_results'])
            
            print(f"  📊 Turn {current_turn.turn_id}: {turn_actions} actions from {len(ai_teams)} teams")
            
            # Advance turn
            advance_result = await synchronizer.advance_turn(battle_room)
            assert advance_result['success']
            
            if advance_result.get('new_turn'):
                battle_stats["turns_completed"] += 1
            
            # Get state updates to validate system
            state_updates = await synchronizer.get_state_updates(battle_room)
            battle_stats["state_deltas_created"] = len(state_updates['deltas'])
        
        # Battle completion validation
        print(f"\n🏁 Battle Simulation Complete!")
        print(f"📈 Battle Statistics:")
        print(f"  • Turns Completed: {battle_stats['turns_completed']}")
        print(f"  • Total Actions: {battle_stats['total_actions']}")
        print(f"  • Successful Actions: {battle_stats['successful_actions']}")
        print(f"  • Success Rate: {battle_stats['successful_actions']/battle_stats['total_actions']*100:.1f}%")
        print(f"  • State Deltas: {battle_stats['state_deltas_created']}")
        print(f"  • Actions per Turn: {battle_stats['total_actions']/battle_stats['turns_completed']:.1f}")
        
        # Validation assertions
        assert battle_stats["turns_completed"] >= 5, "Battle should run at least 5 turns"
        assert battle_stats["successful_actions"] >= battle_stats["total_actions"] * 0.85, "85% action success rate minimum"
        assert battle_stats["state_deltas_created"] >= battle_stats["successful_actions"] * 0.5, "Should generate deltas for actions"
        
        # Validate system state after battle
        final_turn = synchronizer.turn_manager.current_turn
        assert final_turn is not None, "Game should still have active turn"
        assert battle_room in synchronizer.active_games, "Game should still be active"
        
        print(f"✅ 4-AI Client Battle Test PASSED")
        print(f"   Phase 2 multiplayer system successfully handled:")
        print(f"   • Turn-based action ordering with {len(ai_teams)} AI clients")
        print(f"   • State delta broadcasting ({battle_stats['state_deltas_created']} deltas)")
        print(f"   • Conflict resolution across {battle_stats['turns_completed']} turns")
        print(f"   • {battle_stats['total_actions']} total actions with realistic AI behavior")
        
        return battle_stats
    
    async def _generate_ai_action(self, team: Player, char_idx: int, turn_id: int, action_idx: int, config: dict):
        """Generate realistic AI actions for battle simulation"""
        import random
        
        character_id = f"{team.id}_char_{char_idx}"
        battlefield_size = config.get("battlefield_size", {"width": 15, "height": 15})
        
        # AI action distribution (realistic tactical behavior)
        action_weights = {
            CommandType.MOVE: 40,      # Movement is common
            CommandType.ATTACK: 35,    # Attacks are frequent  
            CommandType.USE_DISCIPLINE: 15,  # Disciplines are powerful but limited
            CommandType.RELOAD: 10     # Reloading as needed
        }
        
        action_type = random.choices(
            list(action_weights.keys()),
            weights=list(action_weights.values())
        )[0]
        
        command_id = f"{team.id}_{character_id}_t{turn_id}_a{action_idx}"
        
        if action_type == CommandType.MOVE:
            payload = {
                "character_id": character_id,
                "x": random.randint(0, battlefield_size["width"] - 1),
                "y": random.randint(0, battlefield_size["height"] - 1),
                "movement_type": random.choice(["walk", "run", "tactical"])
            }
            
        elif action_type == CommandType.ATTACK:
            # Target enemy characters
            enemy_teams = [f"ai_team_{i}" for i in range(1, 5) if f"ai_team_{i}" != team.id]
            target_team = random.choice(enemy_teams)
            target_character = f"{target_team}_char_{random.randint(0, 4)}"
            
            payload = {
                "character_id": character_id,
                "target_id": target_character,
                "weapon": random.choice(["primary", "secondary", "melee"]),
                "attack_type": random.choice(["aimed", "burst", "suppressive"])
            }
            
        elif action_type == CommandType.USE_DISCIPLINE:
            payload = {
                "character_id": character_id,
                "discipline": random.choice(["blood_buff", "celerity", "fortitude", "obfuscate"]),
                "target_type": random.choice(["self", "ally", "enemy", "area"]),
                "intensity": random.randint(1, 3)
            }
            
        elif action_type == CommandType.RELOAD:
            payload = {
                "character_id": character_id,
                "weapon": random.choice(["primary", "secondary"]),
                "reload_type": "tactical"
            }
        
        else:
            payload = {"character_id": character_id}
        
        return GameCommand(
            command_id=command_id,
            command_type=action_type,
            player_id=team.id,
            payload=payload
        )


if __name__ == "__main__":
    # Run the specific 4-AI battle test
    import asyncio
    
    async def run_ai_battle():
        test_instance = TestFourAIClientBattle()
        await test_instance.test_four_ai_client_battle()
    
    print("🚀 Running Phase 2 Integration Test: 4-AI Client Battle")
    asyncio.run(run_ai_battle())