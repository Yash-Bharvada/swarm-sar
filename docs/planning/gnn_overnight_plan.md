# One-night GNN implementation plan

Status: initial implementation and CPU validation complete; CUDA/full-budget validation pending. A smoke-trained checkpoint exists, but regressed in shortened diagnostic evaluation and is not promoted. See the [GPU runbook](../../experiments/gnn/README.md) and [validation report](../audits/gnn_implementation_validation.md). This plan is relative to the start of an approximately 12-hour night. It is a bounded experiment, not a promise to complete the previously estimated multi-day validation in 12 hours.

## Target and rationale

The problem statement suggests GNNs for communication and requires decentralized cooperative MARL. We will add a real differentiable graph-attention branch to the Python PPO actors. Each receiver processes a local star graph: itself plus peers represented by actually delivered, unexpired messages. One hop aggregates incoming knowledge; it does not create extra radio deliveries or expose global teammate state.

The first experiment reuses the existing 229-value observations, eight peer slots, seven actions, per-type rover/drone policies, recurrent memory, A*, sensors and transport. This limits overnight integration risk. It is a receiver-side GNN, not a learned radio scheduler, a spatial SLAM graph network or a centralized coordinator.

Potential benefits to measure: better weighting of peer survivor evidence and goal claims, less duplicate exploration, and useful behavior under changing peer availability. A permutation-invariant graph branch helps process a set of peer reports, but the original PPO branch still contains ordered peer slots; the full hybrid policy is not permutation invariant. It retains the eight-peer bound. No communication-speedup, arbitrary-fleet scaling or large-map improvement follows merely from adding a GNN.

## Architecture and checkpoint strategy

```text
229-value local observation
    ├── original PPO input ────────────────────────────┐
    └── local features + 8 delivered peer feature rows │
             ↓                                        │
       one-hop masked graph attention                 │
             ↓                                        │
       zero-initialized residual projection ──────────+
                                                      ↓
                                              existing LSTM/PPO
                                                      ↓
                                            masked seven-action output
```

Use a self edge so no-peer operation remains finite. Invalid/padded peer slots receive exactly zero attention and cannot influence graph output. New graph output starts at zero, allowing verified original actor weights to initialize a hybrid candidate with the same initial logits. This preserves a useful starting behavior; the graph branch is initially inactive, and needs gradient updates before its new information can affect choices.

The observation wire contract remains gpu-v1, but the architecture identity is new (`gnn-residual-v1`). It needs its own checkpoint/manifest. The current backend/frontend intentionally accept only the selected 754k identity. Do not relabel the old checkpoint as GNN, bypass hash checks, or present an untrained graph as an improved model.

Experimental code/configuration lives under `experiments/gnn/`, outside the frozen training-source inventory. The experiment must record its own source/config identity in outputs. Existing trained weights and audited sources remain unchanged.

## One-night sequence and gates

| Time from start | Work | Required evidence |
|---|---|---|
| 0–1 h | Confirm graph inputs, contract, warm-start design and scope | Written graph/masking semantics and a fixed baseline |
| 1–3 h | Implement graph adapter, PPO module and opt-in config builder | Zero influence from padding, no-peer finite output, real gradients, mask preservation |
| 3–4 h | Restore baseline actors into hybrid modules; checkpoint round trip | Equal initial logits and identical recurrent rollout at zero residual; graph parameters survive restore |
| 4–5 h | Small CPU/GPU optimizer and rollout smoke | Both actor types update; numerical health; actual steps/sec and GPU memory measurements |
| 5–8 h | Bounded GPU PPO pilot, optionally BC using existing data | Frequent verified checkpoints and baseline-relative development diagnostics |
| 8–10 h | Evaluate frozen candidate against original PPO/expert on paired development cases | Same seeds, budgets, fleet and initial worlds; report failures and no-peer/loss cases |
| 10–11 h | If candidate qualifies, add versioned backend serving and attention telemetry | Actual active actor identity, step/session checks and telemetry from inference |
| 11–12 h | Frontend integration and rehearsal, or retain offline GNN experiment | Real candidate demonstration/recording; original PPO remains usable |

If a gate fails, stop the dependent work. By hour 5, a training run must save/restore and measure throughput. By hour 10, stop training regardless of whether the candidate is better. A diagnostic subset is preliminary, not a replacement for the full cohort/multi-seed evaluation.

Possible split: A owns graph/module/tests; B owns warm start and training; C owns versioned service/telemetry; D owns paired evaluation and frontend. Work begins sequentially at shared interfaces; this is a proposed ownership split, not historical attribution.

## GPU budget

Start with a 30–60-minute verified pilot, then allocate at most 3 hours of continuation within this night. Budget additional time for evaluation and packaging. One compatible NVIDIA GPU is the intended training resource. Measure actual memory/throughput before increasing batch size or runner count. CPU simulation/A* can dominate; a bigger GPU does not remove that bottleneck. This budget is smaller than the previous 8–20 GPU-hour first-candidate estimate because the overnight goal is a warm-started preliminary experiment.

No long training, paid GPU provisioning, final-test evaluation or ROS deployment is started by writing the implementation. Local CPU tests/smokes establish implementation correctness only.

## Frontend changes compared with today

| Current simulator | Planned qualified GNN candidate |
|---|---|
| Heuristic or selected PPO | Separate explicitly identified GNN-PPO candidate through a versioned artifact manifest |
| Radio topology and packet arcs | Same actual transport display; additional selected-receiver attention edges |
| Private map, evidence and peer messages | Same data plus a per-peer normalized attention view from the decision just executed |
| One active verified PPO identity | Architecture/checkpoint identity, inference step, candidate status and rollback to original PPO |
| Mission metrics | A comparison report for original PPO versus GNN using matched conditions |

Weights should be labelled **attention weights**, not percentages of causal decision contribution. Self attention should be shown separately, and peer weights tied to sender IDs from that exact observation. They may reflect a recent TTL-valid message even when the current physical link is down. A stale/absent decision must show no live attention. Frontend must never generate random weights or infer learned attention from radio distance.

Map geometry, robot models, batteries, sensors, movement, seven actions and ROS visualization do not need to change. GNN runs in Python; Three.js does not run the neural network. The existing heuristic mode does not become GNN-enabled. Keeping the same scene also makes behavioral differences easier to assess.

Backend work must preserve host/origin checks, session isolation, expected-step idempotency and artifact verification. It should support the new candidate with an explicit versioned manifest, not change the 754k hash or weaken validation. Full learned ROS/SLAM integration is outside this night's scope.

## Acceptance and promotion

- Test no-peer and masked padding, peer permutation in the graph branch, gradients after residual activation, action masks, recurrent state and exact save/restore.
- Inspect actual optimizing learner parameters, not just an inference replica. Reject non-finite outputs or invalid actions.
- Run original PPO and candidate on identical development cases, including the known demonstration, difficult maps, disabled communication, loss and partition/reconnection.
- Report found/total, mission completion, coverage, steps, energy, invalid actions/post-shield collisions, inference latency and actual bytes sent. Receiver-side attention alone does not reduce bytes.
- Compare against a zero-residual/disabled-graph ablation as well as original PPO. Keep original candidate-selection gates; do not weaken them to finish the night.
- Preserve final seeds. A small overnight subset supports an experimental claim only. If results regress or are incomplete, retain the original policy and show GNN as implementation work with measured preliminary results.

## Initial implementation deliverable

The first patch targets the optional graph encoder, PPO integration/config builder, verified weight-transfer helper, CPU smoke entry point and meaningful tests. Training/serving/frontend promotion are later gates; their status must be reported separately after local checks.
