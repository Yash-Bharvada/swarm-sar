"""Pygame visualizer kept separate from the simulation engine."""

from typing import TYPE_CHECKING

import numpy as np

from swarm_sar.world.cells import FREE, RUBBLE, UNKNOWN, WALL

if TYPE_CHECKING:
    from swarm_sar.sim.engine import SwarmWorld

COLORS = {UNKNOWN: (8, 10, 14), FREE: (205, 207, 204), WALL: (55, 58, 64), RUBBLE: (133, 91, 59)}
ROBOT_COLORS = [(45, 156, 219), (73, 190, 105), (247, 178, 50), (170, 95, 200), (242, 104, 104), (57, 196, 187), (240, 126, 55), (130, 155, 240), (210, 85, 160)]


class Renderer:
    def __init__(self, world: "SwarmWorld", cell_px: int | None = None, *, rgb_array: bool = False) -> None:
        import pygame

        self.pygame = pygame
        pygame.init()
        pygame.font.init()
        self.world = world
        self.cell_px = int(cell_px or world.sim_config["render_cell_px"])
        self.panel_width = 230
        height, width = world.grid.shape
        self.size = (width * self.cell_px + self.panel_width, height * self.cell_px)
        self.rgb_array_mode = rgb_array
        self.surface = pygame.Surface(self.size) if rgb_array else pygame.display.set_mode(self.size)
        if not rgb_array:
            pygame.display.set_caption("Swarm SAR")
        self.font = pygame.font.Font(None, max(16, self.cell_px))
        self.small_font = pygame.font.Font(None, 18)
        self.ground_truth = False
        self.show_vision = False
        self.debug_victims = False

    def _known_grid(self) -> np.ndarray:
        if not self.world.robots:
            return np.full(self.world.grid.shape, UNKNOWN, dtype=np.int8)
        return np.maximum.reduce([robot.belief for robot in self.world.robots])

    def toggle_ground_truth(self) -> None:
        self.ground_truth = not self.ground_truth

    def toggle_vision(self) -> None:
        self.show_vision = not self.show_vision

    def draw(self) -> np.ndarray | None:
        pygame, surface = self.pygame, self.surface
        surface.fill((22, 25, 31))
        view = self.world.grid if self.ground_truth else self._known_grid()
        height, width = view.shape
        for y in range(height):
            for x in range(width):
                pygame.draw.rect(surface, COLORS[int(view[y, x])], (x * self.cell_px, y * self.cell_px, self.cell_px, self.cell_px))

        if self.show_vision:
            overlay = pygame.Surface(self.size, pygame.SRCALPHA)
            for robot in self.world.robots:
                if robot.alive:
                    radius = int(
                        self.world.robot_configs[robot.type]["vision_radius"]
                    ) * self.cell_px
                    center = (robot.x * self.cell_px + self.cell_px // 2, robot.y * self.cell_px + self.cell_px // 2)
                    pygame.draw.circle(overlay, (80, 180, 255, 35), center, radius, 1)
            surface.blit(overlay, (0, 0))

        for victim in self.world.victims:
            if victim["found"] or self.debug_victims or self.ground_truth:
                center = (victim["x"] * self.cell_px + self.cell_px // 2, victim["y"] * self.cell_px + self.cell_px // 2)
                pygame.draw.circle(surface, (220, 45, 55), center, max(3, self.cell_px // 3))
        for robot in self.world.robots:
            color = ROBOT_COLORS[robot.id % len(ROBOT_COLORS)] if robot.alive else (90, 90, 90)
            rect = pygame.Rect(robot.x * self.cell_px + 2, robot.y * self.cell_px + 2, self.cell_px - 4, self.cell_px - 4)
            if robot.type == "drone":
                pygame.draw.circle(surface, color, rect.center, max(3, rect.width // 2))
            else:
                pygame.draw.rect(surface, color, rect, border_radius=max(1, self.cell_px // 4))
            label = self.font.render(
                f"{'D' if robot.type == 'drone' else 'R'}{robot.id}",
                True,
                (5, 8, 12),
            )
            surface.blit(label, label.get_rect(center=rect.center))

        panel_x = width * self.cell_px
        pygame.draw.rect(surface, (28, 32, 40), (panel_x, 0, self.panel_width, height * self.cell_px))
        metrics = self.world.metrics_snapshot()
        lines = [f"View: {'truth' if self.ground_truth else 'known map'}", f"Step: {self.world.step_count}", f"Victims: {metrics['victims_found']}/{len(self.world.victims)}", f"Coverage: {metrics['coverage']:.1%}", f"Collisions: {metrics['collisions']}", "", "G view  V vision"]
        y = 15
        for line in lines:
            surface.blit(self.small_font.render(line, True, (235, 238, 244)), (panel_x + 12, y))
            y += 21
        y += 8
        for robot in self.world.robots:
            short_name = f"{'D' if robot.type == 'drone' else 'R'}{robot.id}"
            surface.blit(self.small_font.render(short_name, True, ROBOT_COLORS[robot.id % len(ROBOT_COLORS)]), (panel_x + 12, y))
            bar = pygame.Rect(panel_x + 45, y + 2, 150, 12)
            pygame.draw.rect(surface, (68, 72, 80), bar)
            filled = bar.copy()
            full_battery = float(self.world.robot_configs[robot.type]["battery"])
            filled.width = int(bar.width * robot.battery / full_battery)
            pygame.draw.rect(surface, (72, 190, 105) if robot.alive else (120, 70, 70), filled)
            y += 24

        if self.rgb_array_mode:
            return np.transpose(pygame.surfarray.array3d(surface), (1, 0, 2))
        pygame.display.flip()
        return None

    def close(self) -> None:
        self.pygame.quit()
