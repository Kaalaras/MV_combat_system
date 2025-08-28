"""Legacy UIManager (Deprecated)
================================

This legacy implementation mixed rendering responsibilities with gameplay
logic (initiative management, free movement bookkeeping, direct ECS access).
It is superseded by:
  * interface.ui_state.UiState (immutable snapshot)
  * interface.ui_adapter.UIAdapter (event -> UiState aggregation)
  * interface.ui_manager_v2.UIManagerV2 (pure rendering / visual effects)
  * interface.input_manager.InputManager (input -> UI intents)
  * interface.player_turn_controller.PlayerTurnController (intent mediation)

Rationale:
  * Reduce coupling with ECS internals
  * Centralize event vocabulary
  * Enable headless tests for UI pipeline

This stub remains so existing imports `from interface.ui_manager import UIManager`
do not immediately break; attempting to instantiate will raise to nudge migration.
"""
from __future__ import annotations

class UIManager:  # pragma: no cover - legacy stub
    def __init__(self, *_, **__):
        raise NotImplementedError(
            "Legacy UIManager is deprecated. Use UIAdapter + UIManagerV2 with UiState snapshots."
        )
