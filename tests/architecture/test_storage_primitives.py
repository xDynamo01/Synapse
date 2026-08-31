from __future__ import annotations

import ast

from .support import SOURCE_ROOT, imports_for

STORAGE_ROOT = SOURCE_ROOT / "storage"
PILOTS = (
    SOURCE_ROOT / "memory" / "storage.py",
    SOURCE_ROOT / "workers" / "registry.py",
    SOURCE_ROOT / "missions" / "attempts.py",
    SOURCE_ROOT / "notifications" / "local_provider.py",
)


def test_storage_package_is_domain_and_delivery_neutral() -> None:
    allowed = {"synapse.storage"}
    violations = []
    for path in STORAGE_ROOT.rglob("*.py"):
        for module in imports_for(path):
            if module.startswith("synapse.") and not any(
                module == prefix or module.startswith(prefix + ".") for prefix in allowed
            ):
                violations.append((path.name, module))
    assert not violations


def test_pilots_use_common_atomicity_and_locking_only() -> None:
    forbidden = ("os.replace", ".write_text(", ".write_bytes(", "threading.Lock", "threading.RLock")
    for path in PILOTS:
        source = path.read_text(encoding="utf-8")
        assert "synapse.storage" in source
        assert not any(item in source for item in forbidden), path


def test_storage_does_not_import_data_dir_or_resolve_domain_paths() -> None:
    for path in STORAGE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "synapse.core.data_dir" not in source
        assert ".resolve(" not in source or path.name in {"collection.py", "locking.py"}
        assert not any(
            token in source
            for token in ("agents/", "missions/", "notifications/", "memory/")
        )


def test_migrations_are_explicit_and_collection_ids_unique() -> None:
    collection_ids: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "collection_id" and isinstance(keyword.value, ast.Constant):
                    collection_ids.append(str(keyword.value.value))
    assert sorted(collection_ids) == sorted(set(collection_ids))
    migration_source = (STORAGE_ROOT / "migrations.py").read_text(encoding="utf-8")
    assert "def register(" in migration_source
    assert "sequential steps" in migration_source


def test_human_editable_stores_are_not_migrated() -> None:
    migrated = "\n".join(path.read_text(encoding="utf-8") for path in PILOTS)
    assert not any(name in migrated for name in ("SOUL.md", "SKILLS.md", "INBOX.md", "SUMMARY.md"))
