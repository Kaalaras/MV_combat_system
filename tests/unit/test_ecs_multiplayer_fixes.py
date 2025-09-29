"""
Tests for ECS Architecture Compliance and Multiplayer Readiness
===============================================================

This test suite validates the critical fixes implemented to address the ECS 
architecture violations identified in the multiplayer readiness review.

Key Areas Tested:
1. GameState no longer violates ECS principles
2. Enhanced Event Bus functionality
3. Network components for multiplayer support  
4. Proper ECS-only entity management

These tests ensure the codebase is ready for multiplayer implementation.
"""

import unittest
from unittest.mock import Mock, MagicMock
import time
from dataclasses import dataclass

# Test the enhanced event bus
from core.enhanced_event_bus import EnhancedEventBus, Event, EventPriority

# Test network components
from ecs.components.network import NetworkComponent, Authority, ReplicationComponent, make_entity_networkable

# Test the updated GameState
from core.game_state import GameState


class TestECSArchitectureCompliance(unittest.TestCase):
    """Test that ECS architecture violations have been fixed."""
    
    def test_game_state_no_entities_dict(self):
        """
        CRITICAL: Ensure GameState no longer stores entities directly.
        
        Justification: The entities dictionary was the primary ECS violation that
        would prevent proper multiplayer synchronization. This test ensures it's gone.
        """
        gs = GameState()
        
        # Verify entities dict no longer exists
        self.assertFalse(hasattr(gs, 'entities'), 
                        "GameState still has 'entities' attribute - ECS violation not fixed!")
        
        # Verify ECS manager is the intended approach
        self.assertTrue(hasattr(gs, 'ecs_manager'),
                       "GameState missing ecs_manager - proper ECS integration incomplete")

    def test_deprecated_methods_raise_warnings(self):
        """
        CRITICAL: Ensure deprecated entity access methods properly warn users.
        
        Justification: Legacy code using the old API needs clear guidance
        to migrate to proper ECS patterns for multiplayer compatibility.
        """
        import warnings
        gs = GameState()
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            gs.add_entity("test", {})
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
            self.assertIn("ecs_manager.create_entity", str(w[0].message))
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            gs.get_entity("test")
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
            self.assertIn("ecs_manager.get_component", str(w[0].message))
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            gs.remove_entity("test")
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
            self.assertIn("ecs_manager.delete_entity", str(w[0].message))
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            gs.get_component("test", "position")
            self.assertEqual(len(w), 2)  # get_component calls get_entity, so 2 warnings
            deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
            self.assertGreaterEqual(len(deprecation_warnings), 1)
            # Check at least one contains the expected message
            messages = [str(warning.message) for warning in deprecation_warnings]
            self.assertTrue(any("ecs_manager.get_component" in msg for msg in messages))

    def test_ecs_manager_integration(self):
        """
        Test proper integration with ECS manager.
        
        Justification: GameState should work seamlessly with ECS manager
        for entity operations, which is required for multiplayer state sync.
        """
        mock_ecs = Mock()
        gs = GameState(ecs_manager=mock_ecs)
        
        self.assertEqual(gs.ecs_manager, mock_ecs)
        
        # Test update_teams uses ECS manager
        mock_ecs.get_components.return_value = []  # No entities with character refs
        gs.update_teams()  # Should not crash
        
        # Test get_entity_size uses ECS manager
        mock_ecs.get_component.side_effect = KeyError("No component")
        size = gs.get_entity_size("test")
        self.assertEqual(size, (1, 1))  # Default size when no component found


