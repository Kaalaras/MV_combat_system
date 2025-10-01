from entities.default_entities.armors import Clothes
from entities.default_entities.weapons import Fists
from ecs.systems.action_system import Action, ActionType


from ecs.actions.attack_actions import RegisteredAttackAction
from ecs.actions.movement_actions import StandardMoveAction, SprintAction
from ecs.actions.reload_action import ReloadAction
from ecs.actions.defensive_actions import (
    DodgeRangedAction,
    DodgeCloseCombatAction,
    ParryAction,
    AbsorbAction,
)
from ecs.actions.turn_actions import EndTurnAction

BASE_EQUIPMENT = {
    "armor": Clothes(),
    "weapons": {
        "melee": Fists(),
    }
}

# Define actions that need to be initialized with game systems
BASE_ACTIONS = [
    {
        "name": "Attack",
        "type": ActionType.PRIMARY,
        "class": RegisteredAttackAction,
        "params": {},
        "description": "Attack with equipped weapon"
    },
    {
        "name": "Dodge (ranged)",
        "type": ActionType.SECONDARY,
        "class": DodgeRangedAction,
        "params": {"movement_required": True},
        "description": "Dodge a ranged attack"
    },
    {
        "name": "Dodge (close combat)",
        "type": ActionType.SECONDARY,
        "class": DodgeCloseCombatAction,
        "params": {"movement_required": True},
        "description": "Dodge a close combat attack"
    },
    {
        "name": "Parry",
        "type": ActionType.SECONDARY,
        "class": ParryAction,
        "params": {},
        "description": "Parry with a melee weapon"
    },
    {
        "name": "Absorb",
        "type": ActionType.SECONDARY,
        "class": AbsorbAction,
        "params": {},
        "description": "Absorb damage with stamina and brawl"
    },
    {
        "name": "Standard Move",
        "type": ActionType.PRIMARY,
        "class": StandardMoveAction,
        "params": {"movement_required": True},
        "description": "Move up to 7 tiles"
    },
    {
        "name": "Sprint",
        "type": ActionType.PRIMARY,
        "class": SprintAction,
        "params": {"movement_required": True},
        "description": "Move up to 15 tiles"
    },
    {
        "name": "Reload",
        "type": ActionType.SECONDARY,
        "class": ReloadAction,
        "params": {},
        "description": "Reload your weapon"
    },
    {
        "name": "End Turn",
        "type": ActionType.FREE,
        "class": EndTurnAction,
        "params": {},
        "description": "Ends the current entity's turn."
    },
]