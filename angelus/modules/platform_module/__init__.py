"""Operating-system desktop capability adapters."""

from .system_resource_manager import (
    SystemResourceManager,
    SystemResourceManagerError,
    SystemResourceManagerUnavailable,
)

__all__ = [
    "SystemResourceManager",
    "SystemResourceManagerError",
    "SystemResourceManagerUnavailable",
]

