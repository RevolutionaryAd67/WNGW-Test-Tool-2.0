from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClientConnectionProfile:
    partner_ip: str = ""
    partner_station_address: str = ""
    partner_port: Optional[int] = None
    listen_ip: str = ""
    listen_port: Optional[int] = None
    originator_address: str = ""


@dataclass
class ServerConnectionProfile:
    partner_ip: str = ""
    partner_station_address: str = ""
    partner_port: Optional[int] = None
    listen_ip: str = ""
    listen_port: Optional[int] = None
    station_address: str = ""
    originator_address: str = ""
