"""Exercise graph actor/critic backward passes on the explicitly requested device.

No Ray cluster, paid provisioning, source changes or checkpoint updates.
"""
import argparse
import json
import time

import torch
from ray.rllib.core.columns import Columns

from experiments.gnn.attention import ARCHITECTURE
from experiments.gnn.artifacts import source_hashes
from experiments.gnn.smoke import DEFAULT, verified_originals, hybrid
from swarm_sar.learning.behavior_cloning import initial_state_for_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true", help="Require CUDA; fail instead of silently using CPU")
    args = parser.parse_args()
    if args.gpu and not torch.cuda.is_available():
        parser.error("CUDA unavailable. Run --gpu on the NVIDIA training host.")
    device = torch.device("cuda:0" if args.gpu else "cpu")
    torch.set_num_threads(1)
    torch.manual_seed(42)
    originals, digest = verified_originals(DEFAULT)
    rows = {}
    for name, original in originals.items():
        actor = hybrid(original).to(device).train()
        if any(p.device.type != device.type for p in actor.parameters()):
            raise RuntimeError("An actor parameter is on the wrong device")
        optimizer = torch.optim.Adam(actor.parameters(), lr=1e-4)
        obs = torch.zeros(2, 4, 229, device=device)
        peers = obs[..., -88:].reshape(2, 4, 8, 11)
        peers[..., :2, 0] = 1
        peers[..., 0, 9] = 0.7
        peers[..., 1, 3] = 0.4
        batch = {Columns.OBS: {"observations": obs, "action_mask": torch.ones(2, 4, 7, device=device)},
                 Columns.STATE_IN: initial_state_for_batch(actor, 2, device)}
        encoder_before = actor.graph_adapter.peer_encoder[0].weight.detach().clone()
        if args.gpu:
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        started = time.monotonic()
        for _ in range(3):
            optimizer.zero_grad()
            result = actor.forward_train(batch)
            logits = result[Columns.ACTION_DIST_INPUTS]
            loss = -torch.log_softmax(logits, -1)[..., 5].mean() + actor.compute_values(batch).square().mean()
            loss.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in actor.parameters()):
                raise RuntimeError("Non-finite actor/critic/graph gradient")
            optimizer.step()
        if args.gpu:
            torch.cuda.synchronize()
        if torch.equal(encoder_before, actor.graph_adapter.peer_encoder[0].weight):
            raise RuntimeError("Graph encoder did not optimize")
        rows[name] = {"device": str(device), "graph_encoder_updated": True,
                      "three_updates_seconds": time.monotonic() - started,
                      "peak_allocated_bytes": torch.cuda.max_memory_allocated() if args.gpu else None}
    print(json.dumps({"architecture": ARCHITECTURE, "base_sha256": digest,
                      "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
                      "gpu_name": torch.cuda.get_device_name() if args.gpu else None,
                      "policies": rows, "source_sha256": source_hashes(),
                      "interpretation": "Device/backward preflight only; not rollout throughput or trained policy quality."}, indent=2))


if __name__ == "__main__":
    main()
