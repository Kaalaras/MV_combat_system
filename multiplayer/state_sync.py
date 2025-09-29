"""
Phase 2: Game State Synchronization System
Implements turn-based action ordering, state delta broadcasting, and conflict resolution.
"""

import uuid
import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque

from .models import GameCommand, Player, GameRoom

logger = logging.getLogger(__name__)


class TurnPhase(Enum):
    """Different phases of a turn"""
    INITIATIVE = "initiative"
    ACTIONS = "actions"
    RESOLUTION = "resolution"
    END_TURN = "end_turn"


class ActionPriority(Enum):
    """Action execution priorities"""
    IMMEDIATE = 1      # Chat, surrender
    HIGH = 2          # Defensive actions, reactions
    NORMAL = 3        # Movement, attacks
    LOW = 4           # End turn, cleanup


@dataclass
class StateDelta:
    """Represents a change in game state"""
    delta_id: str
    turn_id: int
    sequence_number: int
    timestamp: datetime
    entity_changes: Dict[str, Any]  # entity_id -> component changes
    events: List[Dict[str, Any]]    # Game events generated
    player_id: str
    command_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'delta_id': self.delta_id,
            'turn_id': self.turn_id,
            'sequence_number': self.sequence_number,
            'timestamp': self.timestamp.isoformat(),
            'entity_changes': self.entity_changes,
            'events': self.events,
            'player_id': self.player_id,
            'command_id': self.command_id
        }


@dataclass
class TurnState:
    """State for a single turn"""
    turn_id: int
    phase: TurnPhase
    current_player_id: Optional[str]
    pending_actions: Dict[str, List[GameCommand]]  # player_id -> commands
    executed_actions: List[str]  # command_ids
    turn_start: datetime
    turn_deadline: Optional[datetime]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'turn_id': self.turn_id,
            'phase': self.phase.value,
            'current_player_id': self.current_player_id,
            'pending_actions': {
                pid: [cmd.dict() for cmd in cmds] 
                for pid, cmds in self.pending_actions.items()
            },
            'executed_actions': self.executed_actions,
            'turn_start': self.turn_start.isoformat(),
            'turn_deadline': self.turn_deadline.isoformat() if self.turn_deadline else None
        }


