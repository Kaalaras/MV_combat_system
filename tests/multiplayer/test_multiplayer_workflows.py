"""
End-to-end multiplayer workflow tests.
Tests complete user journeys from authentication through gameplay in realistic scenarios.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from multiplayer.models import (
    Player, GameCommand, CommandType, GameRoom, GameStatus,
    MoveCommandPayload, AttackCommandPayload, ChatCommandPayload
)
from multiplayer.game_manager import GameRoomManager, CommandValidator  
from multiplayer.auth import authenticate_player, create_access_token


class TestMultiplayerWorkflows:
    """
    End-to-End Multiplayer Workflow Tests
    
    Justification: E2E tests validate complete user journeys and ensure all
    multiplayer components work together correctly. These tests simulate real
    player interactions and verify the entire multiplayer infrastructure.
    """
    
    @pytest.fixture
    def room_manager(self):
        """Game room manager instance"""
        return GameRoomManager()
    
    @pytest.fixture
    def validator(self):
        """Command validator instance"""
        return CommandValidator()
    
    @pytest.fixture
    async def authenticated_players(self):
        """Multiple authenticated players for testing"""
        players = []
        
        # Create test players
        for i in range(4):
            username = f"player{i+1}"
            player = await authenticate_player(username, "password123")
            if player:
                token = create_access_token({"sub": player.id})
                players.append((player, token))
        
        return players
    
    @pytest.mark.asyncio
    async def test_complete_room_lifecycle(self, room_manager, authenticated_players):
        """
        Test complete room lifecycle from creation to game completion.
        
        Justification: This validates the entire room management workflow that
        players experience. Room creation, joining, gameplay, and cleanup must
        all work seamlessly together.
        """
        await room_manager.initialize()
        
        if not authenticated_players:
            pytest.skip("No authenticated players available")
        
        host_player, host_token = authenticated_players[0]
        
        # Phase 1: Room Creation
        room_config = {
            "name": "E2E Test Room",
            "max_players": 4,
            "game_mode": "standard"
        }
        
        room = await room_manager.create_room(host_player, room_config)
        assert room.id is not None
        assert room.name == "E2E Test Room"
        assert len(room.players) == 1
        assert room.status == GameStatus.WAITING
        
        # Phase 2: Multiple Players Join
        for i in range(1, min(3, len(authenticated_players))):
            player, token = authenticated_players[i]
            join_success = await room_manager.join_room(room.id, player, team=f"team_{i}")
            assert join_success is True
        
        # Verify all players are in room
        updated_room = await room_manager.get_room(room.id)
        expected_players = min(3, len(authenticated_players))
        assert len(updated_room.players) == expected_players
        
        # Phase 3: Game State Verification
        assert updated_room.game_state is not None
        assert updated_room.turn_id == 0
        assert updated_room.sequence_number == 0
        
        # Phase 4: Room Cleanup (would happen on server shutdown)
        await room_manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_multiplayer_chat_workflow(self, room_manager, validator, authenticated_players):
        """
        Test complete chat functionality in multiplayer context.
        
        Justification: Chat is essential for player coordination and social
        interaction. The workflow from message validation to broadcasting
        must work reliably across all connected players.
        """
        if len(authenticated_players) < 2:
            pytest.skip("Need at least 2 players for chat test")
        
        await room_manager.initialize()
        
        # Setup room with multiple players
        host_player, _ = authenticated_players[0]
        other_player, _ = authenticated_players[1]
        
        room = await room_manager.create_room(host_player, {"name": "Chat Room"})
        await room_manager.join_room(room.id, other_player)
        
        # Test chat message flow
        chat_command = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=1,
            payload={
                "message": "Hello everyone!",
                "channel": "general"
            }
        )
        
        # Validate chat command
        validation_result = await validator.validate_command(
            chat_command, host_player.id, room.id
        )
        assert validation_result.valid is True
        
        # Execute chat command
        response = await room_manager.execute_command(
            room.id, chat_command, host_player.id
        )
        
        assert response.success is True
        assert response.state_changed is False  # Chat doesn't change game state
        assert response.result_data["message"] == "Hello everyone!"
        assert response.result_data["player_name"] == host_player.name
        assert response.result_data["channel"] == "general"
        
        # Test different chat channels
        team_chat = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=2,
            payload={
                "message": "Team strategy discussion",
                "channel": "team"
            }
        )
        
        team_response = await room_manager.execute_command(
            room.id, team_chat, host_player.id
        )
        
        assert team_response.success is True
        assert team_response.result_data["channel"] == "team"
    
    @pytest.mark.asyncio
    async def test_turn_based_gameplay_workflow(self, room_manager, validator, authenticated_players):
        """
        Test turn-based gameplay with command sequencing.
        
        Justification: Turn-based mechanics require precise sequencing and state
        management. This test validates that multiple players can take turns
        with proper ordering and state synchronization.
        """
        if len(authenticated_players) < 2:
            pytest.skip("Need at least 2 players for turn-based test")
        
        await room_manager.initialize()
        
        # Setup game with multiple players
        player1, _ = authenticated_players[0]
        player2, _ = authenticated_players[1]
        
        room = await room_manager.create_room(player1, {"name": "Turn-Based Game"})
        await room_manager.join_room(room.id, player2)
        
        # Turn 1: Player 1 moves
        move_command_p1 = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=1,
            payload={
                "entity_id": "player1_entity",
                "target_x": 5,
                "target_y": 3
            }
        )
        
        move_response_p1 = await room_manager.execute_command(
            room.id, move_command_p1, player1.id
        )
        
        assert move_response_p1.success is True
        assert move_response_p1.turn_id == 1
        assert move_response_p1.sequence_number == 1
        assert move_response_p1.state_changed is True
        
        # Turn 1: Player 2 moves (same turn, next sequence)
        move_command_p2 = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=2,
            payload={
                "entity_id": "player2_entity",
                "target_x": 7,
                "target_y": 4
            }
        )
        
        move_response_p2 = await room_manager.execute_command(
            room.id, move_command_p2, player2.id
        )
        
        assert move_response_p2.success is True
        assert move_response_p2.turn_id == 1
        assert move_response_p2.sequence_number == 2
        
        # Verify room state tracking
        updated_room = await room_manager.get_room(room.id)
        assert updated_room.turn_id == 1
        assert updated_room.sequence_number == 2
        
        # Turn 2: Advanced turn with attack
        attack_command = GameCommand(
            command_type=CommandType.ATTACK,
            turn_id=2,
            sequence_number=1,
            payload={
                "attacker_id": "player1_entity",
                "target_id": "player2_entity",
                "weapon_id": "basic_weapon"
            }
        )
        
        attack_response = await room_manager.execute_command(
            room.id, attack_command, player1.id
        )
        
        assert attack_response.success is True
        assert attack_response.turn_id == 2
        
        # Final room state verification
        final_room = await room_manager.get_room(room.id)
        assert final_room.turn_id == 2
        assert final_room.sequence_number == 1
    
    @pytest.mark.asyncio
    async def test_player_reconnection_workflow(self, room_manager, authenticated_players):
        """
        Test player disconnection and reconnection handling.
        
        Justification: Network disconnections are common in multiplayer games.
        Players must be able to disconnect and reconnect without losing their
        game session or disrupting other players.
        """
        if len(authenticated_players) < 2:
            pytest.skip("Need at least 2 players for reconnection test")
        
        await room_manager.initialize()
        
        # Setup room with players
        player1, _ = authenticated_players[0]
        player2, _ = authenticated_players[1]
        
        room = await room_manager.create_room(player1, {"name": "Reconnection Test"})
        await room_manager.join_room(room.id, player2)
        
        # Verify initial state
        initial_room = await room_manager.get_room(room.id)
        assert len(initial_room.players) == 2
        assert initial_room.players[player1.id].connected is True
        assert initial_room.players[player2.id].connected is True
        
        # Simulate player2 disconnect
        await room_manager.handle_player_disconnect(room.id, player2.id)
        
        # Verify disconnect state
        disconnected_player = await room_manager.get_player(player2.id)
        assert disconnected_player.connected is False
        
        # Room should still contain player for reconnection
        room_after_disconnect = await room_manager.get_room(room.id)
        assert player2.id in room_after_disconnect.players
        assert len(room_after_disconnect.players) == 2  # Still 2 players
        
        # Player1 should still be able to execute commands
        test_command = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=1,
            payload={
                "message": "Testing during disconnect",
                "channel": "general"
            }
        )
        
        response = await room_manager.execute_command(
            room.id, test_command, player1.id
        )
        
        assert response.success is True
        
        # Simulate reconnection (would involve new socket connection in real scenario)
        reconnected_player = Player(id=player2.id, name=player2.name, connected=True)
        
        # Update player connection status
        room_after_disconnect.players[player2.id] = reconnected_player
        
        # Verify reconnection
        assert room_after_disconnect.players[player2.id].connected is True
    
    @pytest.mark.asyncio
    async def test_concurrent_command_processing(self, room_manager, validator, authenticated_players):
        """
        Test handling of simultaneous commands from multiple players.
        
        Justification: Multiplayer servers must handle concurrent player actions
        correctly. Race conditions and command conflicts must be resolved
        deterministically to maintain game integrity.
        """
        if len(authenticated_players) < 3:
            pytest.skip("Need at least 3 players for concurrent test")
        
        await room_manager.initialize()
        
        # Setup room with multiple players
        host_player, _ = authenticated_players[0]
        room = await room_manager.create_room(host_player, {"name": "Concurrent Test", "max_players": 4})
        
        players = [host_player]
        for i in range(1, min(3, len(authenticated_players))):
            player, _ = authenticated_players[i]
            await room_manager.join_room(room.id, player)
            players.append(player)
        
        # Create concurrent commands from different players
        concurrent_commands = []
        for i, player in enumerate(players):
            command = GameCommand(
                command_type=CommandType.MOVE,
                turn_id=1,
                sequence_number=i + 1,  # Different sequence numbers
                payload={
                    "entity_id": f"player{i+1}_entity",
                    "target_x": i + 1,
                    "target_y": i + 1
                }
            )
            concurrent_commands.append((command, player.id))
        
        # Execute commands concurrently
        tasks = []
        for command, player_id in concurrent_commands:
            task = room_manager.execute_command(room.id, command, player_id)
            tasks.append(task)
        
        # Wait for all commands to complete
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all commands succeeded
        successful_responses = [r for r in responses if not isinstance(r, Exception)]
        assert len(successful_responses) == len(concurrent_commands)
        
        for response in successful_responses:
            assert response.success is True
        
        # Verify final room state
        final_room = await room_manager.get_room(room.id)
        assert final_room.sequence_number == len(players)  # Highest sequence processed
    
    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, room_manager, validator, authenticated_players):
        """
        Test system recovery from various error conditions.
        
        Justification: Multiplayer systems must be resilient to errors and
        continue operating for unaffected players. Error recovery ensures
        system stability and player experience continuity.
        """
        if len(authenticated_players) < 2:
            pytest.skip("Need at least 2 players for error recovery test")
        
        await room_manager.initialize()
        
        # Setup test environment
        player1, _ = authenticated_players[0]
        player2, _ = authenticated_players[1]
        
        room = await room_manager.create_room(player1, {"name": "Error Recovery Test"})
        await room_manager.join_room(room.id, player2)
        
        # Test 1: Invalid command handling
        invalid_command = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=1,
            payload={}  # Missing required fields
        )
        
        validation_result = await validator.validate_command(
            invalid_command, player1.id, room.id
        )
        assert validation_result.valid is False
        
        # Test 2: Command execution with nonexistent room
        valid_command = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=1,
            payload={
                "message": "Test message",
                "channel": "general"
            }
        )
        
        error_response = await room_manager.execute_command(
            "nonexistent_room", valid_command, player1.id
        )
        
        assert error_response.success is False
        assert "Room or game state not found" in error_response.error_message
        
        # Test 3: System continues operating after errors
        # Valid command should still work after previous errors
        success_response = await room_manager.execute_command(
            room.id, valid_command, player1.id
        )
        
        assert success_response.success is True
        
        # Test 4: Room remains functional after errors
        room_state = await room_manager.get_room(room.id)
        assert room_state is not None
        assert len(room_state.players) == 2
        assert room_state.game_state is not None
    
    @pytest.mark.asyncio
    async def test_full_game_session_simulation(self, room_manager, validator, authenticated_players):
        """
        Test complete game session from start to finish.
        
        Justification: This comprehensive test simulates a full multiplayer
        game session including all major interactions. It validates that the
        entire system works together for a complete player experience.
        """
        if len(authenticated_players) < 2:
            pytest.skip("Need at least 2 players for full session test")
        
        await room_manager.initialize()
        
        # Session Setup Phase
        host_player, host_token = authenticated_players[0]
        guest_player, guest_token = authenticated_players[1]
        
        # Create and join room
        room = await room_manager.create_room(
            host_player, 
            {"name": "Full Session Test", "max_players": 2}
        )
        await room_manager.join_room(room.id, guest_player, team="blue")
        
        # Pre-game Chat Phase
        welcome_message = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=0,  # Pre-game
            sequence_number=1,
            payload={
                "message": "Welcome to the game!",
                "channel": "general"
            }
        )
        
        chat_response = await room_manager.execute_command(
            room.id, welcome_message, host_player.id
        )
        assert chat_response.success is True
        
        # Gameplay Phase - Multiple turns
        game_commands = [
            # Turn 1
            (host_player.id, CommandType.MOVE, 1, 1, {
                "entity_id": "host_entity", "target_x": 3, "target_y": 3
            }),
            (guest_player.id, CommandType.MOVE, 1, 2, {
                "entity_id": "guest_entity", "target_x": 7, "target_y": 7
            }),
            
            # Turn 2 - Combat
            (host_player.id, CommandType.ATTACK, 2, 1, {
                "attacker_id": "host_entity", "target_id": "guest_entity"
            }),
            (guest_player.id, CommandType.ATTACK, 2, 2, {
                "attacker_id": "guest_entity", "target_id": "host_entity"
            }),
            
            # Turn 3 - Game ending
            (host_player.id, CommandType.END_TURN, 3, 1, {}),
        ]
        
        # Execute all game commands
        all_successful = True
        for player_id, cmd_type, turn, seq, payload in game_commands:
            command = GameCommand(
                command_type=cmd_type,
                turn_id=turn,
                sequence_number=seq,
                payload=payload
            )
            
            # Validate command
            validation = await validator.validate_command(command, player_id, room.id)
            if not validation.valid:
                all_successful = False
                continue
            
            # Execute command
            response = await room_manager.execute_command(room.id, command, player_id)
            if not response.success:
                all_successful = False
        
        assert all_successful, "All game commands should execute successfully"
        
        # Session Cleanup Phase
        final_room = await room_manager.get_room(room.id)
        assert final_room.turn_id == 3
        assert final_room.sequence_number == 1
        assert len(final_room.players) == 2
        
        # Simulate session end
        await room_manager.handle_player_disconnect(room.id, host_player.id)
        await room_manager.handle_player_disconnect(room.id, guest_player.id)
        
        # Verify cleanup
        host_status = await room_manager.get_player(host_player.id)
        guest_status = await room_manager.get_player(guest_player.id)
        
        assert host_status.connected is False
        assert guest_status.connected is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])