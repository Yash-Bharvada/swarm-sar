import json

import numpy as np

from swarm_sar.mapping.topology import AgentTopologicalMap
from swarm_sar.sim.planning import frontier_candidates
from swarm_sar.world.cells import FREE, UNKNOWN


def test_private_belief_compresses_to_attributed_graph(tmp_path):
    belief = np.full((14, 14), UNKNOWN, dtype=np.int8)
    belief[2:9, 2:9] = FREE
    belief[5, 9:12] = FREE
    candidates = frontier_candidates(belief, (4, 4))
    topology = AgentTopologicalMap("rover_0")
    topology.update(
        belief,
        candidates,
        step=10,
        pose_uncertainty=0.2,
        can_cross_rubble=True,
    )
    kinds = topology.node_kind_counts()
    assert kinds["room"] >= 1
    assert kinds["frontier"] >= 1
    assert topology.graph.number_of_edges() >= 1
    for _, _, data in topology.graph.edges(data=True):
        assert {
            "estimated_distance",
            "traversability",
            "observation_confidence",
            "last_update",
        } <= set(data)
    edge = next(iter(topology.graph.edges))
    assert topology.shortest_topological_path(edge[0], edge[1]) == [edge[0], edge[1]]
    path = topology.save_json(tmp_path / "graph.json")
    payload = json.loads(path.read_text())
    assert payload["graph"]["owner"] == "rover_0"


def test_suspected_site_becomes_confirmed_marker():
    topology = AgentTopologicalMap("drone_2")
    topology.add_suspected_survivor((5, 5), 0.6, 3)
    assert topology.node_kind_counts() == {"survivor_suspected": 1}
    topology.mark_survivor_confirmed((6, 5), 0.9, 4)
    assert topology.node_kind_counts() == {"survivor_confirmed": 1}


def test_survivor_marker_connects_to_existing_graph():
    topology = AgentTopologicalMap("rover_1")
    room = topology._upsert_spatial_node("room", (2, 2), 1, 1.0)
    marker = topology.mark_survivor_confirmed((5, 2), 0.9, 2)
    assert topology.graph.has_edge(room, marker)
    assert topology.graph.edges[room, marker]["traversability"] == "estimated"


def test_early_marker_connects_when_map_structure_appears():
    belief = np.full((12, 12), UNKNOWN, dtype=np.int8)
    topology = AgentTopologicalMap("drone_3")
    marker = topology.mark_survivor_confirmed((6, 6), 0.8, 1)
    assert topology.graph.degree(marker) == 0
    belief[2:10, 2:10] = FREE
    candidates = frontier_candidates(belief, (4, 4))
    topology.update(belief, candidates, 2, 0.1, can_cross_rubble=True)
    assert topology.graph.degree(marker) >= 1
