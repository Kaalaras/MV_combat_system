"""
Game room and command management for multiplayer server
"""

import uuid
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .models import (
    GameRoom, Player, GameCommand, CommandResponse, ValidationResult,
    CommandType, GameStatus, MoveCommandPayload, AttackCommandPayload, 
    DisciplineCommandPayload, ChatCommandPayload
)

logger = logging.getLogger(__name__)


class CommandValidator:
    """Validates game commands before execution"""
    
    async def validate_command(
        self, 
        command: GameCommand, 
        player_id: str, 
        room_id: str
    ) -> ValidationResult:
        """
        Validate a game command
        Returns ValidationResult with validation status and reason
        """
        try:
            # Basic validation
            if not command.command_id or not command.command_type:
                return ValidationResult(
                    valid=False, 
                    reason="Missing command_id or command_type"
                )
            
            # Validate command-specific payload
            if command.command_type == CommandType.MOVE:
                return await self._validate_move_command(command, player_id, room_id)
            elif command.command_type == CommandType.ATTACK:
                return await self._validate_attack_command(command, player_id, room_id)
            elif command.command_type == CommandType.USE_DISCIPLINE:
                return await self._validate_discipline_command(command, player_id, room_id)
            elif command.command_type == CommandType.CHAT:
                return await self._validate_chat_command(command, player_id, room_id)
            elif command.command_type == CommandType.END_TURN:
                return ValidationResult(valid=True)  # End turn is always valid
            else:
                return ValidationResult(
                    valid=False,
                    reason=f"Unknown command type: {command.command_type}"
                )
                
        except Exception as e:
            logger.error(f"Error validating command: {e}")
            return ValidationResult(
                valid=False,
                reason="Command validation failed"
            )
    
    async def _validate_move_command(
        self, 
        command: GameCommand, 
        player_id: str, 
        room_id: str
    ) -> ValidationResult:
        """Validate move command"""
        try:
            payload = MoveCommandPayload(**command.payload)
            
            # Basic payload validation
            if not payload.entity_id:
                return ValidationResult(valid=False, reason="Missing entity_id")
                
            if payload.target_x < 0 or payload.target_y < 0:
                return ValidationResult(valid=False, reason="Invalid target coordinates")
            
            return ValidationResult(valid=True)
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Invalid move command payload: {e}"
            )
    
    async def _validate_attack_command(
        self,
        command: GameCommand,
        player_id: str,
        room_id: str
    ) -> ValidationResult:
        """Validate attack command"""
        try:
            payload = AttackCommandPayload(**command.payload)
            
            if not payload.attacker_id or not payload.target_id:
                return ValidationResult(
                    valid=False, 
                    reason="Missing attacker_id or target_id"
                )
            
            if payload.attacker_id == payload.target_id:
                return ValidationResult(
                    valid=False,
                    reason="Cannot attack self"
                )
            
            return ValidationResult(valid=True)
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Invalid attack command payload: {e}"
            )
    
    async def _validate_discipline_command(
        self,
        command: GameCommand, 
        player_id: str,
        room_id: str
    ) -> ValidationResult:
        """Validate discipline command"""
        try:
            payload = DisciplineCommandPayload(**command.payload)
            
            if not payload.caster_id or not payload.discipline_name:
                return ValidationResult(
                    valid=False,
                    reason="Missing caster_id or discipline_name"
                )
            
            return ValidationResult(valid=True)
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Invalid discipline command payload: {e}"
            )
    
    async def _validate_chat_command(
        self,
        command: GameCommand,
        player_id: str, 
        room_id: str
    ) -> ValidationResult:
        """Validate chat command"""
        try:
            payload = ChatCommandPayload(**command.payload)
            
            if not payload.message or len(payload.message.strip()) == 0:
                return ValidationResult(valid=False, reason="Empty message")
                
            if len(payload.message) > 500:  # Max message length
                return ValidationResult(valid=False, reason="Message too long")
            
            return ValidationResult(valid=True)
            
        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Invalid chat command payload: {e}"
            )


class GameRoomManager:
    """Manages game rooms and their lifecycle"""
    
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}
        self.players: Dict[str, Player] = {}
        self.player_to_room: Dict[str, str] = {}  # player_id -> room_id
    
    async def initialize(self):
        """Initialize the game room manager"""
        logger.info("GameRoomManager initialized")
    
    async def cleanup(self):
        """Cleanup on shutdown"""
        for room in self.rooms.values():
            if room.game_state:
                # Save game state if needed
                pass
        logger.info("GameRoomManager cleaned up")
    
    async def create_room(
        self,
        host_player: Player,
        config: Dict[str, Any]
    ) -> GameRoom:
        """Create a new game room"""
        room_id = str(uuid.uuid4())
        room_name = config.get("name", f"Room {len(self.rooms) + 1}")
        max_players = config.get("max_players", 8)
        
        # For Phase 1, we'll create a simple mock game state
        mock_game_state = type('MockGameState', (), {
            'turn_id': 0,
            'sequence_number': 0,
            'current_player_id': None,
            '_teams': {},
            'game_phase': 'preparation'
        })()
        
        # Create room
        room = GameRoom(
            id=room_id,
            name=room_name,
            host_player=host_player,
            players={host_player.id: host_player},
            max_players=max_players,
            game_state=mock_game_state
        )
        
        self.rooms[room_id] = room
        self.players[host_player.id] = host_player
        self.player_to_room[host_player.id] = room_id
        
        logger.info(f"Created room {room_id} ({room_name}) hosted by {host_player.name}")
        return room
    
    async def join_room(
        self,
        room_id: str,
        player: Player,
        team: Optional[str] = None
    ) -> bool:
        """Join a player to an existing room"""
        if room_id not in self.rooms:
            return False
            
        room = self.rooms[room_id]
        
        if room.status != GameStatus.WAITING:
            return False
            
        if not room.add_player(player):
            return False
        
        # Store player info
        self.players[player.id] = player
        self.player_to_room[player.id] = room_id
        
        logger.info(f"Player {player.name} joined room {room_id}")
        return True
    
    async def get_room(self, room_id: str) -> Optional[GameRoom]:
        """Get room by ID"""
        return self.rooms.get(room_id)
    
    async def get_player(self, player_id: str) -> Optional[Player]:
        """Get player by ID"""
        return self.players.get(player_id)
    
    async def get_available_rooms(self) -> List[GameRoom]:
        """Get list of rooms available for joining"""
        return [
            room for room in self.rooms.values()
            if room.status == GameStatus.WAITING and len(room.players) < room.max_players
        ]
    
    async def execute_command(
        self,
        room_id: str,
        command: GameCommand,
        player_id: str
    ) -> CommandResponse:
        """Execute a validated game command"""
        try:
            room = self.rooms.get(room_id)
            if not room or not room.game_state:
                return CommandResponse(
                    command_id=command.command_id,
                    success=False,
                    turn_id=command.turn_id,
                    sequence_number=command.sequence_number,
                    error_message="Room or game state not found"
                )
            
            # Update turn tracking
            room.turn_id = max(room.turn_id, command.turn_id)
            room.sequence_number = max(room.sequence_number, command.sequence_number)
            
            # Execute based on command type (simplified for Phase 1)
            if command.command_type == CommandType.CHAT:
                return await self._execute_chat_command(room, command, player_id)
            elif command.command_type == CommandType.MOVE:
                # For Phase 1, just return success without actual movement
                return CommandResponse(
                    command_id=command.command_id,
                    success=True,  # Always succeed for Phase 1
                    turn_id=command.turn_id,
                    sequence_number=command.sequence_number,
                    state_changed=True,
                    result_data={"moved": True}
                )
            else:
                return CommandResponse(
                    command_id=command.command_id,
                    success=True,  # For Phase 1, all commands succeed
                    turn_id=command.turn_id,
                    sequence_number=command.sequence_number,
                    state_changed=False,
                    result_data={"executed": True}
                )
                
        except Exception as e:
            logger.error(f"Error executing command {command.command_id}: {e}")
            return CommandResponse(
                command_id=command.command_id,
                success=False,
                turn_id=command.turn_id,
                sequence_number=command.sequence_number,
                error_message="Command execution failed"
            )
    
    async def _execute_chat_command(
        self,
        room: GameRoom,
        command: GameCommand,
        player_id: str
    ) -> CommandResponse:
        """Execute chat command"""
        payload = ChatCommandPayload(**command.payload)
        player = self.players.get(player_id)
        
        return CommandResponse(
            command_id=command.command_id,
            success=True,
            turn_id=command.turn_id,
            sequence_number=command.sequence_number,
            state_changed=False,
            result_data={
                "message": payload.message,
                "player_name": player.name if player else "Unknown",
                "channel": payload.channel
            }
        )
    
    async def handle_player_disconnect(self, room_id: str, player_id: str):
        """Handle player disconnection"""
        if player_id in self.players:
            self.players[player_id].connected = False
        
        logger.info(f"Player {player_id} disconnected from room {room_id}")