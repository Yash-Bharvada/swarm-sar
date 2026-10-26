import numpy as np

from swarm_sar.world.cells import FREE, WALL
from swarm_sar.world.reachability import bfs_distances, close_unreachable


def test_bfs_distances_on_handmade_grid():
    grid = np.array(
        [
            [WALL, WALL, WALL, WALL, WALL],
            [WALL, FREE, FREE, WALL, WALL],
            [WALL, WALL, FREE, FREE, WALL],
            [WALL, FREE, WALL, FREE, WALL],
            [WALL, WALL, WALL, WALL, WALL],
        ],
        dtype=np.int8,
    )
    distances = bfs_distances(grid, (1, 1))
    assert distances[1, 1] == 0
    assert distances[2, 2] == 2
    assert distances[3, 3] == 4
    assert distances[3, 1] == -1


def test_cleanup_closes_unreachable_cells():
    grid = np.full((5, 5), WALL, dtype=np.int8)
    grid[1, 1:3] = FREE
    grid[3, 3] = FREE
    cleaned, distances = close_unreachable(grid, (1, 1))
    assert cleaned[3, 3] == WALL
    assert np.all(distances[cleaned != WALL] >= 0)
