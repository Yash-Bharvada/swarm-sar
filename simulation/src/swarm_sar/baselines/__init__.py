"""Non-learning benchmark controllers."""

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline
from swarm_sar.baselines.decentralized import DecentralizedFrontierController

__all__ = ["CoordinatedFrontierBaseline", "DecentralizedFrontierController"]
