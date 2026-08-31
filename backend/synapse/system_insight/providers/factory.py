from __future__ import annotations

import platform

from synapse.system_insight.providers.base import PlatformInsightProvider
from synapse.system_insight.providers.common import PsutilInsightProvider
from synapse.system_insight.providers.linux import LinuxInsightProvider
from synapse.system_insight.providers.macos import MacOSInsightProvider
from synapse.system_insight.providers.windows import WindowsInsightProvider

_PROVIDERS: dict[str, type[PlatformInsightProvider]] = {
    "Windows": WindowsInsightProvider,
    "Linux": LinuxInsightProvider,
    "Darwin": MacOSInsightProvider,
}


def platform_provider(system_name: str | None = None) -> PlatformInsightProvider:
    provider_type = _PROVIDERS.get(system_name or platform.system(), PsutilInsightProvider)
    return provider_type()
