"""Event bus topic constants used across the combat system."""

BEGIN_TURN = "begin_turn"
REQUEST_ACTIONS = "request_actions"
ACTIONS_AVAILABLE = "actions_available"

INTENT_SUBMITTED = "intent_submitted"
INTENT_VALIDATED = "intent_validated"
INTENT_REJECTED = "intent_rejected"

ACTION_ENQUEUED = "action_enqueued"
PERFORM_ACTION = "perform_action"
ACTION_RESOLVED = "action_resolved"

REACTION_WINDOW_OPENED = "reaction_window_opened"
REACTION_DECLARED = "reaction_declared"
REACTION_RESOLVED = "reaction_resolved"

END_TURN = "end_turn"

INVENTORY_QUERIED = "inventory_queried"

