"""Port definition for user input controllers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class InputController(Protocol):
    """Protocol describing the minimal controller interface for intents."""

    def bind(self, event_bus: Any) -> None:
        """Attach the controller to an event bus instance."""

    def on_request_actions(self, actor_id: str) -> None:
        """Handle a prompt to declare an action intent for ``actor_id``."""

    def on_reaction_prompt(self, reaction_context: Any) -> None:
        """Handle a prompt to declare a reaction within ``reaction_context``."""

