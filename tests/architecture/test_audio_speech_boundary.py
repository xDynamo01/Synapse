from __future__ import annotations

import ast
from pathlib import Path

from .support import SOURCE_ROOT, cyclic_components

AUDIO_ROOT = SOURCE_ROOT / "audio"
VOICE_ROOT = SOURCE_ROOT / "voice"
SPEECH_ADAPTERS_ROOT = SOURCE_ROOT / "speech_adapters"
BOOTSTRAP_INTERACTION = SOURCE_ROOT / "bootstrap" / "features" / "interaction.py"
REMOVED_PRESENTATION_ROOTS = tuple(
    SOURCE_ROOT / name for name in ("avatar", "embodiment", "wardrobe")
)


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.modules: list[str] = []

    @staticmethod
    def _is_type_checking(test: ast.expr) -> bool:
        return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )

    def visit_If(self, node: ast.If) -> None:
        if self._is_type_checking(node.test):
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.modules.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.modules.append(node.module)


def _runtime_imports(path: Path) -> list[str]:
    visitor = _RuntimeImportVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor.modules


def _runtime_context_graph() -> set[tuple[str, str]]:
    compatibility = {
        Path("core/__init__.py"),
        Path("core/app.py"),
        Path("core/model_router.py"),
    }
    graph: set[tuple[str, str]] = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT)
        if relative in compatibility:
            continue
        if len(relative.parts) == 1:
            if relative.name == "main.py":
                source = "api"
            else:
                continue
        else:
            source = relative.parts[0]
        if source == "bootstrap":
            continue
        for module in _runtime_imports(path):
            if not module.startswith("synapse."):
                continue
            target = module.split(".", 2)[1]
            if target in {source, "bootstrap"}:
                continue
            graph.add((source, target))
    return graph


def test_audio_depends_only_on_its_consumer_owned_speech_port() -> None:
    imports = {module for path in AUDIO_ROOT.rglob("*.py") for module in _runtime_imports(path)}
    assert not any(module.startswith("synapse.speech_adapters") for module in imports)

    runtime_source = (AUDIO_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "SpeechExecutionPort | None" in runtime_source
    assert "SpeechAdapterRuntime" not in runtime_source


def test_voice_has_no_avatar_or_embodiment_dependency() -> None:
    imports = {module for path in VOICE_ROOT.rglob("*.py") for module in _runtime_imports(path)}
    assert not any(
        module.startswith(("synapse.avatar", "synapse.embodiment")) for module in imports
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in VOICE_ROOT.rglob("*.py"))
    assert "avatar_session_id" not in source.replace('raw.pop("avatar_session_id", None)', "")
    assert "embodiment_id" not in source.replace('raw.pop("embodiment_id", None)', "")


def test_speech_execution_is_consumer_owned_without_process_or_sandbox_authority() -> None:
    imports = {
        module for path in SPEECH_ADAPTERS_ROOT.rglob("*.py") for module in _runtime_imports(path)
    }
    assert not any(module.startswith("synapse.sandbox") for module in imports)
    assert not imports.intersection({"subprocess", "multiprocessing"})
    source = (SPEECH_ADAPTERS_ROOT / "piper_tts.py").read_text(encoding="utf-8")
    assert "os.system" not in source
    assert "Popen" not in source
    assert "shell=True" not in source


def test_realtime_voice_is_not_activated_by_production_bootstrap() -> None:
    construction_sites = []
    for path in SOURCE_ROOT.rglob("*.py"):
        if path == VOICE_ROOT / "realtime.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RealtimeVoiceRuntime"
            for node in ast.walk(tree)
        ):
            construction_sites.append(path.relative_to(SOURCE_ROOT))
    assert construction_sites == [Path("voice_composition/runtime.py")]
    bootstrap_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SOURCE_ROOT / "bootstrap").rglob("*.py")
    )
    assert "voice_composition" not in bootstrap_source


def test_bootstrap_is_the_only_production_audio_speech_binding() -> None:
    construction_sites: list[Path] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "AudioRuntime"
            for node in ast.walk(tree)
        ):
            construction_sites.append(path.relative_to(SOURCE_ROOT))
    assert construction_sites == [Path("bootstrap/features/interaction.py")]

    source = BOOTSTRAP_INTERACTION.read_text(encoding="utf-8")
    assert "dependencies.speech_adapters" in source
    assert "SpeechAdapterRuntime" in source


def test_avatar_embodiment_and_wardrobe_are_physically_absent() -> None:
    assert not any(root.exists() for root in REMOVED_PRESENTATION_ROOTS)
    forbidden_imports = ("synapse.avatar", "synapse.embodiment", "synapse.wardrobe")
    assert not [
        (path.relative_to(SOURCE_ROOT), module)
        for path in SOURCE_ROOT.rglob("*.py")
        for module in _runtime_imports(path)
        if module.startswith(forbidden_imports)
    ]

    active_surfaces = (
        SOURCE_ROOT / "api",
        SOURCE_ROOT / "bootstrap",
        SOURCE_ROOT / "capabilities",
        SOURCE_ROOT / "commands",
        SOURCE_ROOT / "health",
        SOURCE_ROOT / "providers",
        SOURCE_ROOT / "readiness",
    )
    forbidden_terms = (
        "avatar",
        "embodiment",
        "wardrobe",
        "vrm",
        "live2d",
    )
    assert not [
        (path.relative_to(SOURCE_ROOT), term)
        for root in active_surfaces
        for path in root.rglob("*.py")
        for term in forbidden_terms
        if term in path.read_text(encoding="utf-8").lower()
    ]


def test_audio_speech_scc_is_removed_without_changing_other_sccs() -> None:
    graph = _runtime_context_graph()
    assert len(graph) == 306  # Primary MoM: api -> mom -> core.
    assert ("audio", "speech_adapters") not in graph
    assert cyclic_components(graph) == [
        (
            frozenset(
                {
                    "agents",
                    "approvals",
                    "context",
                    "conversations",
                    "decisions",
                    "delegation",
                    "missions",
                    "models",
                    "policies",
                    "tools",
                    "voice",
                }
            ),
                31,
        ),
    ]
