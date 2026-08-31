from __future__ import annotations

import hashlib
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase2_values import (
    SkillContentFingerprint,
    SkillManifestFingerprint,
)
from synapse.skills.phase4_errors import (
    DuplicateSkillManifestKey,
    InvalidRawSkillManifest,
    InvalidSkillVerificationPolicy,
    MissingSkillManifestField,
    SkillAssetChecksumMismatch,
    SkillAssetMissing,
    SkillContentFingerprintMismatch,
    SkillPackagePathEscape,
    SkillVerificationResourceLimitExceeded,
    UndeclaredSkillAsset,
    UnknownSkillManifestField,
    UnsafeSkillManifestTag,
    UnsafeSkillPackageLink,
    UnsupportedSkillManifestFeature,
)
from synapse.skills.phase4_models import (
    SkillAssetChecksum,
    SkillVerificationPolicy,
)
from synapse.skills.phase4_parser import parse_published_skill_manifest
from synapse.skills.phase4_verification import (
    SkillPackageVerifier,
    _add_unique_portable_path,
    _is_reparse,
    _validate_portable_path,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(assets: dict[str, bytes], *, extra: str = "") -> bytes:
    entries = []
    for path, data in assets.items():
        kind = "instructions" if path == "SKILL.md" else "resource"
        media = "text/markdown" if path.endswith(".md") else "application/octet-stream"
        entries.append(
            f"""  - logical_path: {path}
    fingerprint: {_sha(data)}
    kind: {kind}
    media_type: {media}
    size_bytes: {len(data)}"""
        )
    return f"""format_version: 1
skill_id: sample-skill
version: 1.0.0
display_name: Sample skill
summary: Strict sample.
description: A strict manifest used by package verification tests.
provenance:
  publisher_ref: publisher:synapse
scopes:
  - project
content:
{os.linesep.join(entries)}
{extra}""".encode()


def _package(root: Path, assets: dict[str, bytes]) -> None:
    for name, data in assets.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "manifest.yaml").write_bytes(_manifest(assets))


def test_parser_builds_approved_manifest_without_coercion() -> None:
    manifest = parse_published_skill_manifest(_manifest({"SKILL.md": b"# Skill"}))
    assert manifest.skill_id.value == "sample-skill"
    assert manifest.fingerprint() == manifest.fingerprint()


@pytest.mark.parametrize(
    "raw",
    (
        b"format_version: 1\nformat_version: 1\n",
        b"provenance:\n  publisher_ref: publisher:a\n  publisher_ref: publisher:b\n",
        b"content:\n  - logical_path: a\n    logical_path: b\n",
    ),
)
def test_duplicate_keys_are_rejected_at_every_level(raw: bytes) -> None:
    with pytest.raises(DuplicateSkillManifestKey):
        parse_published_skill_manifest(raw)


def test_case_variants_are_distinct_then_unknown() -> None:
    raw = _manifest({"SKILL.md": b"x"}, extra="Skill_id: sample-skill\n")
    with pytest.raises(UnknownSkillManifestField):
        parse_published_skill_manifest(raw)


@pytest.mark.parametrize(
    ("fragment", "error"),
    (
        ("value: &a text\nother: *a\n", UnsupportedSkillManifestFeature),
        ("value: !!python/object:builtins.object {}\n", UnsafeSkillManifestTag),
        ("base: &a {x: y}\nvalue:\n  <<: *a\n", UnsupportedSkillManifestFeature),
    ),
)
def test_yaml_extensions_are_forbidden(fragment: str, error: type[ValueError]) -> None:
    with pytest.raises(error):
        parse_published_skill_manifest(fragment.encode())


