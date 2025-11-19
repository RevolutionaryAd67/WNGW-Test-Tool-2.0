#   Definiert den EventBus, also die Verteilstation für Nachrichten (Events)
#
#   Aufgaben des Skripts:
#       1. Stellt Möglichkeiten bereit, sodass sich Empfänger (Konsumenten) in einer Liste "anmelden" können
#       2. Wenn irgendwo ein neues Ereignis (z.B.) ein neues Telegramm registriertr wird, wird es an alle angemeldeten Empfänger versendet

from __future__ import annotations

import queue
import threading
from typing import Dict, List, Optional


# Funktionen, die als Verteilstation für Events dienen
class EventBus:

    # Enthält alle Konsumenten, die Events beziehen wollen
    def __init__(self) -> None:
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    # Registriert einen neuen Konsumenten und gibt dessen Queue zurück
    def subscribe(self) -> queue.Queue:
        consumer: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(consumer)
        return consumer

    # Entfernt den angegebenen Konsumenten wieder aus der Liste
    def unsubscribe(self, consumer: queue.Queue) -> None:
        with self._lock:
            if consumer in self._subscribers:
                self._subscribers.remove(consumer)

    # Sendet ein Event an alle aktuell registrierten Konsumenten
    def publish(self, event: Dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for consumer in subscribers:
            try:
                consumer.put_nowait(event)
            except queue.Full:
                pass
