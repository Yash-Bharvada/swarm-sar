"""Verify that the checked-in policy contract matches executable constants."""

import json
from pathlib import Path

from swarm_sar.policy_contract import policy_contract


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "artifacts" / "policy_contract_gpu_v1.json"


def main() -> None:
    expected = json.loads(PATH.read_text(encoding="utf-8"))
    actual = policy_contract()
    if expected != actual:
        raise SystemExit(
            "FAIL: policy contract drifted; intentionally version and export a new contract"
        )
    print(f"PASS: {actual['observation_version']} contract {actual['sha256']}")


if __name__ == "__main__":
    main()
