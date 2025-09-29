"""
Comprehensive tests for Phase 1 multiplayer implementation.
Tests Socket.IO integration, command/response patterns, and player session management.
"""

import pytest
import asyncio
import json
from typing import Dict, Any
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

# Import multiplayer modules
from multiplayer.server import app, sio, game_room_manager, command_validator
from multiplayer.models import (
    Player, GameCommand, CommandType, GameRoom, GameStatus,
    MoveCommandPayload, AttackCommandPayload, ChatCommandPayload
)
from multiplayer.auth import authenticate_player, create_access_token, get_current_player
from multiplayer.game_manager import GameRoomManager, CommandValidator


class TestMultiplayerPhase1:
    """
    Phase 1 Multiplayer Tests - Core Infrastructure
    
    Justification: These tests validate the foundational multiplayer infrastructure
    required for real-time game communication. Each test ensures critical functionality
    works correctly before building advanced features in later phases.
    """
    
    @pytest.fixture
    def mock_player_1(self):
        """Test player 1 for multiplayer scenarios"""
        return Player(id="player_001", name="Alice")
    
    @pytest.fixture
    def mock_player_2(self):
        """Test player 2 for multiplayer scenarios"""
        return Player(id="player_002", name="Bob")
    
    @pytest.fixture
    def room_manager(self):
        """Fresh game room manager instance"""
        return GameRoomManager()
    
    @pytest.fixture
    def validator(self):
        """Command validator instance"""
        return CommandValidator()
    
    @pytest.mark.asyncio
    async def test_authentication_flow(self):
        """
        Test JWT authentication flow for multiplayer access.
        
        Justification: Authentication is critical for multiplayer security.
        Players must be properly authenticated before joining games to prevent
        unauthorized access and maintain game integrity.
        """
        # Test valid authentication
        player = await authenticate_player("player1", "password123")
        assert player is not None
        assert player.id == "player1"
        assert player.name == "Player One"
        
        # Test invalid credentials  
        invalid_player = await authenticate_player("invalid", "wrong")
        assert invalid_player is None
        
        # Test token creation
        token = create_access_token({"sub": "player1"})
        assert token is not None
        assert isinstance(token, str)
        
        # Test token validation
        validated_player = await get_current_player(token)
        assert validated_player is not None
        assert validated_player.id == "player1"
    
    @pytest.mark.asyncio
    async def test_room_creation_and_joining(self, room_manager, mock_player_1, mock_player_2):
        """
        Test game room creation and player joining mechanics.
        
        Justification: Room management is fundamental to multiplayer architecture.
        Players must be able to create private game sessions and join existing ones
        with proper validation and capacity limits.
        """
        # Initialize room manager
        await room_manager.initialize()
        
        # Test room creation
        room_config = {"name": "Test Room", "max_players": 4}
        room = await room_manager.create_room(mock_player_1, room_config)
        
        assert room.id is not None
        assert room.name == "Test Room"
        assert room.max_players == 4
        assert room.status == GameStatus.WAITING
        assert mock_player_1.id in room.players
        assert room.host_player.id == mock_player_1.id
        
        # Test joining room
        join_success = await room_manager.join_room(room.id, mock_player_2)
        assert join_success is True
        
        # Verify player is in room
        updated_room = await room_manager.get_room(room.id)
        assert len(updated_room.players) == 2
        assert mock_player_2.id in updated_room.players
        
        # Test room capacity limit
        room_config_small = {"name": "Small Room", "max_players": 1}
        small_room = await room_manager.create_room(mock_player_1, room_config_small)
        
        join_full_room = await room_manager.join_room(small_room.id, mock_player_2)
        assert join_full_room is False  # Should fail - room full
    
    @pytest.mark.asyncio
    async def test_command_validation_system(self, validator):
        """
        Test command validation for different game actions.
        
        Justification: Command validation prevents invalid game states and cheating.
        All player actions must be validated server-side before execution to maintain
        game integrity and prevent exploitation.
        """
        # Test valid move command
        move_command = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=1,
            payload={
                "entity_id": "entity_001",
                "target_x": 5,
                "target_y": 3
            }
        )
        
        move_result = await validator.validate_command(move_command, "player_001", "room_001")
        assert move_result.valid is True
        
        # Test invalid move command (negative coordinates)
        invalid_move = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=2,
            payload={
                "entity_id": "entity_001",
                "target_x": -1,
                "target_y": 3
            }
        )
        
        invalid_result = await validator.validate_command(invalid_move, "player_001", "room_001")
        assert invalid_result.valid is False
        assert "Invalid target coordinates" in invalid_result.reason
        
        # Test valid attack command
        attack_command = GameCommand(
            command_type=CommandType.ATTACK,
            turn_id=1,
            sequence_number=3,
            payload={
                "attacker_id": "entity_001",
                "target_id": "entity_002",
                "weapon_id": "weapon_001"
            }
        )
        
        attack_result = await validator.validate_command(attack_command, "player_001", "room_001")
        assert attack_result.valid is True
        
        # Test invalid attack command (self-attack)
        self_attack = GameCommand(
            command_type=CommandType.ATTACK,
            turn_id=1,
            sequence_number=4,
            payload={
                "attacker_id": "entity_001",
                "target_id": "entity_001"  # Same entity
            }
        )
        
        self_attack_result = await validator.validate_command(self_attack, "player_001", "room_001")
        assert self_attack_result.valid is False
        assert "Cannot attack self" in self_attack_result.reason
        
        # Test chat command validation
        chat_command = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=5,
            payload={
                "message": "Hello world!",
                "channel": "general"
            }
        )
        
        chat_result = await validator.validate_command(chat_command, "player_001", "room_001")
        assert chat_result.valid is True
        
        # Test empty chat message
        empty_chat = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=6,
            payload={
                "message": "",
                "channel": "general"
            }
        )
        
        empty_chat_result = await validator.validate_command(empty_chat, "player_001", "room_001")
        assert empty_chat_result.valid is False
        assert "Empty message" in empty_chat_result.reason
    
    @pytest.mark.asyncio
    async def test_command_execution_flow(self, room_manager, mock_player_1):
        """
        Test end-to-end command execution in game rooms.
        
        Justification: Command execution is the core of multiplayer gameplay.
        Player actions must be processed reliably with proper error handling
        and state synchronization across all connected clients.
        """
        await room_manager.initialize()
        
        # Create room and add player
        room_config = {"name": "Command Test Room", "max_players": 4}
        room = await room_manager.create_room(mock_player_1, room_config)
        
        # Test chat command execution
        chat_command = GameCommand(
            command_type=CommandType.CHAT,
            turn_id=1,
            sequence_number=1,
            payload={
                "message": "Test message",
                "channel": "general"
            }
        )
        
        chat_response = await room_manager.execute_command(
            room.id, chat_command, mock_player_1.id
        )
        
        assert chat_response.success is True
        assert chat_response.command_id == chat_command.command_id
        assert chat_response.state_changed is False  # Chat doesn't change game state
        assert chat_response.result_data["message"] == "Test message"
        assert chat_response.result_data["player_name"] == mock_player_1.name
        
        # Test move command execution (simplified for Phase 1)
        move_command = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=2,
            payload={
                "entity_id": "entity_001",
                "target_x": 5,
                "target_y": 3
            }
        )
        
        move_response = await room_manager.execute_command(
            room.id, move_command, mock_player_1.id
        )
        
        assert move_response.success is True
        assert move_response.state_changed is True  # Move changes game state
        assert move_response.result_data["moved"] is True
        
        # Test command execution in non-existent room
        invalid_response = await room_manager.execute_command(
            "invalid_room", chat_command, mock_player_1.id
        )
        
        assert invalid_response.success is False
        assert "Room or game state not found" in invalid_response.error_message
    
    @pytest.mark.asyncio
    async def test_player_session_management(self, room_manager, mock_player_1, mock_player_2):
        """
        Test player session lifecycle and disconnection handling.
        
        Justification: Robust session management prevents game disruption from
        network issues. Players should be able to reconnect gracefully, and games
        should handle disconnections without breaking the experience for others.
        """
        await room_manager.initialize()
        
        # Create room with multiple players
        room_config = {"name": "Session Test Room", "max_players": 4}
        room = await room_manager.create_room(mock_player_1, room_config)
        await room_manager.join_room(room.id, mock_player_2)
        
        # Verify both players are connected
        updated_room = await room_manager.get_room(room.id)
        assert len(updated_room.players) == 2
        assert updated_room.players[mock_player_1.id].connected is True
        assert updated_room.players[mock_player_2.id].connected is True
        
        # Test player disconnection handling
        await room_manager.handle_player_disconnect(room.id, mock_player_2.id)
        
        # Verify player is marked as disconnected but still in room (for reconnection)
        player_2 = await room_manager.get_player(mock_player_2.id)
        assert player_2.connected is False
        
        final_room = await room_manager.get_room(room.id)
        assert mock_player_2.id in final_room.players  # Still in room for reconnection
    
    @pytest.mark.asyncio 
    async def test_turn_order_and_sequence_management(self, room_manager, mock_player_1):
        """
        Test turn-based sequencing for multiplayer consistency.
        
        Justification: Turn order prevents race conditions and ensures fair gameplay.
        Sequence numbers provide deterministic ordering for network events, critical
        for maintaining consistent game state across all clients.
        """
        await room_manager.initialize()
        
        # Create room
        room_config = {"name": "Turn Order Test", "max_players": 2}
        room = await room_manager.create_room(mock_player_1, room_config)
        
        # Execute commands with sequence numbers
        command_1 = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=1,
            payload={"entity_id": "entity_001", "target_x": 1, "target_y": 1}
        )
        
        command_2 = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=2,
            payload={"entity_id": "entity_001", "target_x": 2, "target_y": 2}
        )
        
        # Execute commands
        response_1 = await room_manager.execute_command(room.id, command_1, mock_player_1.id)
        response_2 = await room_manager.execute_command(room.id, command_2, mock_player_1.id)
        
        assert response_1.success is True
        assert response_2.success is True
        
        # Verify room tracks latest turn and sequence
        updated_room = await room_manager.get_room(room.id)
        assert updated_room.turn_id == 1
        assert updated_room.sequence_number == 2
        
        # Test out-of-order command (earlier sequence number)
        old_command = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=1,  # Already processed
            payload={"entity_id": "entity_001", "target_x": 0, "target_y": 0}
        )
        
        old_response = await room_manager.execute_command(room.id, old_command, mock_player_1.id)
        assert old_response.success is True  # Still succeeds in Phase 1
        
        # Sequence should not go backwards
        final_room = await room_manager.get_room(room.id)
        assert final_room.sequence_number == 2  # Unchanged
    
    @pytest.mark.asyncio
    async def test_room_listing_and_availability(self, room_manager, mock_player_1, mock_player_2):
        """
        Test room discovery and availability filtering.
        
        Justification: Players need to find available games to join. Room listing
        must accurately reflect which games are joinable, preventing attempts to
        join full or in-progress games.
        """
        await room_manager.initialize()
        
        # Initially no rooms
        available_rooms = await room_manager.get_available_rooms()
        assert len(available_rooms) == 0
        
        # Create available room
        room_config_1 = {"name": "Open Room", "max_players": 4}
        room_1 = await room_manager.create_room(mock_player_1, room_config_1)
        
        available_rooms = await room_manager.get_available_rooms()
        assert len(available_rooms) == 1
        assert available_rooms[0].id == room_1.id
        assert available_rooms[0].status == GameStatus.WAITING
        
        # Create full room
        room_config_2 = {"name": "Full Room", "max_players": 1}
        room_2 = await room_manager.create_room(mock_player_2, room_config_2)
        
        # Should still show both rooms (neither is full yet)
        available_rooms = await room_manager.get_available_rooms()
        assert len(available_rooms) == 2
        
        # Make room_2 full by setting status (simulating full capacity)
        room_2.status = GameStatus.IN_PROGRESS
        
        # Now only room_1 should be available
        available_rooms = await room_manager.get_available_rooms()
        assert len(available_rooms) == 1
        assert available_rooms[0].id == room_1.id
    
    def test_network_message_serialization(self):
        """
        Test proper JSON serialization of network messages.
        
        Justification: Network communication requires reliable serialization.
        All game objects must convert to/from JSON without data loss to ensure
        consistent state between server and clients.
        """
        # Test Player serialization
        player = Player(id="player_001", name="Test Player", team="red")
        player_dict = player.dict()
        
        assert player_dict["id"] == "player_001"
        assert player_dict["name"] == "Test Player"  
        assert player_dict["team"] == "red"
        assert player_dict["connected"] is True
        
        # Test GameCommand serialization
        command = GameCommand(
            command_type=CommandType.ATTACK,
            turn_id=5,
            sequence_number=10,
            payload={
                "attacker_id": "entity_001",
                "target_id": "entity_002"
            }
        )
        
        command_dict = command.dict()
        assert command_dict["command_type"] == "attack"
        assert command_dict["turn_id"] == 5
        assert command_dict["sequence_number"] == 10
        assert command_dict["payload"]["attacker_id"] == "entity_001"
        
        # Test JSON roundtrip
        json_str = json.dumps(command_dict, default=str)  # Handle datetime
        parsed = json.loads(json_str)
        assert parsed["command_type"] == "attack"
        assert parsed["turn_id"] == 5
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, room_manager, validator, mock_player_1):
        """
        Test error handling in multiplayer scenarios.
        
        Justification: Robust error handling prevents cascading failures in
        multiplayer environments. Network issues, invalid commands, and unexpected
        states must be handled gracefully without affecting other players.
        """
        await room_manager.initialize()
        
        # Test malformed command handling
        invalid_command = GameCommand(
            command_type=CommandType.MOVE,
            turn_id=1,
            sequence_number=1,
            payload={}  # Missing required fields
        )
        
        validation_result = await validator.validate_command(
            invalid_command, "player_001", "room_001"
        )
        assert validation_result.valid is False
        
        # Test command execution without room
        response = await room_manager.execute_command(
            "nonexistent_room", invalid_command, mock_player_1.id
        )
        assert response.success is False
        assert "Room or game state not found" in response.error_message
        
        # Test room operations with invalid player
        join_result = await room_manager.join_room("room_001", mock_player_1)
        assert join_result is False  # No such room exists
        
        # Test graceful handling of None values
        player = await room_manager.get_player("nonexistent_player")
        assert player is None
        
        room = await room_manager.get_room("nonexistent_room")
        assert room is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])