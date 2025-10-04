"""Protocols describing the passive UI bridge callbacks.

The combat loop exposes a set of passive notifications intended for visual
front-ends.  Concrete adapters (Arcade UI, network clients, etc.) can
implement :class:`UIBridgePort` and bind themselves to the unified event
stream without requiring refactors of the underlying systems.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class UIBridgePort(Protocol):
    """Passive hooks exposed to optional UI bridges.

    Implementations should avoid blocking the caller and favour enqueueing
    any expensive rendering work.  Each callback mirrors a notification that
    the hot-seat CLI already consumes, enabling feature parity while remaining
    decoupled from concrete UI frameworks.
    """

    def show_action_options(
        self,
        actor_id: str,
        options: Sequence[Mapping[str, Any]] | Sequence[Any],
    ) -> None:
        """Display the list of action options calculated for ``actor_id``."""

    def highlight_targets(
        self,
        target_specs: Sequence[Mapping[str, Any]] | Sequence[Any],
    ) -> None:
        """Emphasise the currently highlighted targets on the UI surface."""

    def show_reaction_prompt(
        self,
        context: Mapping[str, Any],
        options: Sequence[Mapping[str, Any]] | Sequence[Any],
    ) -> None:
        """Inform the UI that a reaction window opened for the given context."""

    def show_toast(self, event_summary: str) -> None:
        """Render a lightweight notification summarising a recent event."""


__all__ = ["UIBridgePort"]
