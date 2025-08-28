from entities.base_object import BaseObject
from utils.logger import log_calls
from typing import Optional, List, Dict
from utils.damage_types import classify_damage

class Armor(BaseObject):
    __slots__ = ("name", "armor_value", "damage_type", "icon_path", "weapon_type_protected", "dexterity_mod",
                 "resistance_multipliers")

    VALID_DAMAGE_TYPES = ("superficial", "aggravated")

    @log_calls
    def __init__(self, name: str,
                 armor_value: int,
                 damage_type: List[str],
                 weapon_type_protected: List[str],
                 dexterity_mod: int = 0,
                 icon_path: Optional[str] = None,
                 resistance_multipliers: Optional[Dict[str, float]] = None) -> None:
        super().__init__()
        for damage_type_elem in damage_type:
            if damage_type_elem not in self.VALID_DAMAGE_TYPES:
                raise ValueError(f"Invalid damage type '{damage_type_elem}'. Must be one of {self.VALID_DAMAGE_TYPES}.")
        self.name = name
        self.armor_value = armor_value
        self.damage_type = damage_type # types de dégâts auxquels l'armure offre une absorption plate
        self.icon_path = icon_path  # chemin pour affichage futur, pas sprite immédiat
        self.weapon_type_protected = weapon_type_protected  # type d'arme que l'armure protège (one in : "melee", "ranged", "mental","social", "special")
        self.dexterity_mod = dexterity_mod  # modificateur de dextérité
        # resistance_multipliers: key can be severity (superficial/aggravated) or category (fire, gas, etc) or 'all'
        # value is multiplier applied to incoming damage BEFORE flat soak (0 = immunité, 0.5 = moitié, 2 = double vulnérabilité)
        self.resistance_multipliers = resistance_multipliers or {}

    def modify_incoming(self, damage_amount: int, damage_type: str) -> int:
        if damage_amount <= 0:
            return 0
        sev, cat = classify_damage(damage_type)
        mult = 1.0
        # precedence: category > severity > all
        if cat in self.resistance_multipliers:
            mult *= self.resistance_multipliers[cat]
        if sev in self.resistance_multipliers:
            mult *= self.resistance_multipliers[sev]
        if 'all' in self.resistance_multipliers:
            mult *= self.resistance_multipliers['all']
        adjusted = int(damage_amount * mult)
        # ensure minimum 0 when multiplier leads to fractional rounding
        if adjusted < 0:
            adjusted = 0
        return adjusted

    @log_calls
    def get_armor_value(self,
                        damage_type: str,
                        weapon_type: str) -> int:
        """
        Retourne la valeur d'armure selon le type de dégâts causés et le type d'arme utilisé.
        Extensible plus tard pour des modificateurs dynamiques.
        """
        if damage_type in self.damage_type and weapon_type in self.weapon_type_protected:
            return self.armor_value
        else:
            return 0

    @log_calls
    @property
    def get_dexterity_mod(self) -> int:
        """
        Retourne le modificateur de dextérité de l'armure.
        """
        return self.dexterity_mod