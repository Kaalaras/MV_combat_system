"""
Authentication and authorization for multiplayer server
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .models import Player

# Security configuration (simplified for Phase 1)
SECRET_KEY = "dev-secret-key-change-in-production"  # In production, use environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# FastAPI Security dependency for Bearer tokens
security = HTTPBearer()

# Temporary in-memory user storage (replace with database)
USERS_DB = {
    "player1": {
        "id": "player1", 
        "name": "Player One",
        "password": "password123"  # In production, use hashed passwords
    },
    "player2": {
        "id": "player2",
        "name": "Player Two", 
        "password": "password123"
    },
    "testuser": {
        "id": "testuser",
        "name": "Test User",
        "password": "testpass"
    }
}


async def authenticate_player(username: str, password: str) -> Optional[Player]:
    """
    Authenticate a player with username/password
    Returns Player object if valid, None otherwise
    """
    user_data = USERS_DB.get(username)
    if not user_data:
        return None
        
    if password != user_data["password"]:  # Simplified comparison for Phase 1
        return None
        
    return Player(
        id=user_data["id"],
        name=user_data["name"]
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token (simplified for Phase 1)
    """
    # For Phase 1, we'll use a simple token format
    # In production, use proper JWT with jose library
    player_id = data.get("sub", "unknown")
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    
    # Simple token format for Phase 1: playerid:timestamp
    token = f"{player_id}:{expire.timestamp()}"
    return token


async def get_current_player_from_token(token: str) -> Optional[Player]:
    """
    Get current player from token (simplified for Phase 1)
    """
    try:
        parts = token.split(":")
        if len(parts) != 2:
            return None
            
        player_id = parts[0]
        expire_timestamp = float(parts[1])
        
        # Check if token is expired
        if datetime.utcnow().timestamp() > expire_timestamp:
            return None
            
        # Find user by ID
        for username, data in USERS_DB.items():
            if data["id"] == player_id:
                return Player(
                    id=data["id"],
                    name=data["name"]
                )
        return None
        
    except (ValueError, IndexError):
        return None


async def get_current_player(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Player:
    """
    FastAPI dependency to get current player from Bearer token
    """
    player = await get_current_player_from_token(credentials.credentials)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return player


def validate_token(token: str) -> Optional[str]:
    """
    Validate a token and return player ID if valid
    Used for Socket.IO authentication
    """
    try:
        parts = token.split(":")
        if len(parts) != 2:
            return None
            
        player_id = parts[0]
        expire_timestamp = float(parts[1])
        
        # Check if token is expired
        if datetime.utcnow().timestamp() > expire_timestamp:
            return None
            
        return player_id
        
    except (ValueError, IndexError):
        return None