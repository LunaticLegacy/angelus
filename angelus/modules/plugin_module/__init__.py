"""Plugin package discovery, durable configuration, and controlled loading."""

from .manager import PluginManager
from .models import (
    PluginManifest,
    PluginPermission,
    PluginRecord,
    PluginRuntime,
    PluginSettingField,
    PluginSettingValue,
    PluginTheme,
    PluginToolCategory,
    PluginToolContribution,
    PluginToolDefinition,
)

__all__ = [
    "PluginManager", "PluginManifest", "PluginPermission", "PluginRecord",
    "PluginRuntime", "PluginSettingField", "PluginSettingValue", "PluginTheme",
    "PluginToolCategory", "PluginToolContribution", "PluginToolDefinition",
]
