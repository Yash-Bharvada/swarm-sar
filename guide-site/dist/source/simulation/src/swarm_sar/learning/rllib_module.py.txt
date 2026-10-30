"""PPO module that guarantees invalid frontier actions are never sampled."""

from typing import Any, Optional, Union

import gymnasium as gym

from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.core.columns import Columns
from ray.rllib.core.rl_module.default_model_config import DefaultModelConfig
from ray.rllib.core.rl_module.apis.value_function_api import ValueFunctionAPI
from ray.rllib.utils.annotations import override
from ray.rllib.utils.torch_utils import FLOAT_MIN

import torch


class SwarmActionMaskingTorchRLModule(DefaultPPOTorchRLModule):
    """Official PPO torch module with the environment action mask applied."""

    def __init__(
        self,
        *,
        observation_space: Optional[gym.Space] = None,
        action_space: Optional[gym.Space] = None,
        inference_only: Optional[bool] = None,
        learner_only: bool = False,
        model_config: Optional[Union[dict, DefaultModelConfig]] = None,
        catalog_class=None,
        **kwargs,
    ) -> None:
        if not isinstance(observation_space, gym.spaces.Dict):
            raise ValueError("Action-masked PPO requires a Dict observation space")
        if set(observation_space.spaces) != {"action_mask", "observations"}:
            raise ValueError("Expected action_mask and observations fields")
        self.observation_space_with_mask = observation_space
        super().__init__(
            observation_space=observation_space["observations"],
            action_space=action_space,
            inference_only=inference_only,
            learner_only=learner_only,
            model_config=model_config,
            catalog_class=catalog_class,
            **kwargs,
        )

    @override(DefaultPPOTorchRLModule)
    def setup(self) -> None:
        super().setup()
        self.observation_space = self.observation_space_with_mask

    def _extract(self, batch: dict[str, Any]):
        observations = batch[Columns.OBS]
        if "action_mask" not in observations or "observations" not in observations:
            raise ValueError("Policy batch is missing the action mask or local observation")
        mask = observations["action_mask"]
        updated = dict(batch)
        updated[Columns.OBS] = observations["observations"]
        return mask, updated

    @staticmethod
    def _apply_mask(outputs: dict[str, Any], mask):
        inf_mask = torch.clamp(torch.log(mask), min=FLOAT_MIN)
        outputs[Columns.ACTION_DIST_INPUTS] = (
            outputs[Columns.ACTION_DIST_INPUTS] + inf_mask
        )
        return outputs

    @override(DefaultPPOTorchRLModule)
    def _forward_inference(self, batch, **kwargs):
        mask, batch = self._extract(batch)
        return self._apply_mask(super()._forward_inference(batch, **kwargs), mask)

    @override(DefaultPPOTorchRLModule)
    def _forward_exploration(self, batch, **kwargs):
        mask, batch = self._extract(batch)
        return self._apply_mask(super()._forward_exploration(batch, **kwargs), mask)

    @override(DefaultPPOTorchRLModule)
    def _forward_train(self, batch, **kwargs):
        if "action_mask" in batch:
            mask = batch["action_mask"]
            inner_batch = batch
        else:
            mask, inner_batch = self._extract(batch)
        return self._apply_mask(super()._forward_train(inner_batch, **kwargs), mask)

    @override(ValueFunctionAPI)
    def compute_values(self, batch, embeddings=None):
        if isinstance(batch.get(Columns.OBS), dict):
            mask, batch = self._extract(batch)
            batch["action_mask"] = mask
        return super().compute_values(batch, embeddings)
