from entities.base_object import BaseObject
from utils.logger import log_calls
from typing import Optional, Dict, Tuple, List
from entities.effects import AttackEffect

from enum import Enum

class WeaponType(Enum):
    BRAWL = "brawl"
    MELEE = "melee"
    THROWING = "throwing"
    FIREARM = "firearm"

class Weapon(BaseObject):
    __slots__ = ("name", "damage_bonus", "weapon_range", "damage_type", "icon_path",
                 "weapon_type", "attack_traits", "attack_actions",
                 "ammunition", "max_ammunition", "infinite_ammunition", "reloadable", "reload_action_type",
                 "maximum_range", "effects")

    VALID_DAMAGE_TYPES = {"superficial", "aggravated", "mixed"}

    @log_calls
    def __init__(self, name: str,
                 damage_bonus: int,
                 weapon_range: int,
                 damage_type: str,
                 weapon_type: WeaponType,
                 icon_path: Optional[str] = None,
                 attack_actions: Optional[List[str]] = None,
                 max_ammunition: Optional[int] = None,
                 infinite_ammunition: bool = False,
                 reloadable: bool = True,
                 reload_action_type: str = "secondary",
                 maximum_range_multiplier: Optional[int] = None,
                 effects: Optional[List[AttackEffect]] = None) -> None:
        super().__init__()
        if damage_type not in self.VALID_DAMAGE_TYPES:
            raise ValueError(f"Invalid damage type '{damage_type}'. Must be one of {self.VALID_DAMAGE_TYPES}.")
        self.name = name
        self.damage_bonus = damage_bonus
        self.weapon_range = weapon_range
        self.damage_type = damage_type
        self.weapon_type = weapon_type
        self.icon_path = icon_path  # chemin pour affichage futur, pas sprite immédiat

        # Define which traits to use based on weapon type
        self.attack_traits = self._get_attack_traits()

        # List of attack actions (can be extended for multiple attack types per weapon)
        self.attack_actions = attack_actions or ["default_attack"]

        # New attributes for range and effects
        if maximum_range_multiplier is None:
            # Default max range multiplier
            if self.weapon_type in [WeaponType.BRAWL, WeaponType.MELEE]:
                maximum_range_multiplier = 1
            else:
                maximum_range_multiplier = 3
        self.maximum_range = self.weapon_range * maximum_range_multiplier
        self.effects = effects or []

        # Ammunition system
        self.infinite_ammunition = infinite_ammunition
        self.reloadable = reloadable
        self.reload_action_type = reload_action_type  # "primary" or "secondary"
        self.max_ammunition = max_ammunition if max_ammunition is not None else (float('inf') if infinite_ammunition else 0)
        self.ammunition = self.max_ammunition

    def _get_attack_traits(self):
        """
        Returns the (attribute_path, skill_path) tuple for the weapon type.
        """
        if self.weapon_type == WeaponType.BRAWL:
            return ("Attributes.Physical.Dexterity", "Abilities.Talents.Brawl")
        elif self.weapon_type == WeaponType.MELEE:
            return ("Attributes.Physical.Dexterity", "Abilities.Skills.Melee")
        elif self.weapon_type == WeaponType.THROWING:
            return ("Attributes.Physical.Dexterity", "Abilities.Skills.Athletics")
        elif self.weapon_type == WeaponType.FIREARM:
            return ("Attributes.Physical.Dexterity", "Abilities.Skills.Firearms")
        else:
            return ("Attributes.Physical.Dexterity", "Abilities.Talents.Brawl")

    @log_calls
    def get_damage_bonus(self) -> int:
        """
        Retourne le bonus de dégâts de l'arme.
        """
        return self.damage_bonus

    def can_attack(self, amount: int = 1) -> bool:
        """Return True if the weapon has enough ammunition to attack (or is infinite)."""
        if self.infinite_ammunition:
            return True
        return self.ammunition >= amount

    def consume_ammunition(self, amount: int = 1) -> bool:
        """Consume ammunition if possible. Return True if successful."""
        if self.infinite_ammunition:
            return True
        if self.ammunition >= amount:
            self.ammunition -= amount
            return True
        return False

    def reload(self):
        """Reload the weapon to max_ammunition if reloadable."""
        if not self.reloadable:
            return False
        self.ammunition = self.max_ammunition
        return True
