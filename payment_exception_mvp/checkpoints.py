from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckpointRecorder:
    checkpoints: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, status: str = "passed", details: str | None = None) -> None:
        checkpoint: dict[str, Any] = {"name": name, "status": status}
        if details:
            checkpoint["details"] = details
        self.checkpoints.append(checkpoint)

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.checkpoints)
