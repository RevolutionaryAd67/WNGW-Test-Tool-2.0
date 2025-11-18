"""Backend package for IEC-104 communication services."""

from .controller import BackendController

backend_controller = BackendController()

__all__ = ["backend_controller", "BackendController"]
