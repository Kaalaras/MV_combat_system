from typing import Callable, Dict, List, Any, Optional


class EventBus:
    """
    A simple event publish/subscribe system that enables communication between components
    without them having direct references to each other.

    This implementation supports:
    - Multiple subscribers for the same event type
    - Type-safe callback registration
    - Subscriber management (subscribe, unsubscribe, clear)

    Example usage:

    ```
    # Create an event bus
    event_bus = EventBus()

    # Define event handlers
    def on_user_login(user_id: str, timestamp: float) -> None:
        print(f"User {user_id} logged in at {timestamp}")

    def log_event(event_name: str, **data) -> None:
        print(f"Event '{event_name}' occurred with data: {data}")

    # Subscribe to events
    event_bus.subscribe("user_login", on_user_login)
    event_bus.subscribe("user_login", lambda **kwargs: log_event("user_login", **kwargs))

    # Publish an event
    event_bus.publish("user_login", user_id="abc123", timestamp=1625097600)

    # Unsubscribe when no longer needed
    event_bus.unsubscribe("user_login", on_user_login)
    ```
    """

    def __init__(self) -> None:
        """
        Initialize an empty event bus with no subscribers.
        """
        self.subscribers: Dict[str, List[Callable[..., None]]] = {}

    def subscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """
        Subscribe to a specific event type with a callback function.

        Args:
            event_type: A string identifier for the event type
            callback: A function to be called when the event is published
                      The function signature should match the arguments passed when publishing

        Returns:
            None

        Example:
            ```
            def handle_message(sender: str, content: str) -> None:
                print(f"Message from {sender}: {content}")

            event_bus.subscribe("new_message", handle_message)
            ```
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[..., None]) -> None:
        """
        Unsubscribe a specific callback from an event type.

        Args:
            event_type: The event type string identifier
            callback: The callback function to remove (must be the same object that was subscribed)

        Returns:
            None

        Example:
            ```
            # First subscribe
            event_bus.subscribe("new_message", handle_message)

            # Later, unsubscribe
            event_bus.unsubscribe("new_message", handle_message)
            ```
        """
        if event_type in self.subscribers:
            if callback in self.subscribers[event_type]:
                self.subscribers[event_type].remove(callback)

    def publish(self, event_type: str, **kwargs: Any) -> None:
        """
        Publish an event of the specified type with the given keyword arguments.
        All registered callbacks for this event type will be called with these arguments.

        Args:
            event_type: The event type string identifier
            **kwargs: Keyword arguments to pass to each subscriber callback

        Returns:
            None

        Example:
            ```
            # Publish an event with data
            event_bus.publish("temperature_change",
                             sensor_id="living_room",
                             celsius=21.5,
                             timestamp=1625097600)
            ```
        """
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                callback(**kwargs)

    def clear(self) -> None:
        """
        Remove all subscriptions from the event bus.
        Useful for cleanup or when reinitializing a system.

        Returns:
            None

        Example:
            ```
            # Remove all subscribers
            event_bus.clear()
            ```
        """
        self.subscribers.clear()

    def get_subscribers(self, event_type: str) -> List[Callable[..., None]]:
        """
        Get the list of subscribers for a specific event type.

        Args:
            event_type: The event type string identifier

        Returns:
            A list of callback functions registered for the event type.
            Returns an empty list if no subscribers exist.

        Example:
            ```
            # Check how many subscribers an event has
            subscribers = event_bus.get_subscribers("system_shutdown")
            print(f"There are {len(subscribers)} components listening for shutdown events")
            ```
        """
        return self.subscribers.get(event_type, [])