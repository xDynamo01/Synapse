"""PyInstaller hook for the `webrtcvad-wheels` distribution.

The upstream contrib hook copies metadata for a distribution named `webrtcvad`, while
Synapse intentionally installs `webrtcvad-wheels`, which provides the same extension
module. The extension itself is discovered by Analysis; no distribution metadata is
required at runtime.
"""

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []
