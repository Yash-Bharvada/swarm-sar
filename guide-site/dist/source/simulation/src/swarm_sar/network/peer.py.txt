"""Range-, wall-, loss-, delay-, and partition-aware message transport."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from swarm_sar.network.messages import PeerMessage
from swarm_sar.sensing.vision import bresenham_line
from swarm_sar.world.cells import WALL


@dataclass
class ScheduledDelivery:
    deliver_step: int
    recipient: str
    message: PeerMessage


class PeerNetwork:
    """A transport only: it routes messages but never selects robot actions."""

    def __init__(self, config: dict[str, Any], seed: int) -> None:
        self.config = dict(config)
        self.rng = np.random.default_rng(int(seed) ^ 0x4E455457)
        self.enabled = bool(self.config.get("network_enabled", False))
        self.packet_loss = float(self.config.get("network_packet_loss", 0.0))
        if not 0.0 <= self.packet_loss <= 1.0:
            raise ValueError("network_packet_loss must be between 0 and 1")
        delay = self.config.get("network_delay_steps", [1, 2])
        self.delay_min, self.delay_max = map(int, delay)
        if self.delay_min < 0 or self.delay_max < self.delay_min:
            raise ValueError("Invalid network_delay_steps")
        self.ttl = int(self.config.get("network_message_ttl", 8))
        self.bandwidth = int(self.config.get("network_bandwidth_bytes", 8192))
        self.wall_attenuation = float(
            self.config.get("network_wall_attenuation", 0.70)
        )
        self.require_los = bool(self.config.get("network_require_los", False))
        self.partition_windows = list(
            self.config.get("network_partition_windows", []) or []
        )
        self.outboxes: dict[str, list[PeerMessage]] = defaultdict(list)
        self.inboxes: dict[str, list[PeerMessage]] = defaultdict(list)
        self.seen: dict[str, set[str]] = defaultdict(set)
        self.scheduled: list[ScheduledDelivery] = []
        self.next_seq: dict[str, int] = defaultdict(int)
        self.latest_by_sender: dict[str, dict[str, PeerMessage]] = defaultdict(dict)
        self.link_state: dict[tuple[str, str], bool] = {}
        self.metrics = self._empty_metrics()

    @staticmethod
    def _empty_metrics() -> dict[str, int]:
        return {
            "messages_created": 0,
            "transmission_attempts": 0,
            "messages_delivered": 0,
            "dropped_loss": 0,
            "dropped_range": 0,
            "dropped_wall": 0,
            "dropped_partition": 0,
            "dropped_bandwidth": 0,
            "dropped_stale": 0,
            "duplicates_suppressed": 0,
            "bytes_created": 0,
            "bytes_delivered": 0,
            "reconnections": 0,
        }

    def register(self, agents: list[str]) -> None:
        for agent in agents:
            self.outboxes[agent]
            self.inboxes[agent]
            self.seen[agent]
            self.latest_by_sender[agent]

    def broadcast(
        self,
        sender_id: str,
        *,
        frame_id: str,
        step: int,
        kind: str,
        pose: tuple[float, float],
        pose_uncertainty: float,
        payload: dict[str, Any],
    ) -> PeerMessage | None:
        if not self.enabled:
            return None
        sequence = self.next_seq[sender_id]
        self.next_seq[sender_id] += 1
        message = PeerMessage(
            sender_id=sender_id,
            seq=sequence,
            frame_id=frame_id,
            sent_step=int(step),
            expires_step=int(step) + self.ttl,
            kind=kind,
            pose=(float(pose[0]), float(pose[1])),
            pose_uncertainty=float(pose_uncertainty),
            payload=payload,
        )
        self.outboxes[sender_id].append(message)
        self.metrics["messages_created"] += 1
        self.metrics["bytes_created"] += message.estimated_bytes
        return message

    def _partitioned(self, sender: str, recipient: str, step: int) -> bool:
        for window in self.partition_windows:
            if int(window["start"]) <= step <= int(window["end"]):
                isolated = set(window.get("agents", []))
                if (sender in isolated) != (recipient in isolated):
                    return True
        return False

    def _radio_link(
        self,
        sender,
        recipient,
        robot_configs: dict[str, dict[str, Any]],
        grid: np.ndarray,
    ) -> tuple[bool, str]:
        radius = min(
            float(robot_configs[sender.type]["comm_radius"]),
            float(robot_configs[recipient.type]["comm_radius"]),
        )
        distance = float(
            np.hypot(sender.x - recipient.x, sender.y - recipient.y)
        )
        if distance > radius:
            return False, "range"
        line = bresenham_line(sender.position, recipient.position)[1:-1]
        wall_count = sum(grid[y, x] == WALL for x, y in line)
        if self.require_los and wall_count:
            return False, "wall"
        effective_radius = radius * (self.wall_attenuation**wall_count)
        if distance > effective_radius:
            return False, "wall"
        return True, "ok"

    def _deliver(self, recipient: str, message: PeerMessage, step: int) -> None:
        if step > message.expires_step:
            self.metrics["dropped_stale"] += 1
            return
        if message.message_id in self.seen[recipient]:
            self.metrics["duplicates_suppressed"] += 1
            return
        self.seen[recipient].add(message.message_id)
        self.inboxes[recipient].append(message)
        current = self.latest_by_sender[recipient].get(message.sender_id)
        if current is None or (message.sent_step, message.seq) > (
            current.sent_step,
            current.seq,
        ):
            self.latest_by_sender[recipient][message.sender_id] = message
        self.metrics["messages_delivered"] += 1
        self.metrics["bytes_delivered"] += message.estimated_bytes

    def advance(
        self,
        step: int,
        robots: list[Any],
        robot_configs: dict[str, dict[str, Any]],
        grid: np.ndarray,
    ) -> None:
        if not self.enabled:
            return
        due = [item for item in self.scheduled if item.deliver_step <= step]
        self.scheduled = [item for item in self.scheduled if item.deliver_step > step]
        for item in sorted(
            due,
            key=lambda value: (
                value.deliver_step,
                value.recipient,
                value.message.sender_id,
                value.message.seq,
            ),
        ):
            self._deliver(item.recipient, item.message, step)

        by_name = {robot.name: robot for robot in robots if robot.alive}
        for sender_name in sorted(self.outboxes):
            messages = self.outboxes[sender_name]
            self.outboxes[sender_name] = []
            sender = by_name.get(sender_name)
            if sender is None:
                continue
            remaining = self.bandwidth
            for message in messages:
                if message.estimated_bytes > remaining:
                    self.metrics["dropped_bandwidth"] += 1
                    continue
                remaining -= message.estimated_bytes
                for recipient_name in sorted(by_name):
                    if recipient_name == sender_name:
                        continue
                    recipient = by_name[recipient_name]
                    self.metrics["transmission_attempts"] += 1
                    pair = tuple(sorted((sender_name, recipient_name)))
                    if self._partitioned(sender_name, recipient_name, step):
                        self.metrics["dropped_partition"] += 1
                        self.link_state[pair] = False
                        continue
                    linked, reason = self._radio_link(
                        sender, recipient, robot_configs, grid
                    )
                    if not linked:
                        self.metrics[f"dropped_{reason}"] += 1
                        self.link_state[pair] = False
                        continue
                    if self.link_state.get(pair) is False:
                        self.metrics["reconnections"] += 1
                    self.link_state[pair] = True
                    if self.rng.random() < self.packet_loss:
                        self.metrics["dropped_loss"] += 1
                        continue
                    delay = int(self.rng.integers(self.delay_min, self.delay_max + 1))
                    delivery = ScheduledDelivery(step + delay, recipient_name, message)
                    if delay == 0:
                        self._deliver(recipient_name, message, step)
                    else:
                        self.scheduled.append(delivery)

    def drain(self, recipient: str) -> list[PeerMessage]:
        messages = list(self.inboxes[recipient])
        self.inboxes[recipient].clear()
        return messages

    def peer_messages(
        self, recipient: str, step: int, *, max_age: int | None = None
    ) -> list[PeerMessage]:
        age = int(max_age if max_age is not None else self.ttl)
        return [
            message
            for message in self.latest_by_sender[recipient].values()
            if step - message.sent_step <= age and step <= message.expires_step
        ]

    def inject_delivery(
        self, recipient: str, message: PeerMessage, *, deliver_step: int
    ) -> None:
        """Test/debug hook that still passes through expiry and de-duplication."""
        self.scheduled.append(ScheduledDelivery(deliver_step, recipient, message))

    def snapshot(self) -> dict[str, Any]:
        attempts = self.metrics["transmission_attempts"]
        return {
            **self.metrics,
            "scheduled": len(self.scheduled),
            "delivery_rate": (
                self.metrics["messages_delivered"] / attempts if attempts else 0.0
            ),
        }
