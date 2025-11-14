"""Basic flow control helpers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FlowControl:
    k: int = 12
    w: int = 8
    sent_without_ack: int = 0

    def can_send(self) -> bool:
        return self.sent_without_ack < self.k

    def frame_sent(self) -> None:
        self.sent_without_ack += 1

    def acknowledge(self) -> None:
        self.sent_without_ack = max(0, self.sent_without_ack - 1)

    def reset(self) -> None:
        self.sent_without_ack = 0
