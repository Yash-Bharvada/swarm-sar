import json

from swarm_sar.baselines.frontier import (
    CoordinatedFrontierBaseline,
    EvidenceBoard,
)


def test_evidence_requires_repeat_or_second_agent():
    board = EvidenceBoard(merge_radius=3, expiry_steps=10)
    cluster = board.record("rover_0", (5, 5), 0.5, 1)
    assert not cluster.ready(2)
    cluster = board.record("rover_0", (6, 5), 0.6, 2)
    assert cluster.ready(2)

    second = EvidenceBoard(merge_radius=3, expiry_steps=10)
    cluster = second.record("rover_0", (5, 5), 0.5, 1)
    cluster = second.record("drone_2", (6, 5), 0.5, 1)
    assert cluster.ready(3)


def test_baseline_coordinates_four_distinct_private_maps():
    baseline = CoordinatedFrontierBaseline()
    baseline.reset(0)
    assert len(baseline.maps) == 4
    assert len({id(mapping) for mapping in baseline.maps.values()}) == 4
    for _ in range(10):
        baseline.step()
    assert baseline.duplicate_goal_steps == 0
    assert len(set(baseline.goals.values())) == len(baseline.goals)
    assert all(mapping.graph.number_of_nodes() > 0 for mapping in baseline.maps.values())
    baseline.env.close()


def test_full_baseline_episode_confirms_survivors_and_saves_graphs(tmp_path):
    baseline = CoordinatedFrontierBaseline()
    summary = baseline.run_episode(0, tmp_path)
    assert summary["survivors_found"] == summary["survivors_total"]
    assert summary["collisions"] == 0
    assert summary["duplicate_goal_steps"] == 0
    assert summary["false_confirmations"] == 0
    assert summary["confirmed_markers"] >= summary["survivors_found"]
    graph_files = list((tmp_path / "topology").glob("*.json"))
    assert len(graph_files) == 4
    assert all(json.loads(path.read_text())["nodes"] for path in graph_files)
    baseline.env.close()


def test_baseline_replays_identically_for_same_seed():
    first = CoordinatedFrontierBaseline()
    second = CoordinatedFrontierBaseline()
    first_summary = first.run_episode(2)
    second_summary = second.run_episode(2)
    assert first_summary == second_summary
    assert first.events == second.events
    for agent in first.maps:
        assert first.maps[agent].graph.nodes == second.maps[agent].graph.nodes
        assert first.maps[agent].graph.edges == second.maps[agent].graph.edges
    first.env.close()
    second.env.close()
