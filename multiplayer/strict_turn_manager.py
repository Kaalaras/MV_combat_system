"""
Strict Turn Manager for Turn-Based Multiplayer Combat

Enforces strict turn-based ordering with timeout handling and disconnection recovery.
All actions are resolved in initiative order with proper fallback mechanisms.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TurnPhase(Enum):
    WAITING_FOR_PLAYERS = "waiting_for_players"
    INITIATIVE = "initiative"
    COLLECTING_ACTIONS = "collecting_actions"
    RESOLVING_ACTIONS = "resolving_actions"
    APPLYING_RESULTS = "applying_results"
    END_TURN = "end_turn"

@dataclass
class PlayerAction:
    player_id: str
    action_type: str
    data: Dict[str, Any]
    sequence_number: int
    timestamp: float
    
@dataclass
class TurnState:
    turn_number: int
    phase: TurnPhase
    initiative_order: List[str]
    collected_actions: Dict[str, PlayerAction]
    waiting_for: Set[str]
    phase_timeout: float
    turn_started_at: float

class StrictTurnManager:
    """
    Manages strict turn-based multiplayer with initiative ordering and timeout handling.
    
    Features:
    - Strict initiative-based action resolution
    - Timeout handling for laggy/disconnected players
    - Action collection with fallback for missing players
    - Turn state persistence and recovery
    """
    
    def __init__(self, 
                 action_timeout: float = 30.0,
                 turn_timeout: float = 120.0,
                 max_disconnection_time: float = 300.0):
        self.action_timeout = action_timeout
        self.turn_timeout = turn_timeout
        self.max_disconnection_time = max_disconnection_time
        
        self.current_turn: Optional[TurnState] = None
        self.players: Dict[str, Dict[str, Any]] = {}
        self.disconnected_players: Dict[str, float] = {}
        self.game_state: Dict[str, Any] = {}
        
    def add_player(self, player_id: str, initiative: int):
        """Add a player to the turn order with their initiative value."""
        self.players[player_id] = {
            'initiative': initiative,
            'connected': True,
            'last_action_time': time.time()
        }
        
    def remove_player(self, player_id: str):
        """Remove a player from the game."""
        if player_id in self.players:
            del self.players[player_id]
        if player_id in self.disconnected_players:
            del self.disconnected_players[player_id]
            
    def mark_player_disconnected(self, player_id: str):
        """Mark a player as disconnected but keep them in turn order."""
        if player_id in self.players:
            self.players[player_id]['connected'] = False
            self.disconnected_players[player_id] = time.time()
            logger.warning(f"Player {player_id} disconnected")
            
    def mark_player_reconnected(self, player_id: str):
        """Mark a player as reconnected."""
        if player_id in self.players:
            self.players[player_id]['connected'] = True
            if player_id in self.disconnected_players:
                del self.disconnected_players[player_id]
            logger.info(f"Player {player_id} reconnected")
            
    def get_initiative_order(self) -> List[str]:
        """Get current initiative order for active players."""
        active_players = []
        current_time = time.time()
        
        for player_id, player_data in self.players.items():
            # Remove players disconnected for too long
            if player_id in self.disconnected_players:
                disconnect_time = self.disconnected_players[player_id]
                if current_time - disconnect_time > self.max_disconnection_time:
                    logger.info(f"Removing player {player_id} - disconnected too long")
                    self.remove_player(player_id)
                    continue
                    
            active_players.append((player_id, player_data['initiative']))
            
        # Sort by initiative (higher goes first)
        active_players.sort(key=lambda x: x[1], reverse=True)
        return [player_id for player_id, _ in active_players]
        
    def start_new_turn(self) -> TurnState:
        """Start a new turn with current initiative order."""
        initiative_order = self.get_initiative_order()
        
        if not initiative_order:
            raise ValueError("No active players for turn")
            
        turn_number = (self.current_turn.turn_number + 1) if self.current_turn else 1
        
        self.current_turn = TurnState(
            turn_number=turn_number,
            phase=TurnPhase.INITIATIVE,
            initiative_order=initiative_order,
            collected_actions={},
            waiting_for=set(initiative_order),
            phase_timeout=time.time() + self.action_timeout,
            turn_started_at=time.time()
        )
        
        logger.info(f"Started turn {turn_number} with order: {initiative_order}")
        return self.current_turn
        
    def advance_to_action_collection(self):
        """Advance turn to action collection phase."""
        if not self.current_turn:
            raise ValueError("No active turn")
            
        self.current_turn.phase = TurnPhase.COLLECTING_ACTIONS
        self.current_turn.phase_timeout = time.time() + self.action_timeout
        self.current_turn.waiting_for = set(self.current_turn.initiative_order)
        
        # Remove disconnected players from waiting list
        for player_id in list(self.current_turn.waiting_for):
            if not self.players.get(player_id, {}).get('connected', False):
                self.current_turn.waiting_for.discard(player_id)
                logger.info(f"Not waiting for disconnected player {player_id}")
                
        logger.info(f"Collecting actions from: {self.current_turn.waiting_for}")
        
    def submit_player_action(self, player_id: str, action_type: str, data: Dict[str, Any]) -> bool:
        """Submit an action for a player during action collection phase."""
        if not self.current_turn:
            logger.warning(f"No active turn for action from {player_id}")
            return False
            
        if self.current_turn.phase != TurnPhase.COLLECTING_ACTIONS:
            logger.warning(f"Not in action collection phase for {player_id}")
            return False
            
        if player_id not in self.current_turn.waiting_for:
            logger.warning(f"Not waiting for action from {player_id}")
            return False
            
        # Get sequence number based on initiative order
        sequence_number = self.current_turn.initiative_order.index(player_id)
        
        action = PlayerAction(
            player_id=player_id,
            action_type=action_type,
            data=data,
            sequence_number=sequence_number,
            timestamp=time.time()
        )
        
        self.current_turn.collected_actions[player_id] = action
        self.current_turn.waiting_for.discard(player_id)
        self.players[player_id]['last_action_time'] = time.time()
        
        logger.info(f"Collected action from {player_id}: {action_type}")
        
        # Check if we have all actions
        if not self.current_turn.waiting_for:
            self._advance_to_resolution()
            
        return True
        
    def _advance_to_resolution(self):
        """Advance to action resolution phase."""
        if not self.current_turn:
            return
            
        self.current_turn.phase = TurnPhase.RESOLVING_ACTIONS
        self.current_turn.phase_timeout = time.time() + self.turn_timeout
        logger.info("Advancing to action resolution")
        
    def check_timeout(self) -> bool:
        """Check if current phase has timed out and handle accordingly."""
        if not self.current_turn:
            return False
            
        current_time = time.time()
        
        if current_time > self.current_turn.phase_timeout:
            logger.warning(f"Phase {self.current_turn.phase} timed out")
            
            if self.current_turn.phase == TurnPhase.COLLECTING_ACTIONS:
                # Handle timeout during action collection
                self._handle_action_collection_timeout()
                return True
                
            elif self.current_turn.phase == TurnPhase.RESOLVING_ACTIONS:
                # Force resolution timeout
                logger.error("Action resolution timed out - forcing turn end")
                self._force_turn_end()
                return True
                
        return False
        
    def _handle_action_collection_timeout(self):
        """Handle timeout during action collection - generate default actions."""
        missing_players = list(self.current_turn.waiting_for)
        
        for player_id in missing_players:
            # Generate default "pass" action for missing players
            default_action = PlayerAction(
                player_id=player_id,
                action_type="pass",
                data={"reason": "timeout"},
                sequence_number=self.current_turn.initiative_order.index(player_id),
                timestamp=time.time()
            )
            
            self.current_turn.collected_actions[player_id] = default_action
            logger.warning(f"Generated default action for {player_id} due to timeout")
            
        self.current_turn.waiting_for.clear()
        self._advance_to_resolution()
        
    def _force_turn_end(self):
        """Force the current turn to end due to timeout or error."""
        if self.current_turn:
            self.current_turn.phase = TurnPhase.END_TURN
            logger.warning(f"Force ended turn {self.current_turn.turn_number}")
            
    def get_actions_in_initiative_order(self) -> List[PlayerAction]:
        """Get all collected actions sorted by initiative order."""
        if not self.current_turn:
            return []
            
        actions = list(self.current_turn.collected_actions.values())
        actions.sort(key=lambda x: x.sequence_number)
        return actions
        
    def resolve_conflicts(self, actions: List[PlayerAction]) -> List[PlayerAction]:
        """
        Resolve conflicts between actions using strict initiative ordering.
        
        In a strict turn-based system, conflicts are resolved by initiative order:
        - Earlier initiative (lower sequence_number) wins
        - Invalid actions are filtered out
        - All actions maintain initiative ordering
        """
        resolved_actions = []
        occupied_positions = set()
        targeted_entities = {}
        
        # Process actions in initiative order
        for action in actions:
            action_valid = True
            
            # Movement conflict resolution
            if action.action_type == "move":
                target_pos = tuple(action.data.get("target_position", []))
                if target_pos in occupied_positions:
                    logger.info(f"Movement conflict: {action.player_id} blocked by earlier initiative")
                    action_valid = False
                else:
                    occupied_positions.add(target_pos)
                    
            # Attack conflict resolution - first attacker in initiative order
            elif action.action_type == "attack":
                target_id = action.data.get("target_id")
                if target_id:
                    if target_id not in targeted_entities:
                        targeted_entities[target_id] = action.player_id
                    # All attacks can proceed, but in initiative order
                    
            if action_valid:
                resolved_actions.append(action)
            else:
                # Create a "failed" action to maintain turn order
                failed_action = PlayerAction(
                    player_id=action.player_id,
                    action_type="failed",
                    data={"original_action": action.action_type, "reason": "conflict"},
                    sequence_number=action.sequence_number,
                    timestamp=action.timestamp
                )
                resolved_actions.append(failed_action)
                
        return resolved_actions
        
    def execute_turn_actions(self) -> Dict[str, Any]:
        """Execute all actions for the current turn in initiative order."""
        if not self.current_turn or self.current_turn.phase != TurnPhase.RESOLVING_ACTIONS:
            return {"error": "Not in resolution phase"}
            
        actions = self.get_actions_in_initiative_order()
        resolved_actions = self.resolve_conflicts(actions)
        
        results = {
            "turn_number": self.current_turn.turn_number,
            "actions_executed": [],
            "conflicts_resolved": 0,
            "initiative_order": self.current_turn.initiative_order
        }
        
        for action in resolved_actions:
            # Execute action based on type
            action_result = self._execute_single_action(action)
            results["actions_executed"].append({
                "player_id": action.player_id,
                "action_type": action.action_type,
                "sequence": action.sequence_number,
                "result": action_result
            })
            
            if action.action_type == "failed":
                results["conflicts_resolved"] += 1
                
        self.current_turn.phase = TurnPhase.APPLYING_RESULTS
        logger.info(f"Executed {len(resolved_actions)} actions in initiative order")
        
        return results
        
    def _execute_single_action(self, action: PlayerAction) -> Dict[str, Any]:
        """Execute a single action and return the result."""
        try:
            if action.action_type == "move":
                return self._execute_move_action(action)
            elif action.action_type == "attack":
                return self._execute_attack_action(action)
            elif action.action_type == "pass":
                return {"action": "pass", "success": True}
            elif action.action_type == "failed":
                return {"action": "failed", "success": False, "reason": action.data.get("reason")}
            else:
                return {"action": action.action_type, "success": False, "error": "unknown_action"}
                
        except Exception as e:
            logger.error(f"Error executing action {action.action_type} for {action.player_id}: {e}")
            return {"action": action.action_type, "success": False, "error": str(e)}
            
    def _execute_move_action(self, action: PlayerAction) -> Dict[str, Any]:
        """Execute a movement action."""
        # This would integrate with the actual game state system
        return {
            "action": "move",
            "success": True,
            "player_id": action.player_id,
            "new_position": action.data.get("target_position")
        }
        
    def _execute_attack_action(self, action: PlayerAction) -> Dict[str, Any]:
        """Execute an attack action."""
        # This would integrate with the actual combat system
        return {
            "action": "attack",
            "success": True,
            "attacker": action.player_id,
            "target": action.data.get("target_id"),
            "damage": action.data.get("damage", 0)
        }
        
    def complete_turn(self) -> bool:
        """Complete the current turn and prepare for the next."""
        if not self.current_turn:
            return False
            
        self.current_turn.phase = TurnPhase.END_TURN
        turn_duration = time.time() - self.current_turn.turn_started_at
        
        logger.info(f"Completed turn {self.current_turn.turn_number} in {turn_duration:.2f}s")
        
        # Clean up disconnected players who have been gone too long
        self._cleanup_long_disconnected_players()
        
        return True
        
    def _cleanup_long_disconnected_players(self):
        """Remove players who have been disconnected for too long."""
        current_time = time.time()
        to_remove = []
        
        for player_id, disconnect_time in self.disconnected_players.items():
            if current_time - disconnect_time > self.max_disconnection_time:
                to_remove.append(player_id)
                
        for player_id in to_remove:
            logger.info(f"Removing player {player_id} - disconnected for {self.max_disconnection_time}s")
            self.remove_player(player_id)
            
    def get_turn_status(self) -> Dict[str, Any]:
        """Get current turn status for client synchronization."""
        if not self.current_turn:
            return {"status": "no_active_turn"}
            
        return {
            "turn_number": self.current_turn.turn_number,
            "phase": self.current_turn.phase.value,
            "initiative_order": self.current_turn.initiative_order,
            "waiting_for": list(self.current_turn.waiting_for),
            "actions_collected": len(self.current_turn.collected_actions),
            "timeout_remaining": max(0, self.current_turn.phase_timeout - time.time()),
            "turn_duration": time.time() - self.current_turn.turn_started_at
        }