@pytest.mark.parametrize(
    "fragment",
    (
        "a: &one value\n",
        "a: &one {b: &two value}\n",
        "a: &one [*one]\n",
        "a: &a lol\nb: &b [*a,*a]\nc: [*b,*b]\n",
        "base: &base {x: one}\nitem: {<<: *base, x: two}\n",
        "a: &a {x: one}\nb: &b {x: two}\nitem: {<<: [*a,*b]}\n",
    ),
)
def test_anchors_aliases_and_merges_fail_during_token_preflight(
    fragment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse.skills.phase4_parser as parser

    monkeypatch.setattr(
        parser.yaml,
        "compose_all",
        lambda *_args, **_kwargs: pytest.fail("composition must not run"),
    )
    with pytest.raises(UnsupportedSkillManifestFeature):
        parse_published_skill_manifest(fragment.encode())


def test_invalid_utf8_non_string_keys_and_missing_fields_fail() -> None:
    with pytest.raises(InvalidRawSkillManifest):
        parse_published_skill_manifest(b"\xff")
    with pytest.raises(InvalidRawSkillManifest):
        parse_published_skill_manifest(b"1: value")
    with pytest.raises(MissingSkillManifestField):
        parse_published_skill_manifest(b"format_version: 1")


def test_parser_limits_scalar_and_nesting() -> None:
    policy = replace(SkillVerificationPolicy(), max_scalar_chars=4, max_yaml_depth=2)
    with pytest.raises(SkillVerificationResourceLimitExceeded):
        parse_published_skill_manifest(b"value: abcde", policy=policy)
    with pytest.raises(SkillVerificationResourceLimitExceeded):
        parse_published_skill_manifest(b"a:\n  b:\n    c:\n      d: value", policy=policy)


@pytest.mark.parametrize(
    "value",
    ("1.5", "2026-07-26", "0x10", "0o10", "1e3", "yes", "no", "on", "off", ".inf", ".nan"),
)
def test_ambiguous_yaml_scalars_are_not_coerced(value: str) -> None:
    raw = _manifest({"SKILL.md": b"x"}).replace(b"format_version: 1", f"format_version: {value}".encode())
    with pytest.raises((InvalidRawSkillManifest, UnsupportedSkillManifestFeature)):
        parse_published_skill_manifest(raw)


@pytest.mark.parametrize("value", (0, -1, True, 1_048_577))
def test_policy_rejects_invalid_manifest_limits(value: object) -> None:
    with pytest.raises(InvalidSkillVerificationPolicy) as captured:
        replace(SkillVerificationPolicy(), max_manifest_bytes=value)  # type: ignore[arg-type]
    assert captured.value.args == ("skill verification policy is invalid",)


def test_token_limit_is_applied_before_yaml_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    import synapse.skills.phase4_parser as parser

    monkeypatch.setattr(
        parser.yaml,
        "compose_all",
        lambda *_args, **_kwargs: pytest.fail("composition must not run"),
    )
    with pytest.raises(SkillVerificationResourceLimitExceeded):
        parse_published_skill_manifest(
            b"a: b\nc: d\n",
            policy=replace(SkillVerificationPolicy(), max_yaml_tokens=3),
        )


def test_valid_package_is_deterministic_and_snapshot_has_no_local_path(tmp_path: Path) -> None:
    assets = {"resources/data.bin": b"\x00\xff", "SKILL.md": b"# Skill"}
    _package(tmp_path, assets)
    verifier = SkillPackageVerifier()
    first = verifier.verify(tmp_path)
    second = verifier.verify(tmp_path)
    assert first.technical_identity == second.technical_identity
    assert [item.logical_path.value for item in first.assets] == [
        "SKILL.md",
        "resources/data.bin",
    ]
    assert not hasattr(first, "path")
    assert not hasattr(first, "raw")
    with pytest.raises(FrozenInstanceError):
        first.assets = ()  # type: ignore[misc]


def test_empty_asset_is_hashed(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b""})
    snapshot = SkillPackageVerifier().verify(tmp_path)
    assert snapshot.assets[0].checksum.value == _sha(b"")


def test_missing_extra_and_checksum_mismatch_fail(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    (tmp_path / "SKILL.md").unlink()
    with pytest.raises(SkillAssetMissing):
        SkillPackageVerifier().verify(tmp_path)
    (tmp_path / "SKILL.md").write_bytes(b"x")
    (tmp_path / ".hidden").write_bytes(b"x")
    with pytest.raises(UndeclaredSkillAsset):
        SkillPackageVerifier().verify(tmp_path)
    (tmp_path / ".hidden").unlink()
    (tmp_path / "SKILL.md").write_bytes(b"changed")
    with pytest.raises(SkillAssetChecksumMismatch):
        SkillPackageVerifier().verify(tmp_path)


@pytest.mark.parametrize("name", ("CON.txt", "é.txt"))
def test_cross_platform_unsafe_filesystem_paths_fail(tmp_path: Path, name: str) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    (tmp_path / name).write_bytes(b"x")
    with pytest.raises(SkillPackagePathEscape):
        SkillPackageVerifier().verify(tmp_path)


@pytest.mark.parametrize(
    "path",
    (
        "/absolute",
        "C:/drive",
        "C:relative",
        r"\\server\share",
        r"\\?\C:\extended",
        r"\\.\device",
        "file.txt:stream",
        r"mixed/path\file",
        "CON.txt",
        "name.",
        "name ",
        "a//b",
        "a/./b",
        "a/../b",
        "homoglyph-\u0430.txt",
    ),
)
def test_portable_path_policy_is_independent_of_host(path: str) -> None:
    with pytest.raises((SkillPackagePathEscape, SkillVerificationResourceLimitExceeded)):
        _validate_portable_path(path, len(path.split("/")), SkillVerificationPolicy())


def test_portable_case_collision_is_independent_of_host() -> None:
    seen: set[str] = set()
    _add_unique_portable_path("Docs/Guide.md", seen)
    with pytest.raises(SkillPackagePathEscape):
        _add_unique_portable_path("docs/guide.md", seen)


def test_resource_limits_cover_files_size_total_and_depth(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b"xx", "nested/data.bin": b"x"})
    with pytest.raises(SkillVerificationResourceLimitExceeded):
        SkillPackageVerifier(replace(SkillVerificationPolicy(), max_file_bytes=1)).verify(
            tmp_path
        )
    with pytest.raises(SkillVerificationResourceLimitExceeded):
        SkillPackageVerifier(replace(SkillVerificationPolicy(), max_files=1)).verify(
            tmp_path
        )
    with pytest.raises(SkillVerificationResourceLimitExceeded):
        SkillPackageVerifier(replace(SkillVerificationPolicy(), max_depth=1)).verify(
            tmp_path
        )


