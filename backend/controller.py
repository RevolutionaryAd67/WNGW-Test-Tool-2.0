"""Controller for launching IEC-104 client and server worker processes."""
from __future__ import annotations

import atexit
import multiprocessing as mp
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .events import EventBus
from .history import CommunicationHistory
from .processes import run_client_process, run_server_process


@dataclass
class _ManagedProcess:
    process: mp.Process
    queue: mp.Queue
    listener: threading.Thread


class BackendController:
    """Coordinates backend client/server worker processes and event streaming."""

    def __init__(self) -> None:
        self.event_bus = EventBus()
        self._client: Optional[_ManagedProcess] = None
        self._server: Optional[_ManagedProcess] = None
        self.history = CommunicationHistory(Path("data/telegrams"))
        atexit.register(self.shutdown)

    def _start_process(self, target, label: str) -> bool:
        existing = getattr(self, label)
        if existing and existing.process.is_alive():
            return False
        queue: mp.Queue = mp.Queue()
        process = mp.Process(target=target, args=(queue,), daemon=True)
        process.start()
        listener = threading.Thread(
            target=self._drain_queue, args=(queue,), daemon=True
        )
        listener.start()
        setattr(self, label, _ManagedProcess(process, queue, listener))
        return True

    def start_client(self) -> bool:
        """Start the IEC-104 client worker if not already running."""
        return self._start_process(run_client_process, "_client")

    def start_server(self) -> bool:
        """Start the IEC-104 server worker if not already running."""
        return self._start_process(run_server_process, "_server")

    # properties for compatibility
    @property
    def client_process(self) -> Optional[_ManagedProcess]:
        return self._client

    @property
    def server_process(self) -> Optional[_ManagedProcess]:
        return self._server

    def _drain_queue(self, queue: mp.Queue) -> None:
        while True:
            try:
                data = queue.get()
            except (EOFError, OSError):
                break
            if data is None:
                break
            if isinstance(data, dict):
                self.history.record(data)
                self.event_bus.publish(data)

    def shutdown(self) -> None:
        for label in ("_client", "_server"):
            managed = getattr(self, label)
            if not managed:
                continue
            try:
                managed.queue.put_nowait(None)
            except Exception:
                pass
            if managed.process.is_alive():
                managed.process.terminate()
            setattr(self, label, None)
