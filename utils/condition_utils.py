# utils/condition_utils.py
"""Utility helpers for Conditions (status effects).

Implemented:
- Weakened variants (Physical, MentalSocial, Total) applying -2 dice penalties.

Design:
- Character.states is a set of active condition identifiers.
- Damage-based weakened variants are dynamic: active while thresholds are met.
- Total variant is applied via external effects (e.g., spells) and may have a duration (handled by ConditionSystem).
- A roll is penalized at most -2 even if multiple variants overlap.
"""
from __future__ import annotations
from typing import Iterable, Set, Tuple, List

# Attribute groups
PHYSICAL_ATTRIBUTES: Set[str] = {"Strength", "Dexterity", "Stamina"}
MENTAL_ATTRIBUTES: Set[str] = {"Perception", "Intelligence", "Wits"}
SOCIAL_ATTRIBUTES: Set[str] = {"Charisma", "Manipulation", "Appearance"}
WILLPOWER_TRAIT: Set[str] = {"Willpower"}

# Condition identifiers
WEAKENED_PHYSICAL = "Weakened.Physical"
WEAKENED_MENTAL_SOCIAL = "Weakened.MentalSocial"
WEAKENED_TOTAL = "Weakened.Total"
POISONED = "Poisoned"
SLOWED = "Slowed"
IMMOBILIZED = "Immobilized"
HANDICAP = "Handicap"
INVISIBLE = "Invisible"
SEE_INVISIBLE = "SeeInvisible"  # Grants ability to perceive Invisible targets
NIGHT_VISION_PARTIAL = "NightVision.Partial"
NIGHT_VISION_TOTAL = "NightVision.Total"
ALL_WEAKENED = {WEAKENED_PHYSICAL, WEAKENED_MENTAL_SOCIAL, WEAKENED_TOTAL}


def apply_weakened_penalty(character, base_pool: int, used_attributes: Iterable[str]) -> int:
    """Apply the Weakened penalty (-2 dice) if any relevant attribute is used.

    Args:
        character: Character instance (must have .states set[str])
        base_pool: Original dice pool
        used_attributes: Iterable of attribute/trait names used in the roll (e.g. ["Strength"])
    Returns:
        Adjusted dice pool (never below 0)
    """
    if base_pool <= 0:
        return base_pool
    states = getattr(character, "states", set())
    if not states:
        return base_pool
    used = set(used_attributes)
    if not used:
        return base_pool

    # Total weakened applies to any attribute or willpower
    if WEAKENED_TOTAL in states:
        if used & (PHYSICAL_ATTRIBUTES | MENTAL_ATTRIBUTES | SOCIAL_ATTRIBUTES | WILLPOWER_TRAIT):
            return max(0, base_pool - 2)
        return base_pool

    penalty = False
    if WEAKENED_PHYSICAL in states and used & PHYSICAL_ATTRIBUTES:
        penalty = True
    if WEAKENED_MENTAL_SOCIAL in states and used & (MENTAL_ATTRIBUTES | SOCIAL_ATTRIBUTES | WILLPOWER_TRAIT):
        penalty = True
    if penalty:
        return max(0, base_pool - 2)
    return base_pool


def evaluate_weakened_damage_based(character) -> Tuple[List[str], List[str]]:
    """Evaluate and update damage-based weakened variants on the character.

    Activates / deactivates:
      - Weakened.Physical when total health damage >= max_health
      - Weakened.MentalSocial when total willpower damage >= max_willpower

    Returns:
        (added, removed): lists of condition identifiers changed.
    """
    added: List[str] = []
    removed: List[str] = []
    states = character.states

    health_total = character._health_damage['superficial'] + character._health_damage['aggravated']
    will_total = character._willpower_damage['superficial'] + character._willpower_damage['aggravated']

    # Physical weakened
    phys_active = health_total >= character.max_health
    if phys_active and WEAKENED_PHYSICAL not in states:
        states.add(WEAKENED_PHYSICAL)
        added.append(WEAKENED_PHYSICAL)
    if not phys_active and WEAKENED_PHYSICAL in states:
        states.remove(WEAKENED_PHYSICAL)
        removed.append(WEAKENED_PHYSICAL)

    # Mental/Social weakened
    mental_active = will_total >= character.max_willpower
    if mental_active and WEAKENED_MENTAL_SOCIAL not in states:
        states.add(WEAKENED_MENTAL_SOCIAL)
        added.append(WEAKENED_MENTAL_SOCIAL)
    if not mental_active and WEAKENED_MENTAL_SOCIAL in states:
        states.remove(WEAKENED_MENTAL_SOCIAL)
        removed.append(WEAKENED_MENTAL_SOCIAL)

    return added, removed

__all__ = [
    'PHYSICAL_ATTRIBUTES', 'MENTAL_ATTRIBUTES', 'SOCIAL_ATTRIBUTES', 'WILLPOWER_TRAIT',
    'WEAKENED_PHYSICAL', 'WEAKENED_MENTAL_SOCIAL', 'WEAKENED_TOTAL',
    'POISONED','SLOWED','IMMOBILIZED','HANDICAP','INVISIBLE','SEE_INVISIBLE',
    'NIGHT_VISION_PARTIAL','NIGHT_VISION_TOTAL',
    'apply_weakened_penalty', 'evaluate_weakened_damage_based'
]
