from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from synapse.core.config import Settings
from synapse.main import create_app


def _settings(root: Path) -> Settings:
    return Settings(root, root, "127.0.0.1", 8717, "local_owner")


def _write_package(root: Path) -> None:
    package = root / "skills" / "candidates" / "e2e-review"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("# E2E Review\n\nReview changes safely.\n", encoding="utf-8")
    (package / "manifest.yaml").write_text(
        """skill_id: e2e-review
name: E2E Review
version: 1.0.0
description: Review changes using deterministic evidence
summary: Safe review workflow
authorship: [synapse]
status: active
scopes: [system, agent, project]
supported_agent_kinds: [primary, persistent]
activation: {keywords: [e2e, evidence]}
requirements: {}
dependencies: []
conflicts: []
tools: []
capabilities: []
providers: []
resources: []
references: []
scripts: []
context_policy: {max_tokens: 1000}
permissions: []
compatibility: {agent_skills: partial}
metadata: {tags: [review]}
""",
        encoding="utf-8",
    )


def test_local_package_install_list_and_restart(tmp_path: Path) -> None:
    _write_package(tmp_path)
    with TestClient(create_app(_settings(tmp_path))) as client:
        headers = {"X-Actor-Type": "admin", "X-Actor-ID": "local_owner"}
        assert (
            client.post(
                "/api/skills/inspect",
                json={"package_ref": "skills/candidates/e2e-review"},
                headers=headers,
            ).status_code
            == 200
        )
        assert client.post(
            "/api/skills/validate",
            json={"package_ref": "skills/candidates/e2e-review"},
            headers=headers,
        ).json()["valid"]
        installed = client.post(
            "/api/skills/install",
            json={"package_ref": "skills/candidates/e2e-review"},
            headers=headers,
        )
        assert installed.status_code == 200
        assert client.get("/api/skills").json()["total"] == 1
    with TestClient(create_app(_settings(tmp_path))) as client:
        listed = client.get("/api/skills").json()
        assert listed["skills"][0]["skill_id"] == "e2e-review"
