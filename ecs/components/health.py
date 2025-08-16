class HealthComponent:
    def __init__(self, max_health: int):
        self.max_health = max_health
        self.current_health = max_health
        self.superficial_damage = 0
        self.aggravated_damage = 0
