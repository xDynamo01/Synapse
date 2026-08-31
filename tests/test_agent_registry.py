from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factories.agents import seed_invalid_agent, seed_test_agent
from synapse.agents.registry import AgentRegistry
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound, ValidationError


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=Path(__file__).resolve().parents[1],
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    return directory, settings, create_runtime(settings)


class AgentRegistryTests(unittest.TestCase):
    def test_empty_directory_returns_no_agents(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "data"
        (root / "agents").mkdir(parents=True)
        registry = AgentRegistry(DataDir(root))

        self.assertEqual(registry.list_agents(), [])

    def test_factory_creates_valid_minimal_agent(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_test_agent(settings.data_dir, "worker", role="worker")

        agent = runtime.agents.get("worker")

        self.assertEqual(agent.id, "worker")
        self.assertEqual(agent.name, "Worker")
        self.assertEqual(agent.role, "worker")
        self.assertFalse(agent.can_delegate)
        self.assertEqual(agent.autonomy, "manual")

    def test_missing_id_is_inferred_from_folder(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_invalid_agent(settings.data_dir, "worker", {"name": "Worker", "role": "worker"})

        self.assertEqual(runtime.agents.get("worker").id, "worker")

    def test_folder_and_config_id_mismatch_is_rejected(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_invalid_agent(
            settings.data_dir,
            "worker",
            {"id": "other", "name": "Worker", "role": "worker"},
        )

        with self.assertRaisesRegex(ValidationError, "id mismatch"):
            runtime.agents.get("worker")

    def test_partial_config_is_available_without_identity_validation(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_invalid_agent(settings.data_dir, "worker", {"id": "worker", "name": "Worker"})

        agent = runtime.agents.get("worker")

        self.assertEqual(agent.id, "worker")
        self.assertEqual(agent.role, "")

    def test_non_boolean_can_delegate_is_rejected(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_invalid_agent(
            settings.data_dir,
            "worker",
            {"id": "worker", "name": "Worker", "role": "worker", "can_delegate": "false"},
        )

        with self.assertRaisesRegex(ValidationError, "can_delegate must be boolean"):
            runtime.agents.get("worker")

    def test_invalid_yaml_returns_structured_error(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        path = settings.data_dir / "agents" / "worker" / "CONFIG.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("role: [unterminated", encoding="utf-8")

        with self.assertRaisesRegex(ValidationError, "Invalid agent config"):
            runtime.agents.get("worker")

    def test_missing_config_returns_not_found(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaises(NotFound):
            runtime.agents.get("missing")

    def test_list_is_sorted_and_ignores_extra_files(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        seed_test_agent(settings.data_dir, "zeta", role="worker")
        seed_test_agent(settings.data_dir, "alpha", role="worker")
        (settings.data_dir / "agents" / "README.md").write_text("extra", encoding="utf-8")

        self.assertEqual(
            [agent.id for agent in runtime.agents.list_agents()],
            ["alpha", "orchestrator", "zeta"],
        )


if __name__ == "__main__":
    unittest.main()