class TurnOrderManager:
    """Manages turn-based action ordering and execution"""
    
    def __init__(self):
        self.current_turn: Optional[TurnState] = None
        self.turn_history: List[TurnState] = []
        self.sequence_counter = 0
        self.initiative_order: List[str] = []  # player_ids in order
        
    async def start_new_turn(
        self, 
        turn_id: int, 
        initiative_order: List[str],
        turn_timeout: Optional[int] = 300  # 5 minutes default
    ) -> TurnState:
        """Start a new turn with given initiative order"""
        if self.current_turn:
            # Archive current turn
            self.turn_history.append(self.current_turn)
        
        turn_deadline = None
        if turn_timeout:
            from datetime import timedelta
            turn_deadline = datetime.utcnow() + timedelta(seconds=turn_timeout)
        
        self.current_turn = TurnState(
            turn_id=turn_id,
            phase=TurnPhase.INITIATIVE,
            current_player_id=initiative_order[0] if initiative_order else None,
            pending_actions={pid: [] for pid in initiative_order},
            executed_actions=[],
            turn_start=datetime.utcnow(),
            turn_deadline=turn_deadline
        )
        
        self.initiative_order = initiative_order.copy()
        self.sequence_counter = 0
        
        logger.info(f"Started turn {turn_id} with initiative order: {initiative_order}")
        return self.current_turn
    
    async def queue_action(
        self, 
        player_id: str, 
        command: GameCommand
    ) -> bool:
        """Queue an action for execution"""
        if not self.current_turn:
            return False
        
        if player_id not in self.current_turn.pending_actions:
            return False
        
        # Add sequence number
        command.sequence_number = self._get_next_sequence()
        command.turn_id = self.current_turn.turn_id
        
        # Queue by priority
        self.current_turn.pending_actions[player_id].append(command)
        self.current_turn.pending_actions[player_id].sort(
            key=lambda cmd: self._get_action_priority(cmd).value
        )
        
        logger.info(f"Queued action {command.command_id} for player {player_id}")
        return True
    
    async def get_next_action(self) -> Optional[GameCommand]:
        """Get the next action to execute based on turn order and priority"""
        if not self.current_turn or self.current_turn.phase != TurnPhase.ACTIONS:
            return None
        
        # Get actions from current player first
        if self.current_turn.current_player_id:
            current_player_actions = self.current_turn.pending_actions.get(
                self.current_turn.current_player_id, []
            )
            if current_player_actions:
                return current_player_actions.pop(0)
        
        # Then check all players for high-priority actions (reactions, etc.)
        for player_id, actions in self.current_turn.pending_actions.items():
            high_priority_actions = [
                action for action in actions 
                if self._get_action_priority(action) in [ActionPriority.IMMEDIATE, ActionPriority.HIGH]
            ]
            if high_priority_actions:
                # Remove from pending and return
                for action in high_priority_actions:
                    actions.remove(action)
                return high_priority_actions[0]
        
        return None
    
    async def advance_turn_phase(self) -> Optional[TurnPhase]:
        """Advance to the next turn phase"""
        if not self.current_turn:
            return None
        
        if self.current_turn.phase == TurnPhase.INITIATIVE:
            self.current_turn.phase = TurnPhase.ACTIONS
        elif self.current_turn.phase == TurnPhase.ACTIONS:
            self.current_turn.phase = TurnPhase.RESOLUTION
        elif self.current_turn.phase == TurnPhase.RESOLUTION:
            self.current_turn.phase = TurnPhase.END_TURN
        else:
            # Turn complete
            return None
        
        return self.current_turn.phase
    
    async def advance_current_player(self) -> Optional[str]:
        """Move to next player in initiative order"""
        if not self.current_turn or not self.initiative_order:
            return None
        
        current_idx = 0
        if self.current_turn.current_player_id:
            try:
                current_idx = self.initiative_order.index(self.current_turn.current_player_id)
            except ValueError:
                pass
        
        next_idx = (current_idx + 1) % len(self.initiative_order)
        self.current_turn.current_player_id = self.initiative_order[next_idx]
        
        return self.current_turn.current_player_id
    
    def _get_next_sequence(self) -> int:
        """Get next sequence number"""
        self.sequence_counter += 1
        return self.sequence_counter
    
    def _get_action_priority(self, command: GameCommand) -> ActionPriority:
        """Determine action priority for execution order"""
        if command.command_type.value in ['chat', 'surrender']:
            return ActionPriority.IMMEDIATE
        elif command.command_type.value in ['defend', 'dodge', 'reaction']:
            return ActionPriority.HIGH
        elif command.command_type.value in ['move', 'attack', 'use_discipline']:
            return ActionPriority.NORMAL
        else:
            return ActionPriority.LOW


class StateDeltaManager:
    """Manages state changes and broadcasting"""
    
    def __init__(self):
        self.deltas: Dict[int, List[StateDelta]] = {}  # turn_id -> deltas
        self.delta_history: List[StateDelta] = []
        self.subscribers: Set[str] = set()  # player_ids
        
    async def create_delta(
        self,
        turn_id: int,
        sequence_number: int,
        entity_changes: Dict[str, Any],
        events: List[Dict[str, Any]],
        player_id: str,
        command_id: str
    ) -> StateDelta:
        """Create a new state delta"""
        delta = StateDelta(
            delta_id=str(uuid.uuid4()),
            turn_id=turn_id,
            sequence_number=sequence_number,
            timestamp=datetime.utcnow(),
            entity_changes=entity_changes,
            events=events,
            player_id=player_id,
            command_id=command_id
        )
        
        # Store delta
        if turn_id not in self.deltas:
            self.deltas[turn_id] = []
        self.deltas[turn_id].append(delta)
        self.delta_history.append(delta)
        
        # Keep history manageable (last 1000 deltas)
        if len(self.delta_history) > 1000:
            self.delta_history = self.delta_history[-1000:]
        
        logger.info(f"Created delta {delta.delta_id} for turn {turn_id}, sequence {sequence_number}")
        return delta
    
    async def get_deltas_since(
        self, 
        turn_id: int, 
        sequence_number: int
    ) -> List[StateDelta]:
        """Get all deltas since a specific turn/sequence point"""
        result = []
        
        # Get deltas from specified turn onwards
        for tid, deltas in self.deltas.items():
            if tid < turn_id:
                continue
            elif tid == turn_id:
                # Filter by sequence number
                result.extend([d for d in deltas if d.sequence_number > sequence_number])
            else:
                # Include all deltas from later turns
                result.extend(deltas)
        
        return sorted(result, key=lambda d: (d.turn_id, d.sequence_number))
    
    async def compact_deltas(self, keep_turns: int = 10):
        """Remove old deltas to save memory"""
        if not self.deltas:
            return
        
        max_turn = max(self.deltas.keys())
        cutoff_turn = max_turn - keep_turns
        
        # Remove old turns
        to_remove = [turn_id for turn_id in self.deltas.keys() if turn_id < cutoff_turn]
        for turn_id in to_remove:
            del self.deltas[turn_id]
        
        # Also clean delta_history
        self.delta_history = [
            d for d in self.delta_history 
            if d.turn_id >= cutoff_turn
        ]
        
        logger.info(f"Compacted deltas, removed {len(to_remove)} old turns")


