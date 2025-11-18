from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from backend.iec104.connection_profiles import (
    ClientConnectionProfile,
    ServerConnectionProfile,
)
from backend.utils.json_io import load_json
from backend.utils.paths import CLIENT_SETTINGS_DIR, SERVER_SETTINGS_DIR

BoxValues = Dict[str, Dict[str, object]]


@dataclass
class _BoxContext:
    directory: Path
    component: str

    def path(self) -> Path:
        return self.directory / f"{self.component}.json"


class FrontendSettingsService:
    """Loads persisted UI settings and converts them into connection profiles."""

    def __init__(
        self,
        client_dir: Path | None = None,
        server_dir: Path | None = None,
    ) -> None:
        self.client_dir = client_dir or CLIENT_SETTINGS_DIR
        self.server_dir = server_dir or SERVER_SETTINGS_DIR

    def _load_box(self, context: _BoxContext) -> BoxValues:
        data = load_json(context.path())
        if isinstance(data, dict):
            return data  # type: ignore[return-value]
        return {}

    @staticmethod
    def _read_value(box: BoxValues, row_id: str, column: str = "value") -> str:
        row = box.get(row_id) or {}
        raw = row.get(column)
        if raw is None:
            return ""
        return str(raw).strip()

    @classmethod
    def _read_int(
        cls, box: BoxValues, row_id: str, column: str = "value"
    ) -> Optional[int]:
        value = cls._read_value(box, row_id, column)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def load_client_profile(self) -> ClientConnectionProfile:
        partner_box = self._load_box(_BoxContext(self.client_dir, "kommunikationspartner"))
        tcp_box = self._load_box(_BoxContext(self.client_dir, "tcp_konnektivitaet"))
        asdu_box = self._load_box(_BoxContext(self.client_dir, "asdu_parameter"))
        return ClientConnectionProfile(
            partner_ip=self._read_value(partner_box, "ip_address_wngw_client"),
            partner_station_address=self._read_value(
                partner_box, "asdu_address_wngw_client"
            ),
            listen_ip=self._read_value(tcp_box, "tcp_ip_address_client"),
            listen_port=self._read_int(tcp_box, "tcp_port_client"),
            originator_address=self._read_value(
                asdu_box, "asdu_origin_address_client"
            ),
        )

    def load_server_profile(self) -> ServerConnectionProfile:
        partner_box = self._load_box(_BoxContext(self.server_dir, "kommunikationspartner"))
        tcp_box = self._load_box(_BoxContext(self.server_dir, "tcp_konnektivitaet"))
        asdu_box = self._load_box(_BoxContext(self.server_dir, "asdu_parameter"))
        return ServerConnectionProfile(
            partner_ip=self._read_value(partner_box, "ip_address_wngw_server"),
            partner_station_address=self._read_value(
                partner_box, "asdu_address_wngw_server"
            ),
            listen_ip=self._read_value(tcp_box, "tcp_ip_address_server"),
            listen_port=self._read_int(tcp_box, "tcp_port_server"),
            station_address=self._read_value(asdu_box, "asdu_common_address_server"),
            originator_address=self._read_value(
                asdu_box, "asdu_originator_address_server"
            ),
        )
