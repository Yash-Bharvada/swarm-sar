"""Optional graph-residual RLlib actor, retaining PPO/LSTM/action-mask semantics."""
from __future__ import annotations

from ray.rllib.core.columns import Columns

from swarm_sar.learning.rllib_module import SwarmActionMaskingTorchRLModule
from experiments.gnn.attention import ReceivedPeerAttention


class GraphResidualPPOModule(SwarmActionMaskingTorchRLModule):
    def setup(self):
        super().setup()
        self.graph_adapter = ReceivedPeerAttention(int(self.model_config.get("graph_width", 64)))

    def _extract(self, batch):
        mask, inner = super()._extract(batch)
        encoded, _ = self.graph_adapter(inner[Columns.OBS])
        inner[Columns.OBS] = encoded
        return mask, inner

    def attention_for(self, observation):
        """Weights for the supplied exact observation; never inferred from link distance."""
        return self.graph_adapter(observation)[1]


def warm_start_actor(target: GraphResidualPPOModule, source):
    """Copy an exactly compatible original actor, leaving the new branch at zero.

    Copies weights only, not PPO optimizer state or lifetime training counters.
    Use matching recurrent/model configuration and inference_only flags.
    """
    state = source.state_dict()
    target_state = target.state_dict()
    expected = {k: v for k, v in target_state.items() if not k.startswith("graph_adapter.")}
    if set(expected) != set(state):
        raise ValueError("Original actor keys differ from target; match model configuration")
    for name, tensor in state.items():
        if tensor.shape != expected[name].shape:
            raise ValueError(f"Original actor tensor shape differs: {name}")
    # Validate before mutating target and reject non-finite source weights.
    import torch
    if any(not torch.isfinite(tensor).all() for tensor in state.values()):
        raise ValueError("Original actor has non-finite weights")
    target.load_state_dict(state, strict=False)
    torch.nn.init.zeros_(target.graph_adapter.residual.weight)
    torch.nn.init.zeros_(target.graph_adapter.residual.bias)
    return {"copied_tensors": len(state), "graph_residual_initially_zero": True}
