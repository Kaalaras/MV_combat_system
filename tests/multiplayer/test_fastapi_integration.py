"""
Integration tests for FastAPI REST endpoints supporting multiplayer functionality.
Tests authentication, room management, and HTTP API integration.
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from multiplayer.server import app
from multiplayer.models import Player, GameRoom, GameStatus


class TestFastAPIIntegration:
    """
    FastAPI REST API Integration Tests
    
    Justification: REST endpoints provide essential multiplayer infrastructure
    for authentication, room management, and game session control. These APIs
    must work reliably to support the Socket.IO real-time functionality.
    """
    
    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_token(self):
        """Mock valid JWT token"""
        return "player1:9999999999.0"
    
    @pytest.fixture
    def mock_player(self):
        """Mock authenticated player"""
        return Player(id="player_001", name="Test Player")
    
    def test_health_check_endpoint(self, client):
        """
        Test health check endpoint for load balancer monitoring.
        
        Justification: Health checks are critical for production deployment
        with load balancers and monitoring systems. The endpoint must respond
        quickly and reliably indicate server status.
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
    
    def test_login_endpoint_success(self, client):
        """
        Test successful player authentication via REST API.
        
        Justification: Authentication is the entry point to multiplayer functionality.
        Players must be able to login and receive valid JWT tokens for subsequent
        API calls and Socket.IO connections.
        """
        credentials = {
            "username": "player1",
            "password": "password123"
        }
        
        with patch('multiplayer.server.authenticate_player') as mock_auth, \
             patch('multiplayer.server.create_access_token') as mock_token:
            
            # Mock successful authentication
            mock_player = Player(id="player1", name="Player One")
            mock_auth.return_value = mock_player
            mock_token.return_value = "mock_jwt_token"
            
            response = client.post("/auth/login", json=credentials)
            
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "mock_jwt_token"
            assert data["token_type"] == "bearer"
            
            # Verify authentication was called with correct credentials
            mock_auth.assert_called_once_with("player1", "password123")
    
    def test_login_endpoint_failure(self, client):
        """
        Test login endpoint with invalid credentials.
        
        Justification: Failed authentication must be handled securely without
        revealing sensitive information. Invalid credentials should return
        appropriate error codes and messages.
        """
        credentials = {
            "username": "invalid",
            "password": "wrong"
        }
        
        with patch('multiplayer.server.authenticate_player', return_value=None):
            response = client.post("/auth/login", json=credentials)
            
            assert response.status_code == 401
            data = response.json()
            assert "Invalid credentials" in data["detail"]
    
    def test_login_endpoint_missing_credentials(self, client):
        """
        Test login endpoint with missing credentials.
        
        Justification: API validation must catch missing required fields and
        return clear error messages to guide correct client implementation.
        """
        # Test missing username
        incomplete_credentials = {"password": "password123"}
        response = client.post("/auth/login", json=incomplete_credentials)
        
        assert response.status_code == 400
        data = response.json()
        assert "Username and password required" in data["detail"]
        
        # Test missing password
        incomplete_credentials = {"username": "player1"}
        response = client.post("/auth/login", json=incomplete_credentials)
        
        assert response.status_code == 400
    
    def test_create_room_endpoint(self, client, mock_token, mock_player):
        """
        Test room creation via REST API.
        
        Justification: Room creation is essential for multiplayer game sessions.
        Authenticated players must be able to create private game rooms with
        specified configurations.
        """
        room_config = {
            "name": "Test Room",
            "max_players": 4,
            "game_mode": "standard"
        }
        
        headers = {"Authorization": f"Bearer {mock_token}"}
        
        with patch('multiplayer.auth.get_current_player_from_token', return_value=mock_player), \
             patch('multiplayer.server.game_room_manager.create_room') as mock_create:
            
            # Mock successful room creation
            mock_room = MagicMock()
            mock_room.id = "room_001"
            mock_room.name = "Test Room"
            mock_create.return_value = mock_room
            
            response = client.post("/rooms", json=room_config, headers=headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["room_id"] == "room_001"
            assert data["room_name"] == "Test Room"
            assert data["status"] == "created"
            
            # Verify room creation was called
            mock_create.assert_called_once_with(
                host_player=mock_player,
                config=room_config
            )
    
    def test_create_room_unauthorized(self, client):
        """
        Test room creation without authentication.
        
        Justification: Protected endpoints must enforce authentication to prevent
        unauthorized access and maintain security of game sessions.
        """
        room_config = {"name": "Unauthorized Room", "max_players": 2}
        
        # No Authorization header
        response = client.post("/rooms", json=room_config)
        
        assert response.status_code == 403  # Forbidden due to missing auth
    
    def test_list_rooms_endpoint(self, client):
        """
        Test listing available game rooms.
        
        Justification: Players need to discover available games to join.
        The endpoint must return accurate information about joinable rooms
        with proper filtering of full or in-progress games.
        """
        mock_rooms = [
            MagicMock(
                id="room_001",
                name="Room 1",
                players={"p1": MagicMock(), "p2": MagicMock()},
                max_players=4,
                status=GameStatus.WAITING
            ),
            MagicMock(
                id="room_002", 
                name="Room 2",
                players={"p3": MagicMock()},
                max_players=2,
                status=GameStatus.WAITING
            )
        ]
        
        with patch('multiplayer.server.game_room_manager.get_available_rooms', 
                  return_value=mock_rooms):
            
            response = client.get("/rooms")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            
            assert data[0]["room_id"] == "room_001"
            assert data[0]["room_name"] == "Room 1"
            assert data[0]["players"] == 2
            assert data[0]["max_players"] == 4
            assert data[0]["status"] == "waiting"
            
            assert data[1]["room_id"] == "room_002"
            assert data[1]["players"] == 1
            assert data[1]["max_players"] == 2
    
    def test_join_room_endpoint(self, client, mock_token, mock_player):
        """
        Test joining an existing room via REST API.
        
        Justification: Players must be able to join existing game sessions
        through the REST API. Join requests should be validated and processed
        with appropriate success/failure responses.
        """
        room_id = "room_001"
        join_request = {"team": "red", "spectator": False}
        headers = {"Authorization": f"Bearer {mock_token}"}
        
        with patch('multiplayer.auth.get_current_player_from_token', return_value=mock_player), \
             patch('multiplayer.server.game_room_manager.join_room', return_value=True) as mock_join:
            
            response = client.post(
                f"/rooms/{room_id}/join",
                json=join_request,
                headers=headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "joined"
            assert data["room_id"] == room_id
            
            # Verify join was attempted with correct parameters
            mock_join.assert_called_once_with(
                room_id=room_id,
                player=mock_player,
                team="red"
            )
    
    def test_join_room_failure(self, client, mock_token, mock_player):
        """
        Test joining room when join operation fails.
        
        Justification: Room joining can fail due to full capacity, game in progress,
        or other conditions. Failures must be handled gracefully with appropriate
        error messages.
        """
        room_id = "full_room"
        join_request = {"team": "blue"}
        headers = {"Authorization": f"Bearer {mock_token}"}
        
        with patch('multiplayer.server.get_current_player', return_value=mock_player), \
             patch('multiplayer.server.game_room_manager.join_room', return_value=False):
            
            response = client.post(
                f"/rooms/{room_id}/join",
                json=join_request,
                headers=headers
            )
            
            assert response.status_code == 400
            data = response.json()
            assert "Cannot join room" in data["detail"]
    
    def test_join_nonexistent_room(self, client, mock_token, mock_player):
        """
        Test joining a room that doesn't exist.
        
        Justification: Attempts to join nonexistent rooms should be handled
        gracefully without crashing the server. Clear error messages help
        client applications handle these scenarios.
        """
        room_id = "nonexistent_room"
        join_request = {"team": "red"}
        headers = {"Authorization": f"Bearer {mock_token}"}
        
        with patch('multiplayer.server.get_current_player', return_value=mock_player), \
             patch('multiplayer.server.game_room_manager.join_room', 
                   side_effect=Exception("Room not found")):
            
            response = client.post(
                f"/rooms/{room_id}/join",
                json=join_request,
                headers=headers
            )
            
            assert response.status_code == 500
            data = response.json()
            assert "Failed to join room" in data["detail"]
    
    def test_cors_headers(self, client):
        """
        Test CORS headers for web client support.
        
        Justification: Web clients need proper CORS headers to access the API
        from browser environments. CORS must be configured correctly for
        cross-origin requests from game clients.
        """
        # Test preflight request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization"
            }
        )
        
        # Should allow the request (exact behavior depends on CORS middleware config)
        assert response.status_code in [200, 204]
    
    def test_api_error_handling(self, client):
        """
        Test API error handling and response format consistency.
        
        Justification: Consistent error handling helps client applications
        process errors correctly. All endpoints should return well-formatted
        error responses with appropriate HTTP status codes.
        """
        # Test invalid JSON payload
        invalid_json = "{'invalid': json syntax}"
        headers = {"Content-Type": "application/json"}
        
        response = client.post("/auth/login", content=invalid_json, headers=headers)
        
        assert response.status_code == 422  # Unprocessable Entity
        
        # Test missing Content-Type for JSON endpoints
        response = client.post("/auth/login", data="some data")
        
        assert response.status_code in [400, 422]  # Bad Request or Unprocessable Entity
    
    def test_authentication_token_validation(self, client):
        """
        Test JWT token validation in protected endpoints.
        
        Justification: Token validation is critical for API security. Invalid,
        expired, or malformed tokens should be rejected consistently across
        all protected endpoints.
        """
        invalid_tokens = [
            "invalid_token_format",
            "expired:1000000000.0",  # Expired timestamp
            "malformed:not_a_timestamp",
            "",  # Empty token
            "bearer token_without_bearer_prefix"
        ]
        
        for invalid_token in invalid_tokens:
            headers = {"Authorization": f"Bearer {invalid_token}"}
            
            response = client.post(
                "/rooms",
                json={"name": "Test Room"},
                headers=headers
            )
            
            # Should be unauthorized or forbidden
            assert response.status_code in [401, 403, 422]
    
    def test_api_rate_limiting_simulation(self, client):
        """
        Test API behavior under high request volume (rate limiting simulation).
        
        Justification: APIs must handle high request volumes gracefully. While
        rate limiting isn't implemented in Phase 1, the server should remain
        responsive under load without degrading other clients' performance.
        """
        # Simulate multiple rapid requests
        responses = []
        
        for i in range(10):
            response = client.get("/health")
            responses.append(response.status_code)
        
        # All requests should succeed in Phase 1
        assert all(status == 200 for status in responses)
        
        # In production with rate limiting, some might return 429 (Too Many Requests)
    
    def test_concurrent_api_requests(self, client):
        """
        Test handling of concurrent API requests.
        
        Justification: Multiplayer servers receive many simultaneous requests.
        The API must handle concurrent requests correctly without race conditions
        or data corruption.
        """
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.get("/health")
            results.append(response.status_code)
        
        # Create multiple threads for concurrent requests
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        assert len(results) == 5
        assert all(status == 200 for status in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])