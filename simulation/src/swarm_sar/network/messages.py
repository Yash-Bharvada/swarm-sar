"""Wire-safe message envelopes used by the Step 4 peer network."""

from dataclasses import asdict, dataclass
from functools import cached_property
import json
from typing import Any


@dataclass(frozen=True)
class PeerMessage:
    sender_id: str
    seq: int
    frame_id: str
    sent_step: int
    expires_step: int
    kind: str
    pose: tuple[float, float]
    pose_uncertainty: float
    payload: dict[str, Any]

    @property
    def message_id(self) -> str:
        return f"{self.sender_id}:{self.seq}"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["message_id"] = self.message_id
        return result

    @cached_property
    def estimated_bytes(self) -> int:
        return len(
            json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
