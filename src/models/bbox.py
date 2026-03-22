from dataclasses import dataclass
from typing import Tuple

@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def width(self) -> float:
        return self.x2 - self.x1

    def height(self) -> float:
        return self.y2 - self.y1

    def area(self) -> float:
        return self.width() * self.height()

    def center(self) -> Tuple[float, float]:
        return (
            (self.x1 + self.x2) / 2,
            (self.y1 + self.y2) / 2
        )
