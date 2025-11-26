#   Liest die Client- und Server-Einstellungen aus den jeweiligen JSON-Dateien
#
#   Aufgaben des Skripts:
#       1. Liest die Einstellungen für den Client aus seiner JSON-Datei
#       2. Liest die Einstellungen für den Server aus seiner JSON-Datei

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


# Verzeichnis, indem die JSON-Dateien liegen
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


# Informationen, die in den JSON-Dateien für die Einstellungen des Clients enthalten sind
@dataclass
class ClientSettings:
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    remote_asdu: int
    originator_address: int


# Informationen, die in den JSON-Dateien für die Einstellungen des Servers enthalten sind
@dataclass
class ServerSettings:
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    remote_asdu: int
    common_address: int
    originator_address: int


# Liest den Wert eines Schlüssels aus einer JSON-Datei 
def _read_value(file_path: Path, key: str, fallback: str = "0") -> str:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except json.JSONDecodeError:
        return fallback
    entry = payload.get(key, {})
    value = entry.get("value")
    return str(value) if value is not None else fallback


# Lädt sämtliche Client-Einstellungen aus den JSON-Dateien
def load_client_settings() -> ClientSettings:
    client_dir = DATA_DIR / "einstellungen_client"
    local_ip = _read_value(client_dir / "tcp_konnektivitaet.json", "tcp_ip_address_client", "0.0.0.0")
    local_port = int(_read_value(client_dir / "tcp_konnektivitaet.json", "tcp_port_client", "2404"))
    remote_ip = _read_value(client_dir / "kommunikationspartner.json", "ip_address_wngw_client", "127.0.0.1")
    remote_asdu = int(_read_value(client_dir / "kommunikationspartner.json", "asdu_address_wngw_client", "0"))
    originator = int(_read_value(client_dir / "asdu_parameter.json", "asdu_origin_address_client", "0"))
    return ClientSettings(
        local_ip=local_ip,
        local_port=local_port,
        remote_ip=remote_ip,
        remote_port=2404,
        remote_asdu=remote_asdu,
        originator_address=originator,
    )


# Lädt sämtliche Server-Einstellungen aus den JSON-Dateien
def load_server_settings() -> ServerSettings:
    server_dir = DATA_DIR / "einstellungen_server"
    local_ip = _read_value(server_dir / "tcp_konnektivitaet.json", "tcp_ip_address_server", "0.0.0.0")
    local_port = int(_read_value(server_dir / "tcp_konnektivitaet.json", "tcp_port_server", "2404"))
    remote_ip = _read_value(server_dir / "kommunikationspartner.json", "ip_address_wngw_server", "127.0.0.1")
    remote_asdu = int(_read_value(server_dir / "kommunikationspartner.json", "asdu_address_wngw_server", "0"))
    common_address = remote_asdu
    originator = int(_read_value(server_dir / "asdu_parameter.json", "asdu_originator_address_server", "0"))
    return ServerSettings(
        local_ip=local_ip,
        local_port=local_port,
        remote_ip=remote_ip,
        remote_port=2404,
        remote_asdu=remote_asdu,
        common_address=common_address,
        originator_address=originator,
    )
