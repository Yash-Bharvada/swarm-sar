# PPO 754k development candidate

Selected checkpoint: **753664 environment steps**, not the later 1015808-step
checkpoint that triggered worst-cohort quality gates. Source identity is in
`source_commit.txt`; the archive contains the checkpoint, source status, BC
reference, pilot/continuation definitions, training history, configurations and
policy/source manifests. `training_definition.json` records the effective
**16 rollout runners**, overriding the source YAML's incompatible 20.

`ppo_754k_review.json` records development-only evaluation: **89.29% fixed**,
**88.22% shadow**, **88.80% combined** mean cohort recall; expert fixed/combined
are 87.43%/87.13%. This is selected development evidence, not sealed final-test
performance or statistical proof of superiority. Large-maze recall is 5/18
with 19.15% coverage; tunnel recall is 15/21. See the project report for limits.

Verify the archive from this directory:

```bash
shasum -a 256 -c swarm-754k-handoff.sha256
```

Extract from the repository root into a fresh local directory:

```bash
mkdir -p training/runs/ppo_754k_handoff
tar -xzf models/ppo_754k/swarm-754k-handoff.tar.gz -C training/runs/ppo_754k_handoff
```

The checkpoint is then under
`training/runs/ppo_754k_handoff/results/gpu_continue_1m/checkpoints/step_000000753664`.
Original server paths in metadata are provenance, not local paths to reuse.
The checkpoint tree hash matches the report's provenance:
`23696e6cf3b0821b6c01235a3911cb5cb87d0707589efce6ec43cb58b5340040`.
A local review verified the archive checksum, safe archive paths, checkpoint
file-tree digest, source identity and equality of the archived/loose reports.
CUDA training and the full evaluation were not rerun on the Mac during review.

This artifact does not automatically connect the model to the browser or ROS.
The original audited training tag/source manifest remains unchanged.

The optional [PPO frontend service](../../docs/guides/ppo_frontend_integration.md)
now loads this verified artifact and presents actual Python missions in the 3D
browser. It is explicitly selected and does not connect the checkpoint to ROS.
