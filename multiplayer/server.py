"""
FastAPI + Socket.IO Multiplayer Server
Provides authoritative game state management and real-time communication.
"""

import uuid
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
import socketio

from .models import (
    GameRoom, Player, GameCommand, CommandResponse, 
    PlayerJoinRequest, AuthToken, GameState as NetworkGameState
)
from .auth import authenticate_player, create_access_token, get_current_player
from .game_manager import GameRoomManager, CommandValidator

# Import core modules with path fix
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    from core.game_state import GameState  
    from core.enhanced_event_bus import EnhancedEventBus
except ImportError:
    # Fallback for testing - create mock classes
    GameState = type('GameState', (), {})
    EnhancedEventBus = type('EnhancedEventBus', (), {})

logger = logging.getLogger(__name__)

# FastAPI App
app = FastAPI(title="MV Combat System - Multiplayer Server", version="1.0.0")

# CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080"],  # Add production domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO Server
sio = socketio.AsyncServer(
    cors_allowed_origins=["http://localhost:3000", "http://localhost:8080"],
    logger=True,
    engineio_logger=True
)

# Security
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Global instances
game_room_manager = GameRoomManager()
command_validator = CommandValidator()

# Connect Socket.IO to FastAPI
socket_app = socketio.ASGIApp(sio, app)


# REST API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/auth/login", response_model=AuthToken)
async def login(credentials: dict):
    """
    Authenticate player and return JWT token
    Basic implementation - extend with real authentication
    """
    username = credentials.get("username")
    password = credentials.get("password")
    
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password required"
        )
    
    # Basic authentication (extend with database lookup)
    player = await authenticate_player(username, password)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    access_token = create_access_token(data={"sub": player.id})
    return AuthToken(access_token=access_token, token_type="bearer")


@app.post("/rooms", response_model=dict)
async def create_room(
    room_config: dict,
    current_player: Player = Depends(get_current_player)
):
    """Create a new game room"""
    try:
        room = await game_room_manager.create_room(
            host_player=current_player,
            config=room_config
        )
        return {
            "room_id": room.id,
            "room_name": room.name,
            "status": "created"
        }
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(status_code=500, detail="Failed to create room")


@app.get("/rooms", response_model=List[dict])
async def list_rooms():
    """List available game rooms"""
    rooms = await game_room_manager.get_available_rooms()
    return [
        {
            "room_id": room.id,
            "room_name": room.name,
            "players": len(room.players),
            "max_players": room.max_players,
            "status": room.status.value
        }
        for room in rooms
    ]


@app.post("/rooms/{room_id}/join", response_model=dict)
async def join_room(
    room_id: str,
    join_request: PlayerJoinRequest,
    current_player: Player = Depends(get_current_player)
):
    """Join an existing game room"""
    try:
        success = await game_room_manager.join_room(
            room_id=room_id,
            player=current_player,
            team=join_request.team
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot join room"
            )
        
        return {"status": "joined", "room_id": room_id}
        
    except Exception as e:
        logger.error(f"Error joining room {room_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to join room")


# Socket.IO Event Handlers

@sio.event
async def connect(sid, environ, auth):
    """Handle client connection"""
    try:
        # Authenticate via token in auth data
        if not auth or 'token' not in auth:
            logger.warning(f"Connection {sid} rejected: no auth token")
            return False
            
        token = auth['token']
        player = await get_current_player_from_token(token)
        
        if not player:
            logger.warning(f"Connection {sid} rejected: invalid token")
            return False
            
        # Store player info for this session
        await sio.save_session(sid, {
            'player_id': player.id,
            'player_name': player.name,
            'room_id': None
        })
        
        logger.info(f"Player {player.name} connected with session {sid}")
        await sio.emit('connected', {'status': 'success'}, room=sid)
        
    except Exception as e:
        logger.error(f"Error in connect handler: {e}")
        return False


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    try:
        session = await sio.get_session(sid)
        player_id = session.get('player_id')
        room_id = session.get('room_id')
        
        if room_id:
            await game_room_manager.handle_player_disconnect(room_id, player_id)
            await sio.leave_room(sid, room_id)
        
        logger.info(f"Player {player_id} disconnected from session {sid}")
        
    except Exception as e:
        logger.error(f"Error in disconnect handler: {e}")


