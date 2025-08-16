from entities.base_object import BaseObject
from utils.logger import log_calls
from typing import Optional, List

class Armor(BaseObject):
    __slots__ = ("name", "armor_value", "damage_type", "icon_path", "weapon_type_protected", "dexterity_mod")

    VALID_DAMAGE_TYPES = ("superficial", "aggravated")

    @log_calls
    def __init__(self, name: str,
                 armor_value: int,
                 damage_type: List[str],
                 weapon_type_protected: List[str],
                 dexterity_mod: int = 0,
                 icon_path: Optional[str] = None) -> None:
        super().__init__()
        for damage_type_elem in damage_type:
            if damage_type_elem not in self.VALID_DAMAGE_TYPES:
                raise ValueError(f"Invalid damage type '{damage_type_elem}'. Must be one of {self.VALID_DAMAGE_TYPES}.")
        self.name = name
        self.armor_value = armor_value
        self.damage_type = damage_type # type de dégâts que l'armure protège
        self.icon_path = icon_path  # chemin pour affichage futur, pas sprite immédiat
        self.weapon_type_protected = weapon_type_protected  # type d'arme que l'armure protège (one in : "melee", "ranged", "mental","social", "special")
        self.dexterity_mod = 0  # modificateur de dextérité

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