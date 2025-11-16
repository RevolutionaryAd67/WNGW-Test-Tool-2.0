"""Navigation configuration for the WNGW Test Tool UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class NavItem:
    endpoint: str
    label: str
    description: str = ""


def build_top_navigation() -> List[NavItem]:
    """Return the list of top-level navigation items."""
    return [
        NavItem(endpoint="startseite", label="Startseite", description="Zur Übersicht"),
        NavItem(endpoint="beobachten", label="Beobachten", description="Systeme beobachten"),
        NavItem(endpoint="pruefung", label="Prüfung", description="Tests ausführen"),
        NavItem(endpoint="hilfe", label="Hilfe", description="Dokumentation"),
        NavItem(endpoint="einstellungen", label="Einstellungen", description="Konfiguration"),
    ]


def build_sub_navigation() -> Dict[str, List[NavItem]]:
    """Return mapping of top-level labels to their sub-navigation entries."""
    return {
        "Beobachten": [
            NavItem(endpoint="beobachten_client_master", label="Client/Master", description="Client-Übersicht"),
            NavItem(endpoint="beobachten_server_slave", label="Server/Slave", description="Server-Übersicht"),
            NavItem(endpoint="beobachten_filter", label="Filter", description="Filter konfigurieren"),
            NavItem(endpoint="beobachten_optionen", label="Optionen", description="Optionen anpassen"),
        ]
    }
