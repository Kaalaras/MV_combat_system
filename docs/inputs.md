# Input & Intent Event Flow

This document summarises the canonical flow of combat intents as they travel
through the event bus.  The same sequence is used by the hot-seat controller,
AI shims that emulate player inputs, and any future UI front-ends.

## Topics overview

| Topic | Producer | Consumer(s) | Purpose |
| ----- | -------- | ----------- | ------- |
| `BEGIN_TURN` | Turn engine | Input controllers, UI | Signal that an actor becomes active. |
| `REQUEST_ACTIONS` | Turn engine | `ActionSelector`, input controllers | Ask for action options for an actor. |
| `ACTIONS_AVAILABLE` | `ActionSelector` | Controllers / UI | Provide declarative action options and valid targets. |
| `INTENT_SUBMITTED` | Controllers | `IntentValidator` | Publish a declarative `ActionIntent`. |
| `INTENT_VALIDATED` | `IntentValidator` | `ActionScheduler` | Confirm the intent is valid and ready to reserve costs. |
| `ACTION_ENQUEUED` | `ActionScheduler` | Queue / metrics | Notify downstream systems that the action is queued. |
| `PERFORM_ACTION` | `ActionScheduler`, `ReactionManager` | `ActionPerformer`, `ReactionManager` | Trigger execution (possibly pausing for reactions). |
| `REACTION_WINDOW_OPENED` | `ReactionManager` | Controllers | Offer defenders a chance to respond. |
| `REACTION_DECLARED` | Controllers | `ReactionManager` | Submit a chosen reaction or a pass. |
| `REACTION_RESOLVED` | `ReactionManager` | `ActionPerformer`, UI | Inform that reactions are sorted and execution may resume. |
| `ACTION_RESOLVED` | `ActionPerformer` | Turn engine, UI | Action results (damage, movement, etc.). |
| `END_TURN` | Turn engine | Input controllers, UI | Active actor’s turn is finished. |

## Sequence diagram

```
BEGIN_TURN
   |
   v
REQUEST_ACTIONS ---> (ActionSelector)
   |                    |
   |                    v
   |              ACTIONS_AVAILABLE
   |                    |
   |          +---------+----------+
   |          |                    |
   v          v                    v
Controller publishes INTENT_SUBMITTED
   |                    |
   |              INTENT_VALIDATED
   |                    |
   v                    v
ACTION_ENQUEUED ----> PERFORM_ACTION --> [optional] REACTION_WINDOW_OPENED
                                       (if reactions)        |
                                       <---------------------+
                                       REACTION_DECLARED --> REACTION_RESOLVED
                                       |
                                       v
                               PERFORM_ACTION (resumed)
                                       |
                                       v
                               ACTION_RESOLVED
                                       |
                                       v
                                    END_TURN
```

## Usage tips

* Controllers that emulate players (including AI harnesses) should listen to
  `ACTIONS_AVAILABLE` and publish intents rather than mutating state directly.
* When monitoring a live simulation, run `scripts/dump_events.py --demo` to see
  the event order and payload structure.
* Reaction flows reuse the `PERFORM_ACTION` topic: the initial publication has
  `await_reactions=True`, the resumed call sets `reactions_resolved=True` with
  the sorted results.
