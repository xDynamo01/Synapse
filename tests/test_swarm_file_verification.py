from synapse.missions.verification import ResultVerifier


def test_directory_read_explains_correct_tool_instead_of_permission_denial(tmp_path):
    import pytest

    from synapse.core.data_dir import DataDir
    from synapse.core.exceptions import ValidationError
    from synapse.core.permissions import PermissionContext
    from synapse.tools.builtin import ReadFileTool

    with pytest.raises(ValidationError, match="Use list_directory"):
        ReadFileTool(DataDir(tmp_path)).run(PermissionContext("tester"), path=".")


def receipt(name, path, **output):
    return {"kind": "tool_result", "value": {"success": True, "status": "executed",
            "request": {"name": name}, "result": {"path": str(path), **output}}}


def test_repair_requires_in_root_mutation_and_subsequent_readback(tmp_path):
    root = tmp_path / "project"
    path = root / "app.py"
    policy = {"checks": ["file_operations"], "root": str(root),
              "tool_groups": [["read_file"], ["edit_file"]], "require_readback": True}
    def verify(evidence):
        return ResultVerifier().verify({"output": "Fixed!", "evidence": evidence}, policy).status
    assert verify([]) == "failed"
    assert verify([receipt("read_file", path)]) == "failed"
    assert verify([receipt("read_file", path), receipt("edit_file", path)]) == "failed"
    assert verify([receipt("edit_file", path), receipt("read_file", tmp_path / "other.py")]) == "failed"
    assert verify([receipt("edit_file", path), receipt("read_file", path)]) == "passed"
    pending = receipt("edit_file", path)
    pending["value"]["status"] = "awaiting_approval"
    assert verify([pending, receipt("read_file", path)]) == "failed"


def test_deletion_requires_later_listing_showing_absence(tmp_path):
    path = tmp_path / "obsolete.py"
    policy = {"checks": ["file_operations"], "root": str(tmp_path),
              "tool_groups": [["delete_file"]], "require_readback": True}
    deleted = receipt("delete_file", path)
    for entries, expected in [([{"name": "obsolete.py"}], "failed"), ([], "passed")]:
        evidence = [deleted, receipt("list_directory", tmp_path, entries=entries)]
        assert ResultVerifier().verify({"evidence": evidence}, policy).status == expected