class ConflictResolver:
    """Resolves conflicts between simultaneous actions"""
    
    def __init__(self):
        self.resolution_rules: Dict[str, callable] = {
            'movement_conflict': self._resolve_movement_conflict,
            'target_conflict': self._resolve_target_conflict,
            'resource_conflict': self._resolve_resource_conflict,
            'timing_conflict': self._resolve_timing_conflict,
        }
    
    async def detect_conflicts(
        self, 
        actions: List[GameCommand]
    ) -> List[Dict[str, Any]]:
        """Detect conflicts between actions"""
        conflicts = []
        
        # Check for movement conflicts (multiple entities to same position)
        movement_conflicts = await self._detect_movement_conflicts(actions)
        conflicts.extend(movement_conflicts)
        
        # Check for target conflicts (multiple attacks on same target)
        target_conflicts = await self._detect_target_conflicts(actions)
        conflicts.extend(target_conflicts)
        
        # Check for resource conflicts (multiple uses of limited resources)
        resource_conflicts = await self._detect_resource_conflicts(actions)
        conflicts.extend(resource_conflicts)
        
        return conflicts
    
    async def resolve_conflicts(
        self, 
        conflicts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Resolve detected conflicts"""
        resolutions = []
        
        for conflict in conflicts:
            conflict_type = conflict.get('type')
            if conflict_type in self.resolution_rules:
                resolution = await self.resolution_rules[conflict_type](conflict)
                resolutions.append(resolution)
            else:
                # Default resolution - initiative order determines winner
                actions = conflict.get('actions', [])
                if actions:
                    # Sort by sequence number (initiative order)
                    actions.sort(key=lambda a: a.get('sequence_number', 0))
                    resolution = {
                        'conflict_id': conflict.get('conflict_id'),
                        'resolution_type': 'initiative_order',
                        'winner': actions[0].get('command_id'),
                        'losers': [
                            action.get('command_id') 
                            for action in actions[1:]
                        ],
                        'details': 'Conflict resolved by initiative order'
                    }
                else:
                    resolution = {
                        'conflict_id': conflict.get('conflict_id'),
                        'resolution_type': 'no_action',
                        'details': 'No actions to resolve'
                    }
                resolutions.append(resolution)
        
        return resolutions
    
    async def _detect_movement_conflicts(self, actions: List[GameCommand]) -> List[Dict[str, Any]]:
        """Detect movement conflicts"""
        conflicts = []
        position_map: Dict[tuple, List[GameCommand]] = {}
        
        for action in actions:
            if action.command_type.value == 'move' and action.payload:
                target_pos = (action.payload.get('x', 0), action.payload.get('y', 0))
                if target_pos not in position_map:
                    position_map[target_pos] = []
                position_map[target_pos].append(action)
        
        # Find positions with multiple movement commands
        for position, commands in position_map.items():
            if len(commands) > 1:
                conflicts.append({
                    'conflict_id': str(uuid.uuid4()),
                    'type': 'movement_conflict',
                    'position': position,
                    'actions': [cmd.dict() for cmd in commands],
                    'severity': 'high'
                })
        
        return conflicts
    
    async def _detect_target_conflicts(self, actions: List[GameCommand]) -> List[Dict[str, Any]]:
        """Detect target conflicts"""
        conflicts = []
        target_map: Dict[str, List[GameCommand]] = {}
        
        for action in actions:
            if action.command_type.value == 'attack' and action.payload:
                target_id = action.payload.get('target_id')
                if target_id:
                    if target_id not in target_map:
                        target_map[target_id] = []
                    target_map[target_id].append(action)
        
        # Multiple attacks on same target is usually fine, just note it
        for target_id, commands in target_map.items():
            if len(commands) > 2:  # More than 2 attacks might be worth noting
                conflicts.append({
                    'conflict_id': str(uuid.uuid4()),
                    'type': 'target_conflict',
                    'target_id': target_id,
                    'actions': [cmd.dict() for cmd in commands],
                    'severity': 'low'
                })
        
        return conflicts
    
    async def _detect_resource_conflicts(self, actions: List[GameCommand]) -> List[Dict[str, Any]]:
        """Detect resource conflicts"""
        conflicts = []
        # This would need game state knowledge to implement fully
        # For now, return empty list
        return conflicts
    
    async def _resolve_movement_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve movement conflict - highest initiative wins"""
        actions = conflict.get('actions', [])
        if not actions:
            return {'conflict_id': conflict.get('conflict_id'), 'resolution_type': 'no_action'}
        
        # Sort by sequence number (earlier actions win)
        actions.sort(key=lambda a: a.get('sequence_number', 0))
        
        return {
            'conflict_id': conflict.get('conflict_id'),
            'resolution_type': 'initiative_order',
            'winner': actions[0].get('command_id'),
            'losers': [action.get('command_id') for action in actions[1:]],
            'details': 'Movement conflict resolved by initiative order'
        }
    
    async def _resolve_target_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve target conflict - initiative order determines attack sequence"""
        actions = conflict.get('actions', [])
        if not actions:
            return {'conflict_id': conflict.get('conflict_id'), 'resolution_type': 'no_action'}
        
        # Sort by sequence number (initiative order)
        actions.sort(key=lambda a: a.get('sequence_number', 0))
        
        return {
            'conflict_id': conflict.get('conflict_id'),
            'resolution_type': 'initiative_sequence',
            'execution_order': [action.get('command_id') for action in actions],
            'details': 'Multiple attacks resolved in initiative order'
        }
    
    async def _resolve_resource_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve resource conflict - initiative order determines access"""
        actions = conflict.get('actions', [])
        if not actions:
            return {'conflict_id': conflict.get('conflict_id'), 'resolution_type': 'no_action'}
        
        # Sort by sequence number (initiative order)
        actions.sort(key=lambda a: a.get('sequence_number', 0))
        
        return {
            'conflict_id': conflict.get('conflict_id'),
            'resolution_type': 'initiative_order',
            'winner': actions[0].get('command_id'),
            'losers': [action.get('command_id') for action in actions[1:]],
            'details': 'Resource conflict resolved by initiative order'
        }
    
    async def _resolve_timing_conflict(self, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve timing conflict - initiative order determines execution sequence"""
        actions = conflict.get('actions', [])
        if not actions:
            return {'conflict_id': conflict.get('conflict_id'), 'resolution_type': 'no_action'}
        
        # Sort by sequence number (initiative order)
        actions.sort(key=lambda a: a.get('sequence_number', 0))
        
        return {
            'conflict_id': conflict.get('conflict_id'),
            'resolution_type': 'initiative_sequence',
            'execution_order': [action.get('command_id') for action in actions],
            'details': 'Timing conflict resolved by initiative order'
        }


class GameStateSynchronizer:
    """Main coordinator for game state synchronization"""
    
    def __init__(self):
        self.turn_manager = TurnOrderManager()
        self.delta_manager = StateDeltaManager()
        self.conflict_resolver = ConflictResolver()
        self.rooms: Dict[str, Any] = {}  # room_id -> room state
        self.active_games: Dict[str, bool] = {}  # room_id -> is_active
        
    async def initialize_game(
        self, 
        room_id: str, 
        players: List[Player], 
        game_config: Dict[str, Any]
    ) -> bool:
        """Initialize a new game session"""
        try:
            # Set up initial turn order based on initiative
            initiative_order = await self._calculate_initiative_order(players, game_config)
            
            # Start first turn
            await self.turn_manager.start_new_turn(
                turn_id=1,
                initiative_order=initiative_order,
                turn_timeout=game_config.get('turn_timeout', 300)
            )
            
            self.active_games[room_id] = True
            
            logger.info(f"Initialized game in room {room_id} with {len(players)} players")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize game in room {room_id}: {e}")
            return False
    
    async def process_player_action(
        self, 
        room_id: str,
        player_id: str, 
        command: GameCommand
    ) -> Dict[str, Any]:
        """Process a player action and generate state delta"""
        if room_id not in self.active_games or not self.active_games[room_id]:
            return {'success': False, 'reason': 'Game not active'}
        
        # Queue the action
        success = await self.turn_manager.queue_action(player_id, command)
        if not success:
            return {'success': False, 'reason': 'Failed to queue action'}
        
        # Try to execute queued actions
        execution_results = await self._execute_pending_actions(room_id)
        
        return {
            'success': True,
            'command_id': command.command_id,
            'queued': True,
            'execution_results': execution_results
        }
    
    async def get_state_updates(
        self, 
        room_id: str, 
        since_turn: int = 0, 
        since_sequence: int = 0
    ) -> Dict[str, Any]:
        """Get state updates since specified point"""
        deltas = await self.delta_manager.get_deltas_since(since_turn, since_sequence)
        current_turn = self.turn_manager.current_turn
        
        return {
            'deltas': [delta.to_dict() for delta in deltas],
            'current_turn': current_turn.to_dict() if current_turn else None,
            'last_turn': deltas[-1].turn_id if deltas else since_turn,
            'last_sequence': deltas[-1].sequence_number if deltas else since_sequence
        }
    
    async def advance_turn(self, room_id: str) -> Dict[str, Any]:
        """Advance to next turn phase or next turn"""
        if room_id not in self.active_games:
            return {'success': False, 'reason': 'Game not found'}
        
        # Execute any remaining actions
        await self._execute_pending_actions(room_id)
        
        # Try to advance phase
        next_phase = await self.turn_manager.advance_turn_phase()
        
        if next_phase is None:
            # Turn complete, start new turn
            current_turn = self.turn_manager.current_turn
            if current_turn:
                new_turn_id = current_turn.turn_id + 1
                await self.turn_manager.start_new_turn(
                    turn_id=new_turn_id,
                    initiative_order=self.turn_manager.initiative_order,
                    turn_timeout=300
                )
                
                # Create turn advance delta
                delta = await self.delta_manager.create_delta(
                    turn_id=new_turn_id,
                    sequence_number=0,
                    entity_changes={},
                    events=[{
                        'type': 'turn_started',
                        'turn_id': new_turn_id,
                        'current_player': self.turn_manager.current_turn.current_player_id
                    }],
                    player_id='system',
                    command_id='turn_advance'
                )
                
                return {
                    'success': True, 
                    'new_turn': new_turn_id,
                    'delta': delta.to_dict()
                }
        
        return {
            'success': True, 
            'phase': next_phase.value if next_phase else 'complete',
            'turn_id': self.turn_manager.current_turn.turn_id if self.turn_manager.current_turn else 0
        }
    
    async def _execute_pending_actions(self, room_id: str) -> List[Dict[str, Any]]:
        """Execute all pending actions for current turn phase"""
        results = []
        
        while True:
            # Get next action to execute
            action = await self.turn_manager.get_next_action()
            if not action:
                break
            
            # Execute action and create delta
            execution_result = await self._execute_single_action(room_id, action)
            results.append(execution_result)
        
        return results
    
    async def _execute_single_action(
        self, 
        room_id: str, 
        command: GameCommand
    ) -> Dict[str, Any]:
        """Execute a single game command"""
        try:
            # This would integrate with the actual game engine
            # For now, create a mock execution result
            
            entity_changes = {}
            events = []
            
            if command.command_type.value == 'move':
                entity_changes[command.player_id] = {
                    'position': {
                        'x': command.payload.get('x', 0),
                        'y': command.payload.get('y', 0)
                    }
                }
                events.append({
                    'type': 'entity_moved',
                    'entity_id': command.player_id,
                    'from': command.payload.get('from', {}),
                    'to': command.payload.get('to', {})
                })
            
            elif command.command_type.value == 'attack':
                # Mock attack result
                events.append({
                    'type': 'attack_executed',
                    'attacker': command.player_id,
                    'target': command.payload.get('target_id'),
                    'damage': command.payload.get('damage', 0)
                })
            
            # Create state delta
            delta = await self.delta_manager.create_delta(
                turn_id=command.turn_id,
                sequence_number=command.sequence_number,
                entity_changes=entity_changes,
                events=events,
                player_id=command.player_id,
                command_id=command.command_id
            )
            
            return {
                'success': True,
                'command_id': command.command_id,
                'delta': delta.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Failed to execute command {command.command_id}: {e}")
            return {
                'success': False,
                'command_id': command.command_id,
                'error': str(e)
            }
    
    async def _calculate_initiative_order(
        self, 
        players: List[Player], 
        game_config: Dict[str, Any]
    ) -> List[str]:
        """Calculate initiative order for players"""
        # Simple implementation - could be enhanced with actual initiative rolls
        import random
        
        player_ids = [p.id for p in players if not p.team or p.team != 'spectator']
        random.shuffle(player_ids)  # Random order for now
        
        return player_ids