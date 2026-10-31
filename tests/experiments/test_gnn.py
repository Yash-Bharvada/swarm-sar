"""Behavioral gates for the optional received-message graph branch."""
import pytest
import copy
import torch
from ray.rllib.core.columns import Columns
from ray.rllib.core.rl_module.rl_module import RLModule
from ray.rllib.core.rl_module.rl_module import RLModuleSpec

from experiments.gnn.attention import LOCAL_VALUES, ReceivedPeerAttention
from experiments.gnn.config import build_gnn_ppo_config, experiment_config
from experiments.gnn.module import GraphResidualPPOModule, warm_start_actor
from swarm_sar.learning.observation import policy_observation_space
from swarm_sar.learning.rllib_module import SwarmActionMaskingTorchRLModule
from gymnasium.spaces import Discrete


def observations():
    torch.manual_seed(13)
    obs = torch.rand(2, 3, 229) * 2 - 1
    peers = obs[..., LOCAL_VALUES:].reshape(2, 3, 8, 11)
    peers[..., 0] = 0
    peers[..., :2, 0] = 1
    return obs


def test_graph_branch_is_peer_permutation_invariant_and_padding_has_no_influence():
    graph = ReceivedPeerAttention(16)
    obs = observations()
    message, weights = graph.aggregate(obs)
    changed = obs.clone()
    peers = changed[..., LOCAL_VALUES:].reshape(2, 3, 8, 11)
    peers[..., 2:, 1:] = float("nan")
    torch.testing.assert_close(graph.aggregate(changed)[0], message)
    permutation = torch.tensor([5, 1, 7, 0, 3, 2, 4, 6])
    changed[..., LOCAL_VALUES:] = peers[..., permutation, :].flatten(-2)
    torch.testing.assert_close(graph.aggregate(changed)[0], message)
    assert torch.count_nonzero(weights[..., 3:]) == 0
    torch.testing.assert_close(weights.sum(-1), torch.ones(2, 3))


def test_no_peer_has_only_self_attention_and_batch_sequence_shapes_work():
    graph = ReceivedPeerAttention()
    for shape in ((229,), (3, 229), (2, 4, 229)):
        obs = torch.zeros(shape)
        output, weights = graph(obs)
        assert output.shape == obs.shape
        assert torch.isfinite(output).all()
        assert torch.all(weights[..., 0] == 1)
        assert torch.count_nonzero(weights[..., 1:]) == 0
        torch.testing.assert_close(output, obs, rtol=0, atol=0)
    with pytest.raises(ValueError):
        graph(torch.zeros(129))


def test_graph_learns_after_zero_residual_warm_start():
    graph = ReceivedPeerAttention(16)
    obs = observations()
    optimizer = torch.optim.Adam(graph.parameters(), lr=0.01)
    before = graph.peer_encoder[0].weight.detach().clone()
    for _ in range(3):
        optimizer.zero_grad()
        output, _ = graph(obs)
        loss = (output[..., :12] - 0.25).square().mean()
        loss.backward()
        assert all(p.grad is None or torch.isfinite(p.grad).all() for p in graph.parameters())
        optimizer.step()
    assert not torch.equal(before, graph.peer_encoder[0].weight)
    assert not torch.equal(graph(obs)[0], obs)


def module(cls, recurrent=False):
    return RLModuleSpec(module_class=cls, observation_space=policy_observation_space(),
                        action_space=Discrete(7), model_config={
                            "fcnet_hiddens": [16], "use_lstm": recurrent,
                            "lstm_cell_size": 16, "max_seq_len": 4,
                            "vf_share_layers": False,
                        }).build()


@pytest.mark.parametrize("recurrent", [False, True])
def test_warm_start_preserves_logits_masks_and_checkpoint(tmp_path, recurrent):
    baseline = module(SwarmActionMaskingTorchRLModule, recurrent)
    candidate = module(GraphResidualPPOModule, recurrent)
    warm_start_actor(candidate, baseline)
    obs = observations() if recurrent else observations()[:, 0]
    mask = torch.ones((*obs.shape[:-1], 7))
    mask[..., 1] = 0
    batch = {Columns.OBS: {"observations": obs, "action_mask": mask}}
    if recurrent:
        from swarm_sar.learning.behavior_cloning import initial_state_for_batch
        batch[Columns.STATE_IN] = initial_state_for_batch(candidate, 2, torch.device("cpu"))
    original = baseline.forward_inference(batch)[Columns.ACTION_DIST_INPUTS]
    output = candidate.forward_inference(batch)[Columns.ACTION_DIST_INPUTS]
    torch.testing.assert_close(original, output, rtol=0, atol=0)
    assert (output.argmax(-1) != 1).all()
    # Verify a trained/nonzero graph branch, not just an identity checkpoint.
    with torch.no_grad():
        candidate.graph_adapter.residual.weight.normal_(std=0.01)
    expected = candidate.forward_inference(batch)[Columns.ACTION_DIST_INPUTS]
    path = candidate.save_to_path(str(tmp_path / "actor"))
    restored = RLModule.from_checkpoint(path)
    torch.testing.assert_close(expected, restored.forward_inference(batch)[Columns.ACTION_DIST_INPUTS])
    torch.testing.assert_close(candidate.attention_for(obs), restored.attention_for(obs))
    # Exercise PPO actor and critic training paths and real gradients.
    result = candidate.forward_train(batch)
    loss = result[Columns.ACTION_DIST_INPUTS][..., 0].mean() + candidate.compute_values(batch).square().mean()
    loss.backward()
    assert candidate.graph_adapter.residual.weight.grad is not None
    assert torch.isfinite(candidate.graph_adapter.residual.weight.grad).all()


def test_experiment_specs_select_graph_actor_for_both_types():
    config = build_gnn_ppo_config(experiment_config(smoke=True))
    assert set(config.rl_module_spec.rl_module_specs) == {"rover_policy", "drone_policy"}
    assert all(s.module_class is GraphResidualPPOModule for s in config.rl_module_spec.rl_module_specs.values())


def test_invalid_flags_and_nonfinite_valid_data_fail_closed():
    graph = ReceivedPeerAttention()
    for value in (float("nan"), float("inf"), -1, 0.5):
        obs = torch.zeros(229)
        obs[LOCAL_VALUES] = value
        with pytest.raises(ValueError):
            graph(obs)
    obs = torch.zeros(229)
    obs[LOCAL_VALUES] = 1
    obs[LOCAL_VALUES + 1] = float("nan")
    with pytest.raises(ValueError):
        graph(obs)


def test_graph_uses_delivered_observations_and_network_off_has_no_peer_edges():
    from swarm_sar.learning.env import VariableSwarmRLlibEnv
    graph = ReceivedPeerAttention()
    for enabled in (False, True):
        env = VariableSwarmRLlibEnv({"curriculum": False, "fixed_team_profile": {"rover": 2, "drone": 2},
            "world_sizes": [24], "max_steps": 8, "network_enabled": enabled,
            "sim_overrides": {"network_packet_loss": 0.0, "network_delay_steps": [1, 1]}})
        try:
            obs, _ = env.reset(seed=10000)
            if enabled:
                assert all(torch.count_nonzero(torch.as_tensor(o["observations"][-88:]).reshape(8, 11)[:, 0]) == 0 for o in obs.values())
            obs, _, _, _, _ = env.step({name: 6 for name in env.agents})
            valid_count = 0
            for observation in obs.values():
                encoded = torch.as_tensor(observation["observations"])
                flags = encoded[-88:].reshape(8, 11)[:, 0].bool()
                _, weights = graph(encoded)
                assert torch.count_nonzero(weights[1:][~flags]) == 0
                valid_count += int(flags.sum())
            assert (valid_count > 0) == enabled
        finally:
            env.close()


def test_artifact_verification_rejects_corruption_and_source_change(tmp_path, monkeypatch):
    from experiments.gnn import artifacts
    from experiments.gnn.attention import ARCHITECTURE
    from swarm_sar.learning.release import atomic_json, tree_manifest
    monkeypatch.setattr(artifacts, "source_hashes", lambda: {"encoder.py": "source-v1"})
    (tmp_path / "weights.bin").write_bytes(b"checkpoint")
    manifest = {"architecture": ARCHITECTURE, "final_seeds_used": False,
                "files": tree_manifest(tmp_path), "source_sha256": artifacts.source_hashes()}
    atomic_json(tmp_path / "manifest.json", manifest)
    assert artifacts.verified_manifest(tmp_path) == manifest
    (tmp_path / "weights.bin").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        artifacts.verified_manifest(tmp_path)
    (tmp_path / "weights.bin").write_bytes(b"checkpoint")
    monkeypatch.setattr(artifacts, "source_hashes", lambda: {"encoder.py": "source-v2"})
    with pytest.raises(ValueError, match="source differs"):
        artifacts.verified_manifest(tmp_path)


def test_paired_comparison_rejects_changed_budgets_fleets_and_missing_cases():
    from experiments.gnn.artifacts import assert_paired_reports
    row = {"seed": 10000, "survivors_total": 4, "rover_count": 2,
           "drone_count": 2, "network_enabled": True}
    report = {"final_seeds_used": False, "seed_split": "development", "seeds": [10000],
              "fixed_seeds": [10000], "shadow_seeds": [], "cohorts": {
                  "rooms": {"definition": {"world_size": 32}, "effective_max_steps": 400, "episodes": [row]}}}
    assert_paired_reports(report, copy.deepcopy(report))
    for field, value in (("effective_max_steps", 800), ("definition", {"world_size": 56}), ("episodes", [])):
        changed = copy.deepcopy(report)
        changed["cohorts"]["rooms"][field] = value
        with pytest.raises(ValueError):
            assert_paired_reports(report, changed)
    changed = copy.deepcopy(report)
    changed["cohorts"]["rooms"]["episodes"][0]["drone_count"] = 3
    with pytest.raises(ValueError):
        assert_paired_reports(report, changed)


def test_zeroing_graph_is_a_real_action_logit_ablation():
    candidate = module(GraphResidualPPOModule)
    obs = observations()[:, 0]
    batch = {Columns.OBS: {"observations": obs, "action_mask": torch.ones(2, 7)}}
    before = candidate.forward_inference(batch)[Columns.ACTION_DIST_INPUTS].detach().clone()
    with torch.no_grad():
        candidate.graph_adapter.residual.weight.normal_(std=0.5)
    active = candidate.forward_inference(batch)[Columns.ACTION_DIST_INPUTS]
    assert not torch.allclose(before, active)
    with torch.no_grad():
        candidate.graph_adapter.residual.weight.zero_()
        candidate.graph_adapter.residual.bias.zero_()
    torch.testing.assert_close(candidate.forward_inference(batch)[Columns.ACTION_DIST_INPUTS], before)
