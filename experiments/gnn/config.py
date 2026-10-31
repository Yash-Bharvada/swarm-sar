"""Construct opt-in PPO specs without changing frozen baseline source/configs."""
from copy import deepcopy

from swarm_sar.learning.training import build_ppo_config, training_config
from experiments.gnn.module import GraphResidualPPOModule


def experiment_config(*, smoke=False, gpu=False):
    config = deepcopy(training_config("training/configs/training_gpu_a5000.yaml"))
    config.update(num_env_runners=0 if smoke else 16,
                  num_cpus=2 if smoke else 28,
                  num_gpus_per_learner=1 if gpu else 0,
                  graph_width=64,
                  evaluation_interval_steps=25000,
                  checkpoint_interval_steps=25000)
    if smoke:
        config.update(train_batch_size_per_learner=128, minibatch_size=64,
                      num_epochs=1, rollout_fragment_length=32,
                      world_sizes=[24], max_steps=40, domain_randomization=False,
                      final_team_profiles=[{"rover": 2, "drone": 2}])
    return config


def build_gnn_ppo_config(config):
    result = build_ppo_config(config)
    module_spec = result.rl_module_spec
    for spec in module_spec.rl_module_specs.values():
        spec.module_class = GraphResidualPPOModule
        spec.model_config = {**spec.model_config, "graph_width": config.get("graph_width", 64)}
    return result.rl_module(rl_module_spec=module_spec)
