"""Swarm search-and-rescue simulation."""

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline
from swarm_sar.baselines.decentralized import DecentralizedFrontierController
from swarm_sar.network import PeerNetwork
from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.sim.env import DisasterResponseParallelEnv

__all__ = [
    "CoordinatedFrontierBaseline",
    "DecentralizedFrontierController",
    "DisasterResponseParallelEnv",
    "PeerNetwork",
    "SwarmWorld",
]
__version__ = "0.6.0"
