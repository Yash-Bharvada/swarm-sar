"""One-hop star-graph attention over the existing delivered-peer contract.

There is no global graph lookup or new transport. Node zero is the receiving
agent; nodes 1..8 are TTL-valid advertisements emitted by the environment.
The full hybrid actor retains the original ordered peer-input branch.
"""
from __future__ import annotations

import math

import torch
from torch import nn

from swarm_sar.policy_contract import (
    ENCODED_OBSERVATION_SIZE,
    MAX_PEER_SLOTS,
    PEER_FEATURE_WIDTH,
)

ARCHITECTURE = "gnn-residual-v1"
PEER_VALUES = MAX_PEER_SLOTS * PEER_FEATURE_WIDTH
LOCAL_VALUES = ENCODED_OBSERVATION_SIZE - PEER_VALUES


class ReceivedPeerAttention(nn.Module):
    """Local graph-message aggregation plus a zero-initialized PPO residual.

    Supports [features], [batch, features] and [batch, time, features].
    Attention weights are diagnostic association weights, not causal scores.
    """

    def __init__(self, width: int = 64):
        super().__init__()
        if type(width) is not int or width < 1:
            raise ValueError("Graph width must be a positive integer")
        self.width = width
        self.local_encoder = nn.Sequential(nn.Linear(LOCAL_VALUES, width), nn.Tanh())
        self.peer_encoder = nn.Sequential(nn.Linear(PEER_FEATURE_WIDTH, width), nn.Tanh())
        self.query = nn.Linear(width, width, bias=False)
        self.key = nn.Linear(width, width, bias=False)
        self.value = nn.Linear(width, width, bias=False)
        self.residual = nn.Linear(width, ENCODED_OBSERVATION_SIZE)
        nn.init.zeros_(self.residual.weight)
        nn.init.zeros_(self.residual.bias)

    def aggregate(self, observation: torch.Tensor):
        if observation.ndim < 1 or observation.shape[-1] != ENCODED_OBSERVATION_SIZE:
            raise ValueError("GNN requires the 229-value gpu-v1 observation")
        local = observation[..., :LOCAL_VALUES]
        peers = observation[..., LOCAL_VALUES:].reshape(
            *observation.shape[:-1], MAX_PEER_SLOTS, PEER_FEATURE_WIDTH
        )
        flags = peers[..., 0]
        if not torch.isfinite(flags).all() or not ((flags == 0) | (flags == 1)).all():
            raise ValueError("Peer validity flags must be finite zero or one")
        valid = flags > 0.5
        # Sanitize before the linear layers: even NaN in padding must not enter
        # attention, values, or gradient accumulation.
        peers = torch.where(valid.unsqueeze(-1), peers, torch.zeros_like(peers))
        if not torch.isfinite(local).all() or not torch.isfinite(peers).all():
            raise ValueError("Non-finite local or valid peer features")
        own = self.local_encoder(local)
        nodes = torch.cat((own.unsqueeze(-2), self.peer_encoder(peers)), dim=-2)
        allowed = torch.cat((torch.ones_like(valid[..., :1]), valid), dim=-1)
        query = self.query(own).unsqueeze(-2)
        scores = (query * self.key(nodes)).sum(dim=-1) / math.sqrt(self.width)
        scores = scores.masked_fill(~allowed, float("-inf"))
        weights = torch.softmax(scores, dim=-1)
        message = (weights.unsqueeze(-1) * self.value(nodes)).sum(dim=-2)
        return message, weights

    def forward(self, observation: torch.Tensor):
        message, weights = self.aggregate(observation)
        return observation + self.residual(message), weights