class TestEnhancedEventBus(unittest.TestCase):
    """Test enhanced event bus features required for multiplayer."""
    
    def setUp(self):
        self.bus = EnhancedEventBus()
    
    def test_backward_compatibility(self):
        """
        CRITICAL: Enhanced event bus must maintain backward compatibility.
        
        Justification: Existing game systems should continue working without
        modification while gaining multiplayer features.
        """
        callback_called = False
        
        def test_callback(data="test"):
            nonlocal callback_called
            callback_called = True
        
        # Old API should still work
        self.bus.subscribe("test_event", test_callback)
        self.bus.publish("test_event", data="test")
        
        self.assertTrue(callback_called)
        
        # Verify subscribers can be retrieved
        subscribers = self.bus.get_subscribers("test_event")
        self.assertEqual(len(subscribers), 1)
        self.assertEqual(subscribers[0], test_callback)
    
    def test_event_ordering_and_persistence(self):
        """
        CRITICAL: Events must have deterministic ordering for multiplayer sync.
        
        Justification: Multiplayer games require events to be processed in the
        same order on all clients to maintain state consistency.
        """
        events_received = []
        
        def capture_event(data=None):
            events_received.append(data)
        
        self.bus.subscribe("test", capture_event)
        
        # Publish multiple events
        event1 = self.bus.publish_enhanced("test", data="first")
        event2 = self.bus.publish_enhanced("test", data="second") 
        event3 = self.bus.publish_enhanced("test", data="third")
        
        # Verify sequence numbers are ordered
        self.assertLess(event1.sequence_number, event2.sequence_number)
        self.assertLess(event2.sequence_number, event3.sequence_number)
        
        # Verify events are stored in history
        self.assertEqual(len(self.bus.event_history), 3)
        
        # Verify events can be retrieved since a sequence number
        recent_events = self.bus.get_events_since(event1.sequence_number)
        self.assertEqual(len(recent_events), 2)  # event2 and event3
    
    def test_error_handling(self):
        """
        CRITICAL: Event processing must continue even if individual callbacks fail.
        
        Justification: In multiplayer, one system's failure shouldn't crash
        the entire event processing pipeline.
        """
        good_callback_called = False
        
        def failing_callback(**kwargs):
            raise Exception("Test failure")
        
        def good_callback(**kwargs):
            nonlocal good_callback_called
            good_callback_called = True
        
        self.bus.subscribe("test", failing_callback)
        self.bus.subscribe("test", good_callback)
        
        # Should not raise exception despite failing callback
        self.bus.publish("test")
        
        # Good callback should still execute
        self.assertTrue(good_callback_called)
    
    def test_network_serialization(self):
        """
        Test event serialization for network transmission.
        
        Justification: Multiplayer requires events to be serializable 
        for transmission between clients and server.
        """
        event = Event(
            timestamp=time.time(),
            sequence_number=1,
            event_type="test_event",
            priority=EventPriority.GAMEPLAY,
            data={"player_id": "123", "action": "move"},
            source="player1",
            network_replicate=True
        )
        
        # Test serialization
        serialized = event.serialize()
        self.assertIsInstance(serialized, dict)
        self.assertEqual(serialized['event_type'], "test_event")
        
        # Test deserialization
        deserialized = Event.deserialize(serialized)
        self.assertEqual(deserialized.event_type, event.event_type)
        self.assertEqual(deserialized.data, event.data)


class TestNetworkComponents(unittest.TestCase):
    """Test network components for multiplayer support."""
    
    def test_network_component_creation(self):
        """
        Test creation and serialization of network components.
        
        Justification: Network components are essential for entity ownership
        and authority management in multiplayer games.
        """
        network_comp = NetworkComponent(
            owner_id="player1",
            authority=Authority.CLIENT,
            priority=3
        )
        
        self.assertEqual(network_comp.owner_id, "player1")
        self.assertEqual(network_comp.authority, Authority.CLIENT)
        self.assertEqual(network_comp.priority, 3)
        
        # Test sync timing
        self.assertTrue(network_comp.needs_sync())  # Should need sync initially
        network_comp.mark_synced()
        self.assertFalse(network_comp.needs_sync())  # Should not need sync immediately after
    
    def test_replication_component(self):
        """
        Test replication settings for bandwidth optimization.
        
        Justification: Fine-grained control over what data is synchronized
        is crucial for multiplayer performance and bandwidth usage.
        """
        replication = ReplicationComponent(
            replicate_position=True,
            replicate_health=True,
            replicate_equipment=False
        )
        
        self.assertTrue(replication.should_replicate('position'))
        self.assertTrue(replication.should_replicate('health'))
        self.assertFalse(replication.should_replicate('equipment'))
        self.assertFalse(replication.should_replicate('unknown_field'))
        
        # Test custom fields
        replication.custom_fields['animations'] = True
        self.assertTrue(replication.should_replicate('animations'))
    
    def test_network_component_serialization(self):
        """
        Test network component serialization for state sync.
        
        Justification: Network components must be serializable to transmit
        entity ownership and authority information between clients.
        """
        network_comp = NetworkComponent(
            owner_id="player2",
            authority=Authority.SERVER,
            sync_frequency=0.05
        )
        
        # Test serialization
        serialized = network_comp.serialize()
        self.assertIsInstance(serialized, dict)
        self.assertEqual(serialized['owner_id'], "player2")
        self.assertEqual(serialized['authority'], Authority.SERVER.value)
        
        # Test deserialization
        deserialized = NetworkComponent.deserialize(serialized)
        self.assertEqual(deserialized.owner_id, network_comp.owner_id)
        self.assertEqual(deserialized.authority, network_comp.authority)
    
    def test_entity_networkability_helpers(self):
        """
        Test utility functions for making entities multiplayer-ready.
        
        Justification: Helper functions should make it easy to add network
        support to existing entities without manual component management.
        """
        mock_ecs = Mock()
        
        # Test making entity networkable
        make_entity_networkable("player1", "user123", Authority.CLIENT, mock_ecs)
        
        # Verify components were added
        self.assertEqual(mock_ecs.add_component.call_count, 3)  # Network, Replication, State components


