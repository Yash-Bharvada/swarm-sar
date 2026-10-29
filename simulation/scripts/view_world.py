"""View deterministic generated worlds. Space advances to the next seed."""

import argparse

from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.viz.renderer import Renderer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    world = SwarmWorld()
    world.reset(args.seed)
    renderer = Renderer(world)
    renderer.ground_truth = True
    current = 0
    clock = renderer.pygame.time.Clock()
    running = True
    while running:
        renderer.draw()
        for event in renderer.pygame.event.get():
            if event.type == renderer.pygame.QUIT:
                running = False
            elif event.type == renderer.pygame.KEYDOWN:
                if event.key in (renderer.pygame.K_ESCAPE, renderer.pygame.K_q):
                    running = False
                elif event.key in (renderer.pygame.K_SPACE, renderer.pygame.K_n):
                    current += 1
                    if current >= args.count:
                        running = False
                    else:
                        world.reset(args.seed + current)
                elif event.key == renderer.pygame.K_g:
                    renderer.toggle_ground_truth()
                elif event.key == renderer.pygame.K_v:
                    renderer.toggle_vision()
        clock.tick(30)
    renderer.close()


if __name__ == "__main__":
    main()