@sio.event
async def join_game_room(sid, data):
    """Handle player joining a game room via Socket.IO"""
    try:
        session = await sio.get_session(sid)
        player_id = session['player_id']
        room_id = data['room_id']
        
        # Get player object
        player = await game_room_manager.get_player(player_id)
        if not player:
            await sio.emit('error', {'message': 'Player not found'}, room=sid)
            return
            
        # Join the room
        success = await game_room_manager.join_room(
            room_id=room_id,
            player=player,
            team=data.get('team')
        )
        
        if success:
            await sio.enter_room(sid, room_id)
            session['room_id'] = room_id
            await sio.save_session(sid, session)
            
            # Notify all players in room
            await sio.emit('player_joined', {
                'player_id': player.id,
                'player_name': player.name,
                'team': data.get('team')
            }, room=room_id)
            
            # Send current game state to new player
            room = await game_room_manager.get_room(room_id)
            if room and room.game_state:
                network_state = NetworkGameState.from_game_state(room.game_state)
                await sio.emit('game_state', network_state.dict(), room=sid)
                
        else:
            await sio.emit('error', {'message': 'Failed to join room'}, room=sid)
            
    except Exception as e:
        logger.error(f"Error in join_game_room: {e}")
        await sio.emit('error', {'message': 'Internal server error'}, room=sid)


@sio.event
async def game_command(sid, data):
    """Handle game command from client"""
    try:
        session = await sio.get_session(sid)
        player_id = session['player_id']
        room_id = session.get('room_id')
        
        if not room_id:
            await sio.emit('error', {'message': 'Not in a game room'}, room=sid)
            return
            
        # Parse and validate command
        command = GameCommand(**data)
        validation_result = await command_validator.validate_command(
            command, player_id, room_id
        )
        
        if not validation_result.valid:
            await sio.emit('command_rejected', {
                'command_id': command.command_id,
                'reason': validation_result.reason
            }, room=sid)
            return
            
        # Execute command
        result = await game_room_manager.execute_command(room_id, command, player_id)
        
        # Send response to all players in room
        if result.success:
            # Broadcast state changes to all players
            await sio.emit('command_executed', {
                'command_id': command.command_id,
                'player_id': player_id,
                'result': result.dict()
            }, room=room_id)
            
            # Send updated game state if significant change
            if result.state_changed:
                room = await game_room_manager.get_room(room_id)
                if room and room.game_state:
                    network_state = NetworkGameState.from_game_state(room.game_state)
                    await sio.emit('game_state_update', 
                                 network_state.dict(), room=room_id)
        else:
            await sio.emit('command_failed', {
                'command_id': command.command_id,
                'reason': result.error_message
            }, room=sid)
            
    except Exception as e:
        logger.error(f"Error in game_command: {e}")
        await sio.emit('error', {'message': 'Command processing failed'}, room=sid)


@sio.event
async def get_game_state(sid):
    """Send current game state to requesting client"""
    try:
        session = await sio.get_session(sid)
        room_id = session.get('room_id')
        
        if not room_id:
            await sio.emit('error', {'message': 'Not in a game room'}, room=sid)
            return
            
        room = await game_room_manager.get_room(room_id)
        if room and room.game_state:
            network_state = NetworkGameState.from_game_state(room.game_state)
            await sio.emit('game_state', network_state.dict(), room=sid)
        else:
            await sio.emit('error', {'message': 'Game state not available'}, room=sid)
            
    except Exception as e:
        logger.error(f"Error in get_game_state: {e}")
        await sio.emit('error', {'message': 'Failed to get game state'}, room=sid)


# Helper Functions

async def get_current_player_from_token(token: str) -> Optional[Player]:
    """Extract player from JWT token"""
    try:
        # This would normally verify against your user database
        payload = jwt.decode(token, "your-secret-key", algorithms=["HS256"])
        player_id = payload.get("sub")
        
        if player_id:
            return await game_room_manager.get_player(player_id)
        return None
        
    except JWTError:
        return None


# Application startup
@app.on_event("startup")
async def startup_event():
    """Initialize server on startup"""
    logger.info("MV Combat System Multiplayer Server starting up...")
    await game_room_manager.initialize()


@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup on server shutdown"""
    logger.info("MV Combat System Multiplayer Server shutting down...")
    await game_room_manager.cleanup()


# Export the ASGI app for uvicorn
application = socket_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multiplayer.server:application",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )