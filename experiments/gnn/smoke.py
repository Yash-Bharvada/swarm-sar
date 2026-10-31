"""CPU-only warm-start/rollout/restore evidence; no Ray cluster or training job.

Run: .venv/bin/python -m experiments.gnn.smoke --output training/runs/gnn_smoke
Requires the already extracted selected checkpoint (npm run swarm prepares it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch
from ray.rllib.core.rl_module.rl_module import RLModule, RLModuleSpec

from experiments.gnn.attention import ARCHITECTURE
from experiments.gnn.module import GraphResidualPPOModule, warm_start_actor
from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.inference import initial_policy_state, policy_step
from swarm_sar.learning.release import atomic_json, file_hash
from swarm_sar.learning.training import policy_mapping_fn
from swarm_sar.validation.seeds import load_seed_splits

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664"


def verified_originals(checkpoint):
    """Verify complete selected tree before executing trusted checkpoint restore."""
    checkpoint = checkpoint.resolve()
    digest = hashlib.sha256()
    for path in sorted(checkpoint.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(checkpoint).as_posix().encode())
            digest.update(path.read_bytes())
    expected = json.loads((ROOT / "models/ppo_754k/ppo_754k_review.json").read_text())
    if digest.hexdigest() != expected["checkpoint_provenance"]["tree_sha256"]:
        raise ValueError("Use the verified selected 754k checkpoint; tree digest differs")
    actors = checkpoint / "learner_group/learner/rl_module"
    modules = {name: RLModule.from_checkpoint(str(actors / name)).to("cpu").eval()
               for name in ("rover_policy", "drone_policy")}
    return modules, digest.hexdigest()


def hybrid(original):
    module = RLModuleSpec(module_class=GraphResidualPPOModule,
                          observation_space=original.observation_space,
                          action_space=original.action_space,
                          model_config={**original.model_config, "graph_width": 64},
                          inference_only=original.inference_only).build().to("cpu").eval()
    warm_start_actor(module, original)
    return module


def episode(modules, seed, steps):
    env = VariableSwarmRLlibEnv({"curriculum": False, "domain_randomization": False,
        "fixed_team_profile": {"rover": 2, "drone": 2}, "world_sizes": [32],
        "max_steps": steps, "network_enabled": True,
        "world_overrides": {"layout": "rooms", "footprint": "full", "max_generation_retries": 100}})
    try:
        observations, _ = env.reset(seed=seed)
        states = {agent: initial_policy_state(modules[policy_mapping_fn(agent)]) for agent in env.agents}
        trace = []
        attention_checks = 0
        while env.agents:
            actions = {}
            for agent, obs in observations.items():
                actor = modules[policy_mapping_fn(agent)]
                actions[agent], states[agent] = policy_step(actor, obs, None, states[agent])
                if isinstance(actor, GraphResidualPPOModule):
                    with torch.no_grad():
                        weights = actor.attention_for(torch.as_tensor(obs["observations"]))
                    valid = obs["observations"][-88:].reshape(8, 11)[:, 0] > 0.5
                    assert torch.count_nonzero(weights[1:][~torch.as_tensor(valid)]) == 0
                    assert torch.isfinite(weights).all()
                    attention_checks += 1
            observations, _, _, _, _ = env.step(actions)
            core = env.env.core
            trace.append({"actions": actions, "agents": [(r.name, r.x, r.y, r.battery) for r in core.robots],
                          "found": core.metrics.victims_found})
        metrics = env.metrics_snapshot()
        return {"steps": len(trace), "survivors_found": metrics["victims_found"],
                "survivors_total": metrics["survivors_total"], "coverage": metrics["coverage"],
                "invalid_actions": metrics["invalid_actions"], "attention_checks": attention_checks,
                "trace_sha256": hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()}
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=10000)
    parser.add_argument("--steps", type=int, default=400)
    args = parser.parse_args()
    if args.seed not in load_seed_splits()["development"] or not 1 <= args.steps <= 400:
        parser.error("Choose a development seed and 1–400 steps")
    output = args.output.resolve()
    if output.exists():
        parser.error("Use a new output directory; prior evidence is preserved")
    torch.set_num_threads(1)
    torch.manual_seed(42)
    originals, digest = verified_originals(args.checkpoint)
    candidates = {name: hybrid(original) for name, original in originals.items()}
    output.mkdir(parents=True)
    baseline = episode(originals, args.seed, args.steps)
    candidate = episode(candidates, args.seed, args.steps)
    assert baseline["trace_sha256"] == candidate["trace_sha256"], "Warm start changed the trajectory"
    restored = {}
    for name, actor in candidates.items():
        path = actor.save_to_path(str(output / name))
        restored[name] = RLModule.from_checkpoint(path).to("cpu").eval()
    replay = episode(restored, args.seed, args.steps)
    assert candidate == replay, "Checkpoint restore changed the rollout"
    sources = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted((ROOT / "experiments/gnn").glob("*.py"))}
    report = {"architecture": ARCHITECTURE, "stage": "untrained_zero_residual_warm_start",
              "gpu_used": False, "training_started": False, "seed": args.seed,
              "final_seeds_used": False, "original_tree_sha256": digest,
              "baseline": baseline, "candidate": candidate,
              "identical_initial_behavior": True, "restore_replay_identical": True,
              "source_hashes": sources,
              "interpretation": "Implementation/compatibility evidence only; no GNN performance gain measured."}
    atomic_json(output / "verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