def test_timestamp_and_root_do_not_change_identity(tmp_path: Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    assets = {"SKILL.md": b"x"}
    _package(one, assets)
    _package(two, assets)
    before = SkillPackageVerifier().verify(one)
    os.utime(one / "SKILL.md", None)
    after = SkillPackageVerifier().verify(one)
    copied = SkillPackageVerifier().verify(two)
    assert before.technical_identity == after.technical_identity == copied.technical_identity


def test_expected_content_fingerprint_is_checked(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    with pytest.raises(SkillContentFingerprintMismatch):
        SkillPackageVerifier().verify(
            tmp_path, expected_content_fingerprint=SkillContentFingerprint("0" * 64)
        )


def test_content_fingerprint_golden_vector(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    assert SkillPackageVerifier().verify(tmp_path).content_fingerprint.value == (
        "cadd1f0330417567b50c79b1ebeed77c921b2a9bf18c34da66ed58c7e5758ea1"
    )


@pytest.mark.parametrize(
    ("assets", "expected"),
    (
            (
                {"SKILL.md": b"# Skill", "resources/data.bin": b"\x00\xff"},
                "5fbc7bd02e4ffc84d3c8a4773829def415820ed41839f64e5e4372c19b05f9de",
            ),
            (
                {"SKILL.md": b"", "resources/empty.bin": b""},
                "e4f1570182d2a22999af05da67bcbbb1263fd82e52ef8bc58984cd96323d9f6b",
            ),
    ),
)
def test_additional_content_fingerprint_golden_vectors(
    tmp_path: Path, assets: dict[str, bytes], expected: str
) -> None:
    _package(tmp_path, assets)
    assert SkillPackageVerifier().verify(tmp_path).content_fingerprint.value == expected


def test_directory_mutation_is_detected_by_final_reinventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    verifier = SkillPackageVerifier()
    original = verifier._hash_file

    def mutate(fact: object) -> tuple[SkillAssetChecksum, int]:
        result = original(fact)  # type: ignore[arg-type]
        (tmp_path / "late.tmp").write_bytes(b"late")
        return result

    monkeypatch.setattr(verifier, "_hash_file", mutate)
    with pytest.raises(Exception) as captured:
        verifier.verify(tmp_path)
    assert captured.value.code == "skill_content_changed_during_verification"


def test_file_replacement_before_open_is_detected_without_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    verifier = SkillPackageVerifier()
    original = verifier._hash_file

    def replace_before_open(fact: object) -> tuple[SkillAssetChecksum, int]:
        (tmp_path / "SKILL.md").write_bytes(b"replacement")
        return original(fact)  # type: ignore[arg-type]

    monkeypatch.setattr(verifier, "_hash_file", replace_before_open)
    with pytest.raises(Exception) as captured:
        verifier.verify(tmp_path)
    assert captured.value.code == "skill_content_changed_during_verification"


def test_identity_composes_manifest_and_content_fingerprints(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    snapshot = SkillPackageVerifier().verify(tmp_path)
    identity = PublishedSkillVersionId.from_manifest(
        snapshot.manifest, snapshot.content_fingerprint
    )
    assert identity.manifest_fingerprint == snapshot.manifest_fingerprint
    assert identity.content_fingerprint == snapshot.content_fingerprint
    assert identity != replace(
        identity, manifest_fingerprint=SkillManifestFingerprint("0" * 64)
    )


def test_checksum_types_are_not_interchangeable() -> None:
    checksum = SkillAssetChecksum("0" * 64)
    assert checksum != SkillContentFingerprint("0" * 64)
    assert checksum != SkillManifestFingerprint("0" * 64)


def test_phase4_parser_is_not_exported_from_main_facade() -> None:
    import synapse.skills as skills

    assert not hasattr(skills, "parse_published_skill_manifest")


def test_symlink_is_rejected_when_supported(tmp_path: Path) -> None:
    _package(tmp_path, {"SKILL.md": b"x"})
    target = tmp_path / "target"
    target.write_bytes(b"x")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(UnsafeSkillPackageLink):
        SkillPackageVerifier().verify(tmp_path)


def test_reparse_classifier_has_platform_independent_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import synapse.skills.phase4_verification as verification

    monkeypatch.setattr(verification.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024, raising=False)
    assert _is_reparse(SimpleNamespace(st_file_attributes=1024))  # type: ignore[arg-type]
    assert not _is_reparse(SimpleNamespace(st_file_attributes=0))  # type: ignore[arg-type]
