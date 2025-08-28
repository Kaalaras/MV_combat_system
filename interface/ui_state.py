"""UI State Snapshot Structures
================================

This module defines immutable data containers representing the *current* view
state that the rendering layer (UIManager) uses to draw the interface.

Separation of Concerns
----------------------
Core simulation data lives in GameState / ECS. The UI only needs *selected,*
*derived,* or *ephemeral* information (e.g. which cells are highlighted,
notifications, pending action selection). Extracting these into a snapshot
object allows:
  - Simple diffing / logging
  - Thread or async safety (if later a worker builds snapshots)
  - Easier unit testing (pure data comparisons)

Update Flow (Intended)
----------------------
1. Core & controllers publish events (turn_start, action_performed, etc.).
2. UIAdapter listens, aggregates relevant pieces, produces UiState.
3. UIAdapter publishes ui.state_update(state=<UiState>) via EventBus.
4. UIManager stores the latest UiState and renders it every frame.
5. No mutation of UiState after publication (dataclass frozen = True).

Extensibility Strategy
----------------------
Add optional fields with default None / empty values. Avoid breaking changes.
Prefer derived_* prefix for fields computed purely from other fields for clarity.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple, Dict, Any


Cell = Tuple[int, int]


@dataclass(frozen=True)
class InitiativeEntry:
    """Represents one entity in the initiative order for display purposes.

    Fields kept intentionally small; the renderer can query extra details lazily
    if it has performant access. Avoid embedding heavy component objects here.
    """
    entity_id: str
    is_active: bool = False
    is_player_controlled: bool = False
    # Minimal combat vitals (optional – may be absent if not yet fetched)
    health: Optional[int] = None
    max_health: Optional[int] = None
    willpower: Optional[int] = None
    max_willpower: Optional[int] = None
    conditions: Tuple[str, ...] = ()  # NEW: active conditions identifiers (short)


@dataclass(frozen=True)
class PendingAction:
    """Represents an action the player has chosen but not yet fully parameterized.

    Example: Player picked "Move" but hasn't selected a target tile yet.
    """
    entity_id: str
    action_name: str
    requires_target: bool = False
    valid_targets: Tuple[Cell, ...] = ()  # Precomputed highlightable cells (optional)


@dataclass(frozen=True)
class TooltipData:
    """Represents tooltip information for UI elements."""
    entity_id: Optional[str] = None
    title: str = ""
    main_values: Dict[str, str] = field(default_factory=dict)  # e.g. {"Health": "5/7", "Attack": "Range 2"}
    position: Tuple[int, int] = (0, 0)  # Screen coordinates
    show_delay: float = 1.5  # Seconds before tooltip appears
    visible: bool = False


@dataclass(frozen=True)
class TurnStartNotification:
    """Represents a turn start notification."""
    message: str = "Your Turn's beginning"
    display_time: float = 2.0
    color: Tuple[int, int, int] = (128, 128, 128)  # Grey


@dataclass(frozen=True)
class ErrorFeedback:
    """Represents error feedback for invalid actions."""
    message: str
    entity_id: Optional[str] = None
    display_time: float = 3.0
    color: Tuple[int, int, int] = (255, 100, 100)  # Red


@dataclass(frozen=True)
class UiState:
    """Single immutable snapshot consumed by the rendering layer.

    Only include what the UI needs at a frame boundary.
    Heavy / large collections should be summarized.
    """
    active_entity_id: Optional[str]
    round_number: int
    initiative: Tuple[InitiativeEntry, ...] = ()

    # Action economy
    actions_remaining: Optional[int] = None
    max_actions: int = 2
    free_move_available: bool = False
    primary_actions_remaining: Optional[int] = None
    secondary_actions_remaining: Optional[int] = None

    # Player interaction state
    pending_action: Optional[PendingAction] = None
    highlighted_cells: Tuple[Cell, ...] = ()
    highlight_mode: Optional[str] = None  # e.g. "move", "attack", "target"

    # Notifications / feedback
    notifications: Tuple[str, ...] = ()
    transient_message: Optional[str] = None

    # NEW: Enhanced feedback systems
    tooltip: Optional[TooltipData] = None
    turn_start_notification: Optional[TurnStartNotification] = None
    error_feedback: Optional[ErrorFeedback] = None

    # Combat outcome preview / last action results
    last_action_name: Optional[str] = None
    last_action_result: Optional[str] = None

    # Debug / meta flags
    is_player_turn: bool = False
    waiting_for_player_input: bool = False

    # Arbitrary extensibility bag (for experimental UI panels)
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON‑friendly dictionary version (nested dataclasses expanded)."""
        return asdict(self)

    @staticmethod
    def empty() -> "UiState":
        """Convenience zero / initial value used before any events received."""
        return UiState(active_entity_id=None, round_number=0)
