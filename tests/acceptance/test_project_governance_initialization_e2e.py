from .project_governance_support import initialize, runtime


def test_project_governance_initialization_survives_restart(tmp_path):
    first = runtime(tmp_path)
    project, _ = initialize(first)
    assert (tmp_path / "projects" / "synapse" / ".synapse" / "project.yaml").exists()
    restarted = runtime(tmp_path)
    assert restarted.projects.get("synapse").checksum == project.checksum
    assert restarted.read_project_context("synapse").project_revision == 1
