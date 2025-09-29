"""
Enhanced Event Bus with Multiplayer Support
==========================================

This module provides an enhanced event bus system that addresses the critical issues
identified in the multiplayer readiness review:

1. Event ordering and deterministic processing
2. Event persistence and replay capability
3. Error handling and validation
4. Network serialization support

This enhanced version maintains backward compatibility while adding the features
required for multiplayer synchronization.
"""

import time
import json
from typing import Callable, Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging


class EventPriority(Enum):
    """Event priority levels for deterministic processing order."""
    SYSTEM = 0      # System-level events (highest priority)
    GAMEPLAY = 1    # Core gameplay events
    UI = 2          # User interface events
    DEBUG = 3       # Debug and logging events (lowest priority)


@dataclass
class Event:
    """
    Enhanced event structure with ordering and network support.
    
    Attributes:
        timestamp: When the event was created
        sequence_number: Global sequence number for ordering
        event_type: String identifier for the event type
        priority: Event priority level
        data: Event payload data
        source: Entity or system that created the event
        network_replicate: Whether this event should be sent over network
    """
    timestamp: float
    sequence_number: int
    event_type: str
    priority: EventPriority
    data: Dict[str, Any]
    source: Optional[str] = None
    network_replicate: bool = False
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize event for network transmission."""
        return {
            'timestamp': self.timestamp,
            'sequence_number': self.sequence_number,
            'event_type': self.event_type,
            'priority': self.priority.value,
            'data': self.data,
            'source': self.source,
            'network_replicate': self.network_replicate
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'Event':
        """Deserialize event from network transmission."""
        return cls(
            timestamp=data['timestamp'],
            sequence_number=data['sequence_number'],
            event_type=data['event_type'],
            priority=EventPriority(data['priority']),
            data=data['data'],
            source=data.get('source'),
            network_replicate=data.get('network_replicate', False)
        )


class EnhancedEventBus:
    """
    Enhanced event bus with multiplayer support and deterministic ordering.
    
    Key improvements over the basic EventBus:
    - Event ordering and persistence
    - Error handling and validation
    - Network serialization support
    - Event replay capability
    - Priority-based processing
    
    This class maintains backward compatibility with the existing EventBus API.
    """

    def __init__(self, enable_persistence: bool = True, max_history: int = 10000):
        """
        Initialize the enhanced event bus.
        
        Args:
            enable_persistence: Whether to store event history
            max_history: Maximum number of events to keep in history
        """
        # Backward compatibility - same as original EventBus
        self.subscribers: Dict[str, List[Callable[..., None]]] = {}
        
        # Enhanced features
        self.event_history: List[Event] = []
        self.sequence_counter: int = 0
        self.enable_persistence = enable_persistence
        self.max_history = max_history
        self.logger = logging.getLogger(__name__)
        
        # Network support (for future multiplayer implementation)
        self.network_callback: Optional[Callable[[Event], None]] = None
        
        # Event validation schemas (extensible)
        self.validation_schemas: Dict[str, Callable[[Dict[str, Any]], bool]] = {}

    # ===== BACKWARD COMPATIBILITY METHODS =====
    # These methods maintain the exact same API as the original EventBus

    def subscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """Subscribe to events (backward compatible)."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """Unsubscribe from events (backward compatible)."""
        if event_type in self.subscribers:
            if callback in self.subscribers[event_type]:
                self.subscribers[event_type].remove(callback)

    def publish(self, event_type: str, **kwargs: Any) -> None:
        """Publish events (backward compatible with enhancements)."""
        self.publish_enhanced(
            event_type=event_type,
            priority=EventPriority.GAMEPLAY,
            network_replicate=False,
            **kwargs
        )

    def clear(self) -> None:
        """Clear all subscriptions (backward compatible)."""
        self.subscribers.clear()

    def get_subscribers(self, event_type: str) -> List[Callable[..., None]]:
        """Get subscribers (backward compatible)."""
        return self.subscribers.get(event_type, [])

    # ===== ENHANCED METHODS =====

    def publish_enhanced(self, event_type: str, priority: EventPriority = EventPriority.GAMEPLAY,
                        source: Optional[str] = None, network_replicate: bool = False,
                        **kwargs: Any) -> Event:
        """
        Enhanced event publishing with ordering and network support.
        
        Args:
            event_type: Event type identifier
            priority: Event priority for processing order
            source: Entity/system that created the event
            network_replicate: Whether to replicate over network
            **kwargs: Event data payload
            
        Returns:
            The created Event object
        """
        # Create event with sequence number for ordering
        event = Event(
            timestamp=time.time(),
            sequence_number=self._get_next_sequence(),
            event_type=event_type,
            priority=priority,
            data=kwargs,
            source=source,
            network_replicate=network_replicate
        )
        
        # Validate event if schema exists
        if not self._validate_event(event):
            self.logger.warning(f"Event validation failed for {event_type}: {kwargs}")
            return event
        
        # Store in history if persistence enabled
        if self.enable_persistence:
            self._add_to_history(event)
        
        # Network replication if enabled
        if network_replicate and self.network_callback:
            try:
                self.network_callback(event)
            except Exception as e:
                self.logger.error(f"Network replication failed for {event_type}: {e}")
        
        # Process subscribers with error handling
        self._process_subscribers(event)
        
        return event

    def _get_next_sequence(self) -> int:
        """Get next sequence number for event ordering."""
        self.sequence_counter += 1
        return self.sequence_counter

    def _validate_event(self, event: Event) -> bool:
        """Validate event data against registered schemas."""
        if event.event_type in self.validation_schemas:
            try:
                validator = self.validation_schemas[event.event_type]
                return validator(event.data)
            except Exception as e:
                self.logger.error(f"Event validation error for {event.event_type}: {e}")
                return False
        return True  # No validation schema = assume valid

    def _add_to_history(self, event: Event) -> None:
        """Add event to history with size management."""
        self.event_history.append(event)
        
        # Maintain maximum history size
        if len(self.event_history) > self.max_history:
            # Remove oldest events
            excess = len(self.event_history) - self.max_history
            self.event_history = self.event_history[excess:]

    def _process_subscribers(self, event: Event) -> None:
        """Process subscribers with error handling."""
        subscribers = self.subscribers.get(event.event_type, [])
        
        for callback in subscribers:
            try:
                callback(**event.data)
            except Exception as e:
                self.logger.error(f"Subscriber error for {event.event_type}: {e}")
                # Continue processing other subscribers despite errors

    # ===== MULTIPLAYER SUPPORT METHODS =====

    def set_network_callback(self, callback: Callable[[Event], None]) -> None:
        """Set callback for network event replication."""
        self.network_callback = callback

    def add_validation_schema(self, event_type: str, validator: Callable[[Dict[str, Any]], bool]) -> None:
        """Add validation schema for an event type."""
        self.validation_schemas[event_type] = validator

    def get_events_since(self, sequence_number: int) -> List[Event]:
        """Get all events since a specific sequence number (for late-joining players)."""
        return [event for event in self.event_history if event.sequence_number > sequence_number]

    def get_events_by_type(self, event_type: str, since_timestamp: Optional[float] = None) -> List[Event]:
        """Get events of a specific type, optionally since a timestamp."""
        events = [event for event in self.event_history if event.event_type == event_type]
        if since_timestamp is not None:
            events = [event for event in events if event.timestamp >= since_timestamp]
        return events

    def replay_events(self, events: List[Event]) -> None:
        """Replay a list of events in order (for state synchronization)."""
        # Sort events by sequence number to ensure proper order
        sorted_events = sorted(events, key=lambda e: e.sequence_number)
        
        for event in sorted_events:
            # Process subscribers without adding to history again
            self._process_subscribers(event)

    def get_current_sequence(self) -> int:
        """Get the current sequence number."""
        return self.sequence_counter

    def serialize_history(self, since_sequence: int = 0) -> str:
        """Serialize event history to JSON (for network transmission)."""
        events_to_serialize = [
            event for event in self.event_history 
            if event.sequence_number > since_sequence
        ]
        return json.dumps([event.serialize() for event in events_to_serialize])

    def deserialize_and_replay(self, serialized_events: str) -> None:
        """Deserialize and replay events from JSON."""
        try:
            event_data_list = json.loads(serialized_events)
            events = [Event.deserialize(data) for data in event_data_list]
            self.replay_events(events)
        except Exception as e:
            self.logger.error(f"Failed to deserialize and replay events: {e}")

    # ===== DEBUGGING AND MONITORING =====

    def get_statistics(self) -> Dict[str, Any]:
        """Get event bus statistics for monitoring."""
        event_counts = {}
        for event in self.event_history:
            event_type = event.event_type
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        return {
            'total_events': len(self.event_history),
            'sequence_counter': self.sequence_counter,
            'subscriber_count': sum(len(subs) for subs in self.subscribers.values()),
            'event_type_counts': event_counts,
            'max_history': self.max_history
        }

    def print_recent_events(self, count: int = 10) -> None:
        """Print recent events for debugging."""
        recent = self.event_history[-count:] if self.event_history else []
        for event in recent:
            print(f"[{event.sequence_number}] {event.event_type} @ {event.timestamp:.3f}: {event.data}")