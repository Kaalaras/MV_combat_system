"""
Multiplayer data models and DTOs for network serialization
"""

import uuid
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass, asdict
from pydantic import BaseModel, Field, ConfigDict


class GameStatus(Enum):
    """Game room status"""
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CommandType(Enum):
    """Types of game commands"""
    MOVE = "move"
    ATTACK = "attack"
    USE_DISCIPLINE = "use_discipline"
    RELOAD = "reload"
    END_TURN = "end_turn"
    CHAT = "chat"


# Pydantic Models for API

class Player(BaseModel):
    """Player information"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    team: Optional[str] = None
    connected: bool = True
    session_id: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PlayerJoinRequest(BaseModel):
    """Request to join a game room"""
    team: Optional[str] = None
    spectator: bool = False


class AuthToken(BaseModel):
    """JWT authentication token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # seconds


class GameCommand(BaseModel):
    """Command sent from client to server"""
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command_type: CommandType
    player_id: Optional[str] = None
    turn_id: int = 0
    sequence_number: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Dict[str, Any]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        use_enum_values = True


class CommandResponse(BaseModel):
    """Response to a game command"""
    command_id: str
    success: bool
    turn_id: int
    sequence_number: int
    state_changed: bool = False
    error_message: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ValidationResult(BaseModel):
    """Result of command validation"""
    valid: bool
    reason: Optional[str] = None
    modified_command: Optional[GameCommand] = None


# Data Classes for Internal Use

@dataclass
class GameRoom:
    """Internal game room representation"""
    id: str
    name: str
    host_player: Player
    players: Dict[str, Player]
    max_players: int = 8
    status: GameStatus = GameStatus.WAITING
    game_state: Optional[Any] = None  # Will be CoreGameState
    turn_id: int = 0
    sequence_number: int = 0
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def add_player(self, player: Player) -> bool:
        """Add player to room"""
        if len(self.players) >= self.max_players:
            return False
        self.players[player.id] = player
        return True
    
    def remove_player(self, player_id: str) -> bool:
        """Remove player from room"""
        if player_id in self.players:
            del self.players[player_id]
            return True
        return False


# Command Payload Schemas

class MoveCommandPayload(BaseModel):
    """Payload for move command"""
    entity_id: str
    target_x: int
    target_y: int
    path: Optional[List[tuple]] = None


class AttackCommandPayload(BaseModel):
    """Payload for attack command"""
    attacker_id: str
    target_id: str
    weapon_id: Optional[str] = None
    attack_type: str = "basic"


class DisciplineCommandPayload(BaseModel):
    """Payload for discipline command"""
    caster_id: str
    discipline_name: str
    target_id: Optional[str] = None
    target_position: Optional[tuple] = None
    power_level: int = 1


class ChatCommandPayload(BaseModel):
    """Payload for chat command"""
    message: str
    channel: str = "general"  # general, team, whisper
    target_player: Optional[str] = None


# Network Game State (simplified for Phase 1)

class GameState(BaseModel):
    """Network-serializable game state"""
    turn_id: int
    sequence_number: int
    current_player: Optional[str] = None
    entities: List[Dict] = []
    teams: Dict[str, List[str]] = {}
    game_phase: str = "preparation"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @classmethod
    def from_game_state(cls, game_state):
        """Convert core GameState to network format (simplified)"""
        return cls(
            turn_id=getattr(game_state, 'turn_id', 0),
            sequence_number=getattr(game_state, 'sequence_number', 0),
            current_player=getattr(game_state, 'current_player_id', None),
            entities=[],  # Simplified for Phase 1
            teams=getattr(game_state, '_teams', {}),
            game_phase=getattr(game_state, 'game_phase', 'preparation')
        )
    
    def dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            "turn_id": self.turn_id,
            "sequence_number": self.sequence_number,
            "current_player": self.current_player,
            "entities": self.entities,
            "teams": self.teams,
            "game_phase": self.game_phase,
            "timestamp": self.timestamp.isoformat()
        }