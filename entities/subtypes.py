from entities.character import Character

class Mortal(Character):
    pass

class Human(Mortal):
    pass

class Animal(Mortal):
    pass

class GhoulMixin:
    """Mixin providing Hunger logic. Character already has hunger attribute slot."""
    def set_hunger(self, value: int):
        self.hunger = max(0, min(5, value))

    def add_hunger(self, delta: int = 1):
        self.set_hunger(self.hunger + delta)

class Undead(Character):
    """Undead halve superficial damage (rounded up) before application."""
    def take_damage(self, amount: int, damage_type: str = 'superficial', target: str = 'health') -> None:
        original_type = damage_type
        is_magic = False
        if damage_type.endswith('_magic'):
            is_magic = True
            damage_type = damage_type.replace('_magic', '')
        if damage_type == 'superficial':
            # Halve superficial damage rounded up
            amount = (amount + 1) // 2
        # Forward to base logic without magic suffix (base class doesn't distinguish)
        super().take_damage(amount, damage_type=damage_type, target=target)

class Vampire(Undead, GhoulMixin):
    pass

class Zombie(Undead):
    pass

class Ghost(Undead):
    """Ghosts immune to non-magic damage."""
    def take_damage(self, amount: int, damage_type: str = 'superficial', target: str = 'health') -> None:
        if not damage_type.endswith('_magic'):
            # Ignore all non-magic damage
            return
        base_type = damage_type.replace('_magic', '')
        # Apply undead halving for superficial via Undead.take_damage path
        super().take_damage(amount, damage_type=damage_type, target=target)

__all__ = [
    'Mortal', 'Human', 'Animal', 'GhoulMixin', 'Undead', 'Vampire', 'Zombie', 'Ghost'
]

