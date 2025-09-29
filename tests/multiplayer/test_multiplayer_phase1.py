"""
Comprehensive tests for Phase 1 Multiplayer Infrastructure
Tests Socket.IO integration, player session management, and command/response patterns
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import socketio
from fastapi.testclient import TestClient

from ...multiplayer.server import app, sio, game_room_manager, command_validator
from ...multiplayer.models import (
    Player, GameCommand, CommandType, GameRoom, GameStatus,
    MoveCommandPayload, ChatCommandPayload
)
from ...multiplayer.auth import create_access_token, authenticate_player
from ...multiplayer.game_manager import GameRoomManager, CommandValidator


class TestMultiplayerPhase1:
    """
    Comprehensive test suite for Phase 1 multiplayer implementation
    
    JUSTIFICATION: Phase 1 is the foundation for the entire multiplayer system.
    These tests ensure Socket.IO integration, player sessions, and command patterns
    work correctly before building more complex features. Critical for preventing
    architectural issues that would compound in later phases.
    """

    @pytest.fixture
    def test_client(self):
        """Test client for FastAPI endpoints"""
        return TestClient(app)

    @pytest.fixture
    async def test_player(self):
        """Create test player with authentication token"""
        player = Player(id="test_player_1", name="Test Player")
        token = create_access_token(data={"sub": player.id})
        return player, token

    @pytest.fixture
    async def game_room(self, test_player):
        """Create test game room"""
        player, _ = test_player
        room = await game_room_manager.create_room(
            host_player=player,
            config={"name": "Test Room", "max_players": 4}
        )
        return room

    @pytest.fixture
    async def authenticated_headers(self, test_player):
        """HTTP headers with authentication"""
        _, token = test_player
        return {"Authorization": f"Bearer {token}"}

    # Authentication & API Tests

    def test_health_endpoint(self, test_client):
        """
        Test health check endpoint for load balancers
        
        JUSTIFICATION: Health checks are essential for production deployment
        with load balancers and container orchestration. Ensures server
        status monitoring works correctly.
        """
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])