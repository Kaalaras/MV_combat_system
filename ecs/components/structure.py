class StructureComponent:
    """Generic static structure (decor) durability component.

    Attributes:
        vigor_max: maximum vigor (HP equivalent)
        vigor: current remaining vigor
        armor_level: abstract level; for cover we fix 8 (spec) and use to halve superficial damage
    """
    def __init__(self, vigor_max: int, armor_level: int):
        self.vigor_max = vigor_max
        self.vigor = vigor_max
        self.armor_level = armor_level

    def apply_damage(self, amount: int, damage_type: str) -> int:
        """Apply damage to structure. Superficial damage is halved (rounded up) by armor.
        Returns effective damage actually subtracted.
        """
        if amount <= 0:
            return 0
        effective = amount
        if damage_type.startswith('superficial'):
            # Halve, rounding up to ensure progress
            effective = (amount + 1) // 2
        if effective <= 0:
            effective = 1  # ensure at least chip damage
        if effective > self.vigor:
            effective = self.vigor
        self.vigor -= effective
        return effective

    @property
    def destroyed(self) -> bool:
        return self.vigor <= 0

