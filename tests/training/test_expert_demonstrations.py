import numpy as np
import pytest

from swarm_sar.learning.demonstrations import (
    DemonstrationWriter,
    dataset_summary,
    validate_dataset,
    sha256_file,
    PolicyCompatibleExpert,
    expert_case,
)
from swarm_sar.sim.env import DisasterResponseParallelEnv


def test_writer_round_trip_and_corruption_detection(tmp_path):
    env = DisasterResponseParallelEnv()
    observations, _ = env.reset(seed=91)
    agent = env.agents[0]
    writer = DemonstrationWriter(tmp_path / "dataset", chunk_size=1)
    writer.add(
        observation=observations[agent],
        action=6,
        robot_type=env._robots_by_name[agent].type,
        seed=91,
        step=0,
        agent_index=0,
        packet_loss=0.0,
        team_size=len(env.agents),
    )
    writer.finish(
        [{"survivors_found": 0, "survivors_total": 1, "seed": 91}]
    )
    manifest = validate_dataset(tmp_path / "dataset")
    assert manifest["rows"] == 1
    summary = dataset_summary(tmp_path / "dataset", display_path="test/dataset")
    assert summary["dataset_path"] == "test/dataset"
    assert summary["rows"] == 1
    assert summary["episode_seed_range"] == [91, 91]
    chunk = tmp_path / "dataset" / manifest["chunks"][0]["path"]
    chunk.write_bytes(chunk.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="Corrupt"):
        validate_dataset(tmp_path / "dataset")
    env.close()


def test_legacy_identity_dataset_is_rejected(tmp_path):
    import json
    output = tmp_path / "legacy"
    output.mkdir()
    (output / "manifest.json").write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(ValueError, match="legacy"):
        validate_dataset(output)


def test_expert_actions_preserve_emitted_observation_and_frontier_slots():
    world, robots, sim, config, _ = expert_case(5)
    env = DisasterResponseParallelEnv(world_config=world, robot_config=robots, sim_config=sim)
    expert = PolicyCompatibleExpert(env, config)
    observations = expert.reset(5)
    try:
        for _ in range(50):
            if not env.agents:
                break
            goals = dict(env._active_goals)
            before = {
                agent: {name: value.copy() for name, value in observations[agent].items()}
                for agent in env.agents
            }
            candidate_positions = {
                agent: [tuple(candidate["position"]) for candidate in env._candidate_list(agent)]
                for agent in env.agents
            }
            actions = expert.choose_actions()
            assert env._active_goals == goals
            for agent, action in actions.items():
                fresh = env.observe(agent)
                assert all(np.array_equal(value, fresh[name]) for name, value in before[agent].items())
                assert before[agent]["action_mask"][action] > 0
                if action < 5:
                    assert tuple(env._candidate_list(agent)[action]["position"]) == candidate_positions[agent][action]
            observations, *_ = env.step(actions)
            expert.observations = observations
    finally:
        env.close()


def test_dataset_rejects_robot_identity_policy_switch(tmp_path):
    from swarm_sar.learning.demonstrations import collect_episode
    import json
    output = tmp_path / "switched"
    writer = DemonstrationWriter(output, chunk_size=50000)
    episode = collect_episode(1, writer)
    manifest = writer.finish([episode])
    chunk = output / manifest["chunks"][0]["path"]
    with np.load(chunk) as values:
        fields = {name: values[name].copy() for name in values.files}
    indices = np.flatnonzero(fields["agent_indices"] == fields["agent_indices"][0])
    fields["policy_ids"][indices[-1]] = 1 - fields["policy_ids"][indices[-1]]
    np.savez_compressed(chunk, **fields)
    manifest["chunks"][0]["sha256"] = sha256_file(chunk)
    (output / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="identity"):
        validate_dataset(output)


@pytest.mark.parametrize("damage", ["final_seed", "missing_field"])
def test_dataset_rejects_sealed_seed_and_missing_row_metadata(tmp_path, damage):
    from swarm_sar.learning.demonstrations import collect_episode
    import json
    output = tmp_path / damage
    writer = DemonstrationWriter(output, chunk_size=50000)
    manifest = writer.finish([collect_episode(2, writer)])
    if damage == "final_seed":
        manifest["episodes"][0]["seed"] = 20000
    else:
        chunk = output / manifest["chunks"][0]["path"]
        with np.load(chunk) as values:
            fields = {name: values[name].copy() for name in values.files if name != "agent_indices"}
        np.savez_compressed(chunk, **fields)
        manifest["chunks"][0]["sha256"] = sha256_file(chunk)
    (output / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="training split|Missing required"):
        validate_dataset(output)


def test_writer_rejects_masked_action_and_existing_dataset(tmp_path):
    env = DisasterResponseParallelEnv()
    observations, _ = env.reset(seed=92)
    agent = env.agents[0]
    invalid = int(np.flatnonzero(observations[agent]["action_mask"] == 0)[0])
    output = tmp_path / "dataset"
    writer = DemonstrationWriter(output, chunk_size=10)
    with pytest.raises(ValueError, match="masked"):
        writer.add(
            observation=observations[agent],
            action=invalid,
            robot_type=env._robots_by_name[agent].type,
            seed=92,
            step=0,
            agent_index=0,
            packet_loss=0.0,
            team_size=len(env.agents),
        )
    (output / "sentinel").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        DemonstrationWriter(output)
    env.close()
