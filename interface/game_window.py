"""Legacy GameWindow (Deprecated)
=================================

This file contained an early experimental Arcade-based window integrating
legacy UI + ECS + direct input handling. It is now deprecated in favor of the
new decoupled architecture:
  - player_turn_controller.PlayerTurnController
  - input_manager.InputManager
  - ui_adapter.UIAdapter
  - ui_manager_v2.UIManagerV2

Rationale for deprecation:
  * Tight coupling of rendering, input, turn logic, and action economy
  * Direct manipulation of ECS components from UI layer
  * Divergent event naming and action flow vs core GameSystem / EventBus

Retention Policy:
  * Kept as a stub so imports referencing interface.game_window do not break.
  * Actual Arcade window (if reintroduced) should be implemented in a new file
    (e.g. interface/arcade_app.py) using the new modular components.

Attempting to instantiate GameWindow will raise NotImplementedError to avoid
silent misuse.
"""
from __future__ import annotations
from typing import Any


class GameWindow:  # pragma: no cover - legacy stub
    def __init__(self, *_, **__):
        raise NotImplementedError(
            "Legacy GameWindow has been deprecated. Use the new modular UI stack: "
            "PlayerTurnController + UIAdapter + UIManagerV2 + external render loop."
        )

    # Placeholder methods (documented to guide refactorers)
    def on_draw(self) -> None:  # pragma: no cover
        """Removed. Previously handled full scene rendering via Arcade."""
        pass

    def on_update(self, delta_time: float) -> None:  # pragma: no cover
        """Removed. Previously advanced movement/combat systems each frame."""
        pass
