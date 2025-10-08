"""Canonical registry of event bus topics used by the combat systems.

Each entry is declared as a :class:`~enum.Enum` member and documents the
producer, the intended consumers and the payload guarantees for the associated
event.  Importing modules should rely on the enum members (e.g.
``topics.EventTopic.ACTION_QUEUED``) to avoid drifting topic names and hidden
couplings between systems.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["EventTopic"]


class EventTopic(str, Enum):
    """Enumeration of every topic published on the global event bus."""

    BEGIN_TURN = "BeginTurn"
    """Published by the turn order system when a creature becomes active.

    Subscribers: user interfaces, AI controllers.
    Guarantees: provides ``actor_id`` for the entity starting its turn.
    """

    REQUEST_ACTIONS = "RequestActions"
    """Published by the turn order system to ask controllers for intents.

    Subscribers: action selectors and player input adapters.
    Guarantees: includes ``actor_id`` and any contextual turn metadata.
    """

    ACTIONS_AVAILABLE = "ActionsAvailable"
    """Published by :class:`core.actions.selector.ActionSelector` with options.

    Subscribers: UI layers and controller orchestrators.
    Guarantees: carries ``actor_id`` and an ``actions`` iterable payload.
    """

    INTENT_SUBMITTED = "IntentSubmitted"
    """Published by controllers once an actor has chosen an intent.

    Subscribers: validation pipelines and analytics hooks.
    Guarantees: contains an ``intent`` serialisation and optional context.
    """

    ACTION_VALIDATED = "ActionValidated"
    """Published by :class:`core.actions.validation.ValidationPipeline`.

    Subscribers: schedulers and analytics sinks.
    Guarantees: includes the ``intent`` payload accepted for execution.
    """

    INTENT_REJECTED = "IntentRejected"
    """Published by the validation pipeline when an intent cannot be played.

    Subscribers: controllers to surface validation errors to the player.
    Guarantees: contains the ``intent`` and a ``reasons`` sequence.
    """

    ACTION_QUEUED = "ActionQueued"
    """Published by :class:`core.actions.scheduler.ActionScheduler` on enqueue.

    Subscribers: the reaction manager and logging sinks.
    Guarantees: exposes the ``intent`` payload scheduled for resolution.
    """

    PERFORM_ACTION = "PerformAction"
    """Published by the scheduler when an action is ready to resolve.

    Subscribers: :class:`core.actions.performers.ActionPerformer`.
    Guarantees: contains ``intent`` metadata and ``await_reactions`` flag.
    """

    ACTION_RESOLVED = "ActionResolved"
    """Published by performers after an action (and reactions) has resolved.

    Subscribers: turn drivers, logging sinks and UI updates.
    Guarantees: replays the resolved ``intent`` payload and outcomes.
    """

    REACTION_WINDOW_OPENED = "ReactionWindowOpened"
    """Published by :class:`core.reactions.manager.ReactionManager`.

    Subscribers: controllers interested in declaring reactions.
    Guarantees: contains ``actor_id`` and reaction ``options`` metadata.
    """

    REACTION_DECLARED = "ReactionDeclared"
    """Published by controllers to announce a reaction intent.

    Subscribers: reaction manager which schedules the reactions.
    Guarantees: includes the ``intent`` payload and triggering metadata.
    """

    REACTION_RESOLVED = "ReactionResolved"
    """Published by the reaction manager once a reaction has been handled.

    Subscribers: UI layers and analytics.
    Guarantees: mirrors ``intent`` information and applied side effects.
    """

    END_TURN = "EndTurn"
    """Published by the turn driver after an actor has finished its turn.

    Subscribers: turn order system and state trackers.
    Guarantees: includes ``actor_id`` of the actor that just finished acting.
    """

    TURN_ADVANCED = "TurnAdvanced"
    """Published when the turn order advances to the next actor globally.

    Subscribers: initiative trackers, logging utilities.
    Guarantees: provides ``round`` and ``actor_id`` of the new active entity.
    """

    DAMAGE_APPLIED = "DamageApplied"
    """Published by damage resolution utilities when HP values change.

    Subscribers: UI, condition systems and achievement trackers.
    Guarantees: exposes ``source_id``, ``target_id`` and ``amount`` fields.
    """

    CONDITION_APPLIED = "ConditionApplied"
    """Published by the condition system whenever a status is applied.

    Subscribers: UI indicators and stackable condition tracking.
    Guarantees: provides ``target_id``, ``condition`` identifier and duration.
    """

    LINE_OF_SIGHT_CHANGED = "LoSChanged"
    """Published by :class:`core.los_manager.LoSManager` on visibility change.

    Subscribers: AI planning helpers and fog-of-war presenters.
    Guarantees: carries ``observer_id`` and a ``visible_entities`` sequence.
    """

    ATTACK_OF_OPPORTUNITY_TRIGGERED = "AoOTriggered"
    """Published when an entity provokes an attack of opportunity.

    Subscribers: reaction managers and combat logs.
    Guarantees: includes ``attacker_id`` and ``target_id`` identifiers.
    """

    MAP_LOADED = "MapLoaded"
    """Published by the map loader after loading a new terrain configuration.

    Subscribers: LOS manager, UI layout initialisers and placement systems.
    Guarantees: contains a ``map_id`` or ``terrain`` descriptor.
    """

    INVENTORY_QUERIED = "InventoryQueried"
    """Published by :mod:`core.inventory.query` helpers after a lookup.

    Subscribers: logging / debugging aides.
    Guarantees: includes ``actor_id`` and the resulting ``items`` tuple.
    """


# ---------------------------------------------------------------------------
# Backwards compatibility aliases
# ---------------------------------------------------------------------------

# NOTE: legacy modules still import the uppercase module-level constants.  By
# exposing aliases we keep their imports valid while funnelling everything
# through :class:`EventTopic`.  The aliases are intentionally defined *after*
# the enum so that tools such as Sphinx can still pick-up the richer docs.

BEGIN_TURN = EventTopic.BEGIN_TURN
REQUEST_ACTIONS = EventTopic.REQUEST_ACTIONS
ACTIONS_AVAILABLE = EventTopic.ACTIONS_AVAILABLE
INTENT_SUBMITTED = EventTopic.INTENT_SUBMITTED
INTENT_VALIDATED = EventTopic.ACTION_VALIDATED
INTENT_REJECTED = EventTopic.INTENT_REJECTED
ACTION_ENQUEUED = EventTopic.ACTION_QUEUED
PERFORM_ACTION = EventTopic.PERFORM_ACTION
ACTION_RESOLVED = EventTopic.ACTION_RESOLVED
REACTION_WINDOW_OPENED = EventTopic.REACTION_WINDOW_OPENED
REACTION_DECLARED = EventTopic.REACTION_DECLARED
REACTION_RESOLVED = EventTopic.REACTION_RESOLVED
END_TURN = EventTopic.END_TURN
TURN_ADVANCED = EventTopic.TURN_ADVANCED
DAMAGE_APPLIED = EventTopic.DAMAGE_APPLIED
CONDITION_APPLIED = EventTopic.CONDITION_APPLIED
LOS_CHANGED = EventTopic.LINE_OF_SIGHT_CHANGED
AOO_TRIGGERED = EventTopic.ATTACK_OF_OPPORTUNITY_TRIGGERED
MAP_LOADED = EventTopic.MAP_LOADED
INVENTORY_QUERIED = EventTopic.INVENTORY_QUERIED

