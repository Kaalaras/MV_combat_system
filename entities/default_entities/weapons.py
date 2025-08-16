from entities.weapon import Weapon, WeaponType
from entities.effects import PenetrationEffect, RadiusAoE, ConeAoE

class Fists(Weapon):
    """Default weapon that deals superficial damage"""
    def __init__(self) -> None:
        super().__init__(
            name="Fists",
            damage_bonus=0,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.BRAWL,
            icon_path="assets/sprites/weapons/fists.png",
            infinite_ammunition=True,
            reloadable=False
        )

class Knucles(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="KnucleFists",
            damage_bonus=1,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.BRAWL,
            icon_path="assets/sprites/weapons/knucle_fists.png",
            infinite_ammunition=True,
            reloadable=False
        )


class Club(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Club",
            damage_bonus=2,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/club.png",
            infinite_ammunition=True,
            reloadable=False
        )


class Staff(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Staff",
            damage_bonus=2,
            weapon_range=3,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/staff.png",
            infinite_ammunition=True,
            reloadable=False
        )


class SafetyKnife(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Knife with lock",
            damage_bonus=2,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/safety_knife.png",
            infinite_ammunition=True,
            reloadable=False
        )


class FireCrossbow(Weapon):
    """Default weapon that deals aggravated damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Fire crossbow",
            damage_bonus=2,
            weapon_range=40,
            damage_type="aggravated",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/fire_crossbow.png"
        )


class Crossbow(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Crossbow",
            damage_bonus=2,
            weapon_range=60,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/crossbow.png"
        )


class LightPistol(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Light Pistol",
            damage_bonus=3,
            weapon_range=12,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/light pistol.png",
            max_ammunition=13,
            infinite_ammunition=False,
            reloadable=True,
            reload_action_type="secondary"
        )


class Merlin(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Merlin",
            damage_bonus=3,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/merlin.png",
            infinite_ammunition=True,
            reloadable=False
        )


class HeavyAxe(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Heavy Axe",
            damage_bonus=3,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/heavy_axe.png",
            infinite_ammunition=True,
            reloadable=False
        )


class Sword(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Sword",
            damage_bonus=3,
            weapon_range=1,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/sword.png",
            infinite_ammunition=True,
            reloadable=False
        )


class Pistol(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Pistol",
            damage_bonus=3,
            weapon_range=20,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/pistol.png"
        )


class Carbin(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Carbin",
            damage_bonus=3,
            weapon_range=120,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/fists.png"
        )


class Shotgun(Weapon):
    """Default weapon that deals superficial damage and hits in a cone."""

    def __init__(self) -> None:
        super().__init__(
            name="Shotgun",
            damage_bonus=4,
            weapon_range=12,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/shotgun.png",
            effects=[ConeAoE(length=12, angle=30, decay=0.75)]
        )

class HeavyPistol(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Heavy Pistol",
            damage_bonus=4,
            weapon_range=20,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/shotgun.png"
        )

class TwoHandedSword(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Two handed sword",
            damage_bonus=4,
            weapon_range=3,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/two_handed_sword.png",
            infinite_ammunition=True,
            reloadable=False
        )

class SteelBeam(Weapon):
    """Default weapon that deals superficial damage"""

    def __init__(self) -> None:
        super().__init__(
            name="Steel Beam",
            damage_bonus=4,
            weapon_range=4,
            damage_type="superficial",
            weapon_type=WeaponType.MELEE,
            icon_path="assets/sprites/weapons/steel_beam.png",
            infinite_ammunition=True,
            reloadable=False
        )

class AssaultRifle(Weapon):
    """Default weapon that deals superficial damage and has penetration."""

    def __init__(self) -> None:
        super().__init__(
            name="Assault Rifle",
            damage_bonus=4,
            weapon_range=80,
            damage_type="superficial",
            weapon_type=WeaponType.FIREARM,
            icon_path="assets/sprites/weapons/assault_rifle.png",
            effects=[PenetrationEffect(max_penetration=2)]
        )

class Grenade(Weapon):
    """Thrown weapon with an area of effect."""
    def __init__(self) -> None:
        super().__init__(
            name="Grenade",
            damage_bonus=4,
            weapon_range=15, # Can be thrown
            damage_type="aggravated",
            weapon_type=WeaponType.THROWING,
            max_ammunition=2,
            infinite_ammunition=False,
            reloadable=False,
            effects=[RadiusAoE(radius=5, decay=0.25)]
        )
