"""Robot state."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from swarm_sar.world.cells import UNKNOWN


@dataclass
class Robot:
    id: int
    type: str
    x: int
    y: int
    battery: float
    belief: np.ndarray
    visited: np.ndarray
    odom_x: float
    odom_y: float
    odom_uncertainty: float = 0.0
    alive: bool = True
    last_action: int = 0
    collided: bool = False
    distance_travelled: int = 0
    thermal: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    acoustic: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.float32))
    prev_thermal: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    prev_acoustic: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.float32))

    @classmethod
    def create(
        cls,
        robot_id: int,
        robot_type: str,
        x: int,
        y: int,
        battery: float,
        shape: tuple[int, int],
    ) -> "Robot":
        belief = np.full(shape, UNKNOWN, dtype=np.int8)
        visited = np.zeros(shape, dtype=bool)
        visited[y, x] = True
        return cls(
            robot_id,
            robot_type,
            x,
            y,
            float(battery),
            belief,
            visited,
            float(x),
            float(y),
        )

    @property
    def position(self) -> tuple[int, int]:
        return self.x, self.y

    @property
    def name(self) -> str:
        return f"{self.type}_{self.id}"

    def as_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "battery": self.battery,
            "alive": self.alive,
            "odom_x": self.odom_x,
            "odom_y": self.odom_y,
            "odom_uncertainty": self.odom_uncertainty,
        }
