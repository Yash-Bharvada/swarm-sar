import gymnasium as gym
import numpy as np
import pytest
import torch
from ray.rllib.core.columns import Columns

from swarm_sar.learning.inference import policy_step, policy_step_with_diagnostics


class CorruptedPolicy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.anchor = torch.nn.Parameter(torch.zeros(1))
        self.observation_space = gym.spaces.Box(-1, 1, (229,), dtype=np.float32)

    def is_stateful(self):
        return False

    def forward_inference(self, batch):
        return {Columns.ACTION_DIST_INPUTS: torch.full((1, 7), float("nan"))}


@pytest.mark.parametrize("step", [policy_step, policy_step_with_diagnostics])
def test_inference_refuses_nan_logits_instead_of_silently_picking_frontier_zero(step):
    observation = {"observations": np.zeros(229, dtype=np.float32), "action_mask": np.ones(7, dtype=np.float32)}
    with pytest.raises(FloatingPointError, match="non-finite action logits"):
        step(CorruptedPolicy(), observation, rng=None)
