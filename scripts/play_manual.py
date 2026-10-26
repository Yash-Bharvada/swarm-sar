"""Keyboard-controlled smoke test for movement and sensing."""

import argparse

from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.viz.renderer import Renderer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    world = SwarmWorld()
    world.reset(args.seed)
    renderer = Renderer(world)
    pygame = renderer.pygame
    clock = pygame.time.Clock()
    selected = 0
    key_actions = {pygame.K_UP: 1, pygame.K_DOWN: 2, pygame.K_LEFT: 3, pygame.K_RIGHT: 4}
    running = True
    while running:
        renderer.draw()
        robot = world.robots[selected]
        pygame.display.set_caption(f"Swarm SAR | rover {selected} | thermal {robot.thermal.round(2)} | acoustic {robot.acoustic[0]:.2f}")
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_TAB:
                    selected = (selected + 1) % len(world.robots)
                elif event.key == pygame.K_g:
                    renderer.toggle_ground_truth()
                elif event.key == pygame.K_v:
                    renderer.toggle_vision()
                elif event.key in key_actions and not world.done:
                    actions = [0] * len(world.robots)
                    actions[selected] = key_actions[event.key]
                    world.step(actions)
        clock.tick(int(world.sim_config["fps"]))
    renderer.close()


if __name__ == "__main__":
    main()
