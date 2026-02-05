from __future__ import annotations
from dataclasses import dataclass


@dataclass
class DriftModel:
    alpha: float = 0.0
    beta: float = 1.0
    n: int = 0
    sum_t: float = 0.0
    sum_x: float = 0.0
    sum_tt: float = 0.0
    sum_tx: float = 0.0

    def reset(self, initial_track_time: float, initial_wall_time: float):
        self.alpha = initial_track_time
        self.beta = 1.0
        self.n = 0
        self.sum_t = 0.0
        self.sum_x = 0.0
        self.sum_tt = 0.0
        self.sum_tx = 0.0
        self.update(wall_time=initial_wall_time, track_time=initial_track_time)

    def update(self, wall_time: float, track_time: float):
        self.n += 1
        self.sum_t += wall_time
        self.sum_x += track_time
        self.sum_tt += wall_time * wall_time
        self.sum_tx += wall_time * track_time

        if self.n >= 2:
            denom = (self.n * self.sum_tt - self.sum_t * self.sum_t)
            if abs(denom) > 1e-9:
                self.beta = (self.n * self.sum_tx - self.sum_t * self.sum_x) / denom
                self.alpha = (self.sum_x - self.beta * self.sum_t) / self.n
                if self.beta < 0.90:
                    self.beta = 0.90
                if self.beta > 1.10:
                    self.beta = 1.10

    def predict(self, wall_time: float) -> float:
        return self.alpha + self.beta * wall_time
