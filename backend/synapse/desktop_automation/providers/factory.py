from __future__ import annotations

import platform

from synapse.desktop_automation.errors import ProviderUnavailable
from synapse.desktop_automation.providers.linux import LinuxATSPIProvider
from synapse.desktop_automation.providers.macos import MacOSAccessibilityProvider
from synapse.desktop_automation.providers.windows import WindowsUIAutomationProvider


def platform_desktop_provider(system_name: str | None = None):
    mapping = {
        "Windows": WindowsUIAutomationProvider,
        "Linux": LinuxATSPIProvider,
        "Darwin": MacOSAccessibilityProvider,
    }
    selected = system_name or platform.system()
    provider_type = mapping.get(selected)
    if provider_type is None:
        raise ProviderUnavailable(f"No desktop automation provider for platform: {selected}")
    return provider_type()
