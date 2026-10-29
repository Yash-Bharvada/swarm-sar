import numpy as np

from swarm_sar.sim.planning import astar_path, frontier_candidates, frontier_clusters
from swarm_sar.world.cells import FREE, UNKNOWN, WALL


def test_frontier_detection_uses_only_local_belief():
    belief = np.full((7, 7), UNKNOWN, dtype=np.int8)
    belief[2:5, 2:5] = FREE
    clusters = frontier_clusters(belief)
    cells = {cell for cluster in clusters for cell in cluster}
    assert (3, 3) not in cells
    assert (2, 2) in cells and (4, 4) in cells


def test_astar_routes_around_known_wall():
    belief = np.full((7, 7), FREE, dtype=np.int8)
    belief[1:6, 3] = WALL
    belief[5, 3] = FREE
    path = astar_path(belief, (1, 2), (5, 2))
    assert path[0] == (1, 2) and path[-1] == (5, 2)
    assert all(belief[y, x] != WALL for x, y in path)
    assert len(path) > 5


def test_frontier_candidates_include_reachable_paths():
    belief = np.full((9, 9), UNKNOWN, dtype=np.int8)
    belief[2:7, 2:7] = FREE
    candidates = frontier_candidates(belief, (4, 4), max_candidates=5)
    assert 1 <= len(candidates) <= 5
    assert all(candidate["path"][0] == (4, 4) for candidate in candidates)


def test_multi_sample_candidates_surface_distinct_branches_first():
    belief = np.full((9, 15), WALL, dtype=np.int8)
    belief[4, 1:14] = FREE
    belief[3, 3] = UNKNOWN
    belief[5, 11] = UNKNOWN
    candidates = frontier_candidates(
        belief, (7, 4), max_candidates=2, max_per_cluster=5
    )
    assert {candidate["position"] for candidate in candidates} == {(3, 4), (11, 4)}
