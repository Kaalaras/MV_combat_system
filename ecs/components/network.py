"""
Network Components for Multiplayer Support
==========================================

This module provides network-aware components required for multiplayer
implementation, addressing the issues identified in the ECS architecture review.

Key components:
- NetworkComponent: Entity ownership and authority management
- SerializableComponent: Base class for network serialization
- ReplicationComponent: Controls what gets synchronized over network
"""

from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass
from enum import Enum
import time


class Authority(Enum):
    """Defines who has authority over an entity's state."""
    CLIENT = "client"      # Client has authority (e.g., player character)
    SERVER = "server"      # Server has authority (e.g., NPCs, environment)
    SHARED = "shared"      # Shared authority (e.g., projectiles)


class SerializationProtocol(Protocol):
    """Protocol that serializable components must implement."""
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize component to dictionary for network transmission."""
        ...
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'SerializationProtocol':
        """Deserialize component from network data."""
        ...


@dataclass
class NetworkComponent:
    """
    Component that marks entities for network synchronization.
    
    This component defines ownership, authority, and sync settings for entities
    in a multiplayer environment.
    
    Attributes:
        owner_id: ID of the client/player that owns this entity
        authority: Who has authority over this entity's state
        last_sync: Timestamp of last synchronization
        sync_frequency: How often to sync (seconds between syncs)
        priority: Network priority (higher = more frequent updates)
        replicate: Whether this entity should be replicated at all
    """
    owner_id: str
    authority: Authority = Authority.SERVER
    last_sync: float = 0.0
    sync_frequency: float = 0.1  # 10 times per second by default
    priority: int = 1  # 1-5, higher = more important
    replicate: bool = True
    
    def needs_sync(self) -> bool:
        """Check if this entity needs synchronization based on time."""
        current_time = time.time()
        return (current_time - self.last_sync) >= self.sync_frequency
    
    def mark_synced(self) -> None:
        """Mark entity as synchronized (update last_sync timestamp)."""
        self.last_sync = time.time()
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize network component for transmission."""
        return {
            'owner_id': self.owner_id,
            'authority': self.authority.value,
            'last_sync': self.last_sync,
            'sync_frequency': self.sync_frequency,
            'priority': self.priority,
            'replicate': self.replicate
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'NetworkComponent':
        """Deserialize network component from transmission."""
        return cls(
            owner_id=data['owner_id'],
            authority=Authority(data['authority']),
            last_sync=data.get('last_sync', 0.0),
            sync_frequency=data.get('sync_frequency', 0.1),
            priority=data.get('priority', 1),
            replicate=data.get('replicate', True)
        )


@dataclass
class ReplicationComponent:
    """
    Component that controls which aspects of an entity are replicated.
    
    This allows fine-grained control over what data is synchronized,
    reducing bandwidth usage.
    
    Attributes:
        replicate_position: Sync position changes
        replicate_health: Sync health/damage changes  
        replicate_equipment: Sync equipment changes
        replicate_conditions: Sync status conditions
        replicate_animations: Sync animation states
        custom_fields: Additional custom fields to replicate
    """
    replicate_position: bool = True
    replicate_health: bool = True
    replicate_equipment: bool = True
    replicate_conditions: bool = True
    replicate_animations: bool = False
    custom_fields: Dict[str, bool] = None
    
    def __post_init__(self):
        if self.custom_fields is None:
            self.custom_fields = {}
    
    def should_replicate(self, field_name: str) -> bool:
        """Check if a specific field should be replicated."""
        if field_name in self.custom_fields:
            return self.custom_fields[field_name]
        
        field_map = {
            'position': self.replicate_position,
            'health': self.replicate_health,
            'equipment': self.replicate_equipment,
            'conditions': self.replicate_conditions,
            'animations': self.replicate_animations
        }
        
        return field_map.get(field_name, False)
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize replication settings."""
        return {
            'replicate_position': self.replicate_position,
            'replicate_health': self.replicate_health,
            'replicate_equipment': self.replicate_equipment,
            'replicate_conditions': self.replicate_conditions,
            'replicate_animations': self.replicate_animations,
            'custom_fields': self.custom_fields
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'ReplicationComponent':
        """Deserialize replication settings."""
        return cls(
            replicate_position=data.get('replicate_position', True),
            replicate_health=data.get('replicate_health', True),
            replicate_equipment=data.get('replicate_equipment', True),
            replicate_conditions=data.get('replicate_conditions', True),
            replicate_animations=data.get('replicate_animations', False),
            custom_fields=data.get('custom_fields', {})
        )


class SerializableComponent:
    """
    Base class for components that can be serialized for network transmission.
    
    All components that need to be synchronized over the network should
    inherit from this class and implement the required methods.
    """
    
    def serialize(self) -> Dict[str, Any]:
        """
        Serialize component data for network transmission.
        
        Returns:
            Dictionary containing component data
        """
        raise NotImplementedError("Subclasses must implement serialize()")
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'SerializableComponent':
        """
        Deserialize component from network data.
        
        Args:
            data: Dictionary containing component data
            
        Returns:
            New component instance
        """
        raise NotImplementedError("Subclasses must implement deserialize()")
    
    def get_dirty_fields(self) -> Dict[str, Any]:
        """
        Get fields that have changed since last sync (optional optimization).
        
        This allows delta synchronization to reduce bandwidth.
        Default implementation returns all data.
        
        Returns:
            Dictionary of changed fields
        """
        return self.serialize()
    
    def mark_clean(self) -> None:
        """Mark all fields as synchronized (optional optimization)."""
        pass  # Override in subclasses that implement dirty tracking


@dataclass
class NetworkStateComponent:
    """
    Component that tracks network synchronization state for an entity.
    
    This component is automatically managed by the network system
    and tracks sync status, conflicts, and prediction state.
    """
    is_predicted: bool = False  # Client-side prediction active
    server_timestamp: float = 0.0  # Last confirmed server state timestamp
    client_timestamp: float = 0.0  # Last client state timestamp
    has_conflicts: bool = False  # Whether there are sync conflicts
    pending_corrections: Dict[str, Any] = None  # Server corrections pending
    
    def __post_init__(self):
        if self.pending_corrections is None:
            self.pending_corrections = {}
    
    def add_pending_correction(self, field: str, server_value: Any) -> None:
        """Add a server correction for a field."""
        self.pending_corrections[field] = server_value
        self.has_conflicts = True
    
    def clear_corrections(self) -> None:
        """Clear all pending corrections."""
        self.pending_corrections.clear()
        self.has_conflicts = False
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize network state."""
        return {
            'is_predicted': self.is_predicted,
            'server_timestamp': self.server_timestamp,
            'client_timestamp': self.client_timestamp,
            'has_conflicts': self.has_conflicts,
            'pending_corrections': self.pending_corrections
        }
    
    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'NetworkStateComponent':
        """Deserialize network state."""
        return cls(
            is_predicted=data.get('is_predicted', False),
            server_timestamp=data.get('server_timestamp', 0.0),
            client_timestamp=data.get('client_timestamp', 0.0),
            has_conflicts=data.get('has_conflicts', False),
            pending_corrections=data.get('pending_corrections', {})
        )


# Utility functions for network component management

def make_entity_networkable(entity_id: str, owner_id: str, 
                           authority: Authority = Authority.SERVER,
                           ecs_manager=None) -> None:
    """
    Add network components to an entity to make it multiplayer-ready.
    
    Args:
        entity_id: The entity to make networkable
        owner_id: Who owns this entity
        authority: Who has authority over this entity
        ecs_manager: ECS manager to add components to
    """
    if ecs_manager is None:
        return
        
    network_comp = NetworkComponent(owner_id=owner_id, authority=authority)
    replication_comp = ReplicationComponent()  # Default settings
    state_comp = NetworkStateComponent()
    
    ecs_manager.add_component(entity_id, network_comp)
    ecs_manager.add_component(entity_id, replication_comp)
    ecs_manager.add_component(entity_id, state_comp)


def is_client_authoritative(entity_id: str, ecs_manager) -> bool:
    """Check if client has authority over an entity."""
    try:
        network_comp = ecs_manager.get_component(entity_id, NetworkComponent)
        return network_comp.authority == Authority.CLIENT
    except KeyError:
        return False  # No network component = not networkable


def should_replicate_entity(entity_id: str, ecs_manager) -> bool:
    """Check if an entity should be replicated over network."""
    try:
        network_comp = ecs_manager.get_component(entity_id, NetworkComponent)
        return network_comp.replicate
    except KeyError:
        return False  # No network component = don't replicate