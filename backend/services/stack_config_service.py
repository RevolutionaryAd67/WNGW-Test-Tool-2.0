"""Utilities to apply persisted settings to the IEC-104 stacks."""
from __future__ import annotations

from backend.iec104.client_stack import client_stack
from backend.iec104.server_stack import server_stack
from backend.services.logging_service import logging_service
from backend.services.settings_service import settings_service

_logger = logging_service.get_logger(__name__)


def apply_stack_settings() -> None:
    """Read the persisted configuration and push it to the stacks."""
    client_profile = settings_service.get_client_profile()
    server_profile = settings_service.get_server_profile()

    client_stack.configure_network(**client_profile)
    server_stack.configure_network(**server_profile)
    _logger.info(
        "Applied stack settings: client -> %s, server -> %s",
        client_profile,
        server_profile,
    )
