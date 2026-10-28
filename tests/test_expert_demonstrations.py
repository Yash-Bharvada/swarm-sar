import numpy as np
import pytest

from swarm_sar.learning.demonstrations import (
    DemonstrationWriter,
    dataset_summary,
    validate_dataset,
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
