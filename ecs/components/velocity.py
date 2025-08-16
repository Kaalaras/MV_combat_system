class VelocityComponent:
    def __init__(self, dexterity: int):
        self.dexterity = dexterity

    @property
    def run_distance(self):
        # 10 + 1/3 * Dexterity, rounded up
        import math
        return math.ceil(10 + (self.dexterity / 3))