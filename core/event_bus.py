"""Global publish/subscribe bus used to coordinate the combat systems."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Dict, Mapping, MutableMapping, Sequence

from core.events.topics import EventTopic

__all__ = ["EventBus", "Subscriber", "Topic"]

Topic = str | EventTopic
Subscriber = Callable[..., None]


class EventBus:
    """Simple in-memory event dispatcher.

    The bus accepts :class:`~core.events.topics.EventTopic` members or plain
    strings for backward compatibility.  Payloads can be supplied either as a
    mapping argument (``publish(topic, payload)``) or as keyword arguments
    (``publish(topic, foo=1)``); both forms may be combined, with keyword values
    taking precedence.
    """

    def __init__(self) -> None:
        self._subscribers: MutableMapping[str, list[Subscriber]] = defaultdict(list)

    @staticmethod
    def _normalise_topic(topic: Topic) -> str:
        return topic.value if isinstance(topic, EventTopic) else str(topic)

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------
    def subscribe(self, topic: Topic, callback: Subscriber) -> None:
        """Register ``callback`` for ``topic`` events."""

        key = self._normalise_topic(topic)
        if callback not in self._subscribers[key]:
            self._subscribers[key].append(callback)

    def unsubscribe(self, topic: Topic, callback: Subscriber) -> None:
        """Remove a previously registered subscription if present."""

        key = self._normalise_topic(topic)
        callbacks = self._subscribers.get(key)
        if not callbacks:
            return

        try:
            callbacks.remove(callback)
        except ValueError:  # pragma: no cover - defensive branch
            return

        if not callbacks:
            del self._subscribers[key]

    # ------------------------------------------------------------------
    # Publishing helpers
    # ------------------------------------------------------------------
    def publish(
        self,
        topic: Topic,
        payload: Mapping[str, Any] | None = None,
        /,
        **kwargs: Any,
    ) -> None:
        """Publish ``topic`` with the provided payload."""

        key = self._normalise_topic(topic)
        merged_payload: Dict[str, Any] = dict(payload or {})
        if kwargs:
            merged_payload.update(kwargs)

        for callback in list(self._subscribers.get(key, ())):
            callback(**merged_payload)

    # ------------------------------------------------------------------
    # Introspection helpers (mostly for tests/debug)
    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Remove all subscriptions from the bus."""

        self._subscribers.clear()

    def get_subscribers(self, topic: Topic) -> Sequence[Subscriber]:
        """Return all subscribers registered for ``topic``."""

        key = self._normalise_topic(topic)
        return tuple(self._subscribers.get(key, ()))

