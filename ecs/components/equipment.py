class EquipmentComponent:
    def __init__(self):
        # Only one armor and one weapon of each type (melee, ranged, etc.)
        self.armor = None
        self.weapons = {"melee": None,
                        "ranged": None,
                        "mental": None,
                        "social": None,
                        "special": None}
        self.equipped_weapon = None
        self.other_items = []  # List of other items (e.g., consumables, tools, etc.)