class TestMultiplayerReadiness(unittest.TestCase):
    """Integration tests for overall multiplayer readiness."""
    
    def test_no_direct_entity_access_patterns(self):
        """
        CRITICAL: Verify no direct entity dictionary access remains.
        
        Justification: Any remaining direct entity access would bypass ECS
        and break multiplayer synchronization.
        """
        gs = GameState()
        
        # These should all be deprecated/removed
        deprecated_methods = ['add_entity', 'get_entity', 'remove_entity', 'get_component', 'set_component']
        
        for method_name in deprecated_methods:
            method = getattr(gs, method_name, None)
            self.assertIsNotNone(method, f"Method {method_name} should exist (for deprecation warning)")
            
    def test_no_direct_entity_access_patterns(self):
        """
        CRITICAL: Verify no direct entity dictionary access remains.
        
        Justification: Any remaining direct entity access would bypass ECS
        and break multiplayer synchronization.
        """
        import warnings
        gs = GameState()
        
        # These should all be deprecated/removed
        deprecated_methods = ['add_entity', 'get_entity', 'remove_entity', 'get_component', 'set_component']
        
        for method_name in deprecated_methods:
            method = getattr(gs, method_name, None)
            self.assertIsNotNone(method, f"Method {method_name} should exist (for deprecation warning)")
            
            # Calling these should raise deprecation warnings
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                try:
                    if method_name == 'add_entity':
                        method("test", {})
                    elif method_name == 'set_component':
                        method("test", "pos", None)
                    elif method_name == 'get_component':
                        method("test", "position")
                    else:
                        method("test")
                except Exception:
                    pass  # Some methods may raise other exceptions, we only care about warnings
                
                # Check that a deprecation warning was issued
                deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
                self.assertGreater(len(deprecation_warnings), 0, f"Method {method_name} should issue DeprecationWarning")
    
    def test_enhanced_event_bus_statistics(self):
        """
        Test monitoring and debugging capabilities.
        
        Justification: Multiplayer systems need monitoring capabilities
        to debug synchronization issues and performance problems.
        """
        bus = EnhancedEventBus()
        
        # Generate some events
        bus.publish("test_event1")
        bus.publish("test_event2")
        bus.publish("test_event1")  # Duplicate type
        
        stats = bus.get_statistics()
        
        self.assertEqual(stats['total_events'], 3)
        self.assertEqual(stats['sequence_counter'], 3)
        self.assertEqual(stats['event_type_counts']['test_event1'], 2)
        self.assertEqual(stats['event_type_counts']['test_event2'], 1)
    
    def test_event_replay_functionality(self):
        """
        Test event replay for late-joining players.
        
        Justification: Multiplayer games need to synchronize late-joining
        players by replaying the event history.
        """
        bus = EnhancedEventBus()
        received_events = []
        
        def capture_event(**kwargs):
            received_events.append(kwargs)
        
        bus.subscribe("replay_test", capture_event)
        
        # Create some events to replay
        events = [
            Event(time.time(), 1, "replay_test", EventPriority.GAMEPLAY, {"data": "event1"}),
            Event(time.time(), 2, "replay_test", EventPriority.GAMEPLAY, {"data": "event2"}),
        ]
        
        # Replay events
        bus.replay_events(events)
        
        # Verify events were processed in order
        self.assertEqual(len(received_events), 2)
        self.assertEqual(received_events[0]['data'], "event1")
        self.assertEqual(received_events[1]['data'], "event2")


if __name__ == '__main__':
    unittest.main(verbosity=2)