from synapse.system_insight.providers.base import PlatformInsightProvider
from synapse.system_insight.providers.factory import platform_provider
from synapse.system_insight.providers.linux import LinuxInsightProvider
from synapse.system_insight.providers.macos import MacOSInsightProvider
from synapse.system_insight.providers.windows import WindowsInsightProvider

__all__ = [
    "LinuxInsightProvider",
    "MacOSInsightProvider",
    "PlatformInsightProvider",
    "WindowsInsightProvider",
    "platform_provider",
]
