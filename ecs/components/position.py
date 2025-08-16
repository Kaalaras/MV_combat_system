class PositionComponent:
    def __init__(self, x: int, y: int, width: int = 1, height: int = 1):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    @property
    def x1(self) -> int:
        return self.x

    @property
    def y1(self) -> int:
        return self.y

    @property
    def x2(self) -> int:
        return self.x + self.width - 1

    @property
    def y2(self) -> int:
        return self.y + self.height - 1
