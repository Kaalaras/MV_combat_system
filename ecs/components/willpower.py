class WillpowerComponent:
    def __init__(self, max_willpower: int):
        self.max_willpower = max_willpower
        self.current_willpower = max_willpower
        self.superficial_damage = 0
        self.aggravated_damage = 0