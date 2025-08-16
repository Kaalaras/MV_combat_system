from entities.armor import Armor


class Clothes(Armor):
    """Default armor that provides no protection"""
    def __init__(self) -> None:
        super().__init__(
            name="Clothes",
            armor_value=0,
            damage_type=["superficial", "aggravated"],
            weapon_type_protected=["melee", "ranged", "mental", "social", "special"],
            icon_path="assets/sprites/armors/clothes.png"
        )

class HeavyClothes(Armor):
    """Armor that provides no protection against range attacks"""
    def __init__(self) -> None:
        super().__init__(
            name="Heavy Clothes",
            armor_value=2,
            damage_type=["superficial", "aggravated"],
            weapon_type_protected=["melee", ],
            icon_path="assets/sprites/armors/heavy_clothes.png",
        )

class ThickHide(Armor):
    """Armor that provides no protection against range attacks"""
    def __init__(self) -> None:
        super().__init__(
            name="Thick Hide",
            armor_value=2,
            damage_type=["superficial", "aggravated"],
            weapon_type_protected=["melee", ],
            icon_path="assets/sprites/armors/Thick hide.png",
        )

class BallisticNylonArmor(Armor):
    """Armor that provides small protection against physical attacks"""
    def __init__(self) -> None:
        super().__init__(
            name="Ballistic Nylon Armor",
            armor_value=2,
            damage_type=["superficial", "aggravated"],
            weapon_type_protected=["melee", "ranged"],
            icon_path="assets/sprites/armors/ballistic_nylon_armor.png",
        )

class KevlarJacket(Armor):
    """Armor that provides good protection against physical attacks"""
    def __init__(self) -> None:
        super().__init__(
            name="Kevlar Jacket",
            armor_value=4,
            damage_type=["superficial", "aggravated"],
            weapon_type_protected=["melee", "ranged"],
            icon_path="assets/sprites/armors/kevlar_jacket.png",
        )

class MilitaryArmor(Armor):
    """Armor that provides excellent protection against physical attacks"""
    def __init__(self) -> None:
        super().__init__(
            name="Military Armor",
            armor_value=6,
            damage_type=["superficial", "aggravated"],
            weapon_type_protected=["melee", "ranged"],
            icon_path="assets/sprites/armors/military_armor.png",
            dexterity_mod=-1
        )