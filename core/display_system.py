class DisplaySystem:
    def __init__(self, game_state):
        self.game_state = game_state

    def render(self):
        terrain = self.game_state.terrain
        grid = [["." for _ in range(terrain.width)] for _ in range(terrain.height)]
        for entity_id, components in self.game_state.entities.items():
            pos = components.get("position")
            if pos:
                grid[pos.y][pos.x] = entity_id[0].upper()
        print("\n".join(" ".join(row) for row in grid))
        print()