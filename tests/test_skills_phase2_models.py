from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

import synapse.skills as skills_api
from synapse.skills import (
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillId,
    SkillManifestFingerprint,
    SkillManifestFormatVersion,
    SkillVersion,
    SkillVersionConstraint,
)
from synapse.skills.models import SKILL_STATUSES, SkillManifest
from synapse.skills.phase2_errors import (
    ImmutableSkillIdentityMismatch,
    InvalidPublishedSkillManifest,
    InvalidSkillContentReference,
    InvalidSkillDependencyDeclaration,
    InvalidSkillFingerprint,
    InvalidSkillId,
    InvalidSkillSecurityDeclaration,
    InvalidSkillVersion,
    InvalidSkillVersionConstraint,
    SkillPhase2DomainError,
    UnsupportedSkillManifestFormat,
)
from synapse.skills.phase2_models import (
    CapabilityRequirement,
    DataClassificationCeiling,
    EgressRequirement,
    ExternalProcessingRequirement,
    ExternalRuntimeRequirement,
    FilesystemRequirement,
    NetworkRequirement,
    ProviderModelRequirement,
    SkillCompatibilityDeclaration,
    SkillConflictDeclaration,
    SkillContentKind,
    SkillContentRef,
    SkillDependencyDeclaration,
    SkillDependencyReason,
    SkillEvaluationRequirement,
    SkillExecutionDeclaration,
    SkillExecutionRuntime,
    SkillGovernanceRequirement,
    SkillLogicalPath,
    SkillPackageFingerprint,
    SkillProvenance,
    SkillPublicationScope,
    SkillRequirementId,
    SkillResourceRequirement,
    SkillSchemaVersionRequirement,
    SkillSecurityDeclaration,
    SkillSemanticReference,
    ToolRequirement,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _ref(
    path: str,
    kind: SkillContentKind,
    *,
    digest: str = SHA_A,
    media_type: str = "text/plain",
) -> SkillContentRef:
    return SkillContentRef(
        SkillLogicalPath(path),
        SkillContentFingerprint(digest),
        kind,
        media_type,
        10,
    )


def _manifest(*, reverse: bool = False) -> PublishedSkillManifest:
    instructions = _ref("SKILL.md", SkillContentKind.INSTRUCTIONS)
    entrypoint = _ref(
        "entrypoints/main.wasm",
        SkillContentKind.ENTRYPOINT,
        digest=SHA_B,
        media_type="application/wasm",
    )
    schema = _ref(
        "schemas/input.json",
        SkillContentKind.SCHEMA,
        digest=SHA_C,
        media_type="application/json",
    )
    content = (instructions, entrypoint, schema)
    tools = (
        ToolRequirement(SkillRequirementId("read_file")),
        ToolRequirement(SkillRequirementId("web_search")),
    )
    dependencies = (
        SkillDependencyDeclaration(
            SkillId("base-workflow"),
            SkillDependencyReason.REQUIRED_WORKFLOW,
            version=SkillVersion.parse("1.0.0"),
        ),
        SkillDependencyDeclaration(
            SkillId("extra-workflow"),
            SkillDependencyReason.OPTIONAL_ENHANCEMENT,
            constraint=SkillVersionConstraint("^2.0.0"),
            optional=True,
        ),
    )
    if reverse:
        content = tuple(reversed(content))
        tools = tuple(reversed(tools))
        dependencies = tuple(reversed(dependencies))
    return PublishedSkillManifest(
        format_version=SkillManifestFormatVersion(1),
        skill_id=SkillId("research-synthesis"),
        version=SkillVersion.parse("2.1.0-rc.1+build.7"),
        display_name="Research synthesis",
        summary="Evidence-oriented research workflow.",
        description="A deterministic workflow that references content without carrying payloads.",
        provenance=SkillProvenance(
            publisher_ref=SkillSemanticReference("publisher:synapse"),
            source_repository_ref=SkillSemanticReference("repository:synapse"),
            source_revision_ref=SkillSemanticReference("revision:abc123"),
            lineage_ref=SkillSemanticReference("lineage:research-v1"),
        ),
        scopes=(SkillPublicationScope.PROJECT, SkillPublicationScope.AGENT),
        content=content,
        dependencies=dependencies,
        conflicts=(
            SkillConflictDeclaration(
                SkillId("unsafe-workflow"),
                SkillVersionConstraint("^1.0.0"),
                SkillSemanticReference("reason:incompatible-output"),
            ),
        ),
        tools=tools,
        capabilities=(
            CapabilityRequirement(SkillRequirementId("code_review")),
        ),
        providers=(
            ProviderModelRequirement(
                SkillRequirementId("local-provider"),
                SkillRequirementId("analysis-model"),
            ),
        ),
        compatibility=SkillCompatibilityDeclaration(
            operating_profiles=(SkillRequirementId("local-first"),),
            platforms=(SkillRequirementId("windows"),),
            python_constraint=SkillVersionConstraint(">=3.12.0,<4.0.0"),
            external_runtimes=(
                ExternalRuntimeRequirement(
                    SkillRequirementId("wasm-runtime"),
                    SkillVersionConstraint("^1.0.0"),
                ),
            ),
            schemas=(SkillSchemaVersionRequirement("input:1"),),
        ),
        security=SkillSecurityDeclaration(
            classification_ceiling=DataClassificationCeiling.INTERNAL,
            network_requirement=NetworkRequirement.NONE,
            external_processing_requirement=ExternalProcessingRequirement.FORBIDDEN,
            filesystem_requirement=FilesystemRequirement.READ_ONLY,
            egress_requirement=EgressRequirement.NONE,
            sandbox_profile_requirement=SkillSemanticReference("sandbox:restricted"),
            secret_reference_requirements=(
                SkillSemanticReference("secretref:research-api"),
            ),
        ),
        execution=(
            SkillExecutionDeclaration(
                entrypoint=entrypoint,
                runtime=SkillExecutionRuntime.WASM,
                sandbox_profile_ref=SkillSemanticReference("sandbox:restricted"),
                resources=SkillResourceRequirement(30, 256, 500),
                required_tools=tools,
                input_schema_ref=schema,
                output_schema_ref=schema,
            ),
        ),
        governance_requirements=(
            SkillGovernanceRequirement(SkillSemanticReference("governance:rfc-approved")),
        ),
        evaluation_requirements=(
            SkillEvaluationRequirement(SkillSemanticReference("evalsuite:research-v2")),
        ),
        configuration_schema_ref=schema,
    )


@pytest.mark.parametrize(
    "value",
    (
        "",
        "ab",
        " skill",
        "skill ",
        "Skill-name",
        "skill/name",
        r"skill\name",
        "../skill",
        "skill_name",
        "skill$name",
        "á-skill",
        "skill--name",
        "-skill",
        "skill-",
        "con",
        "nul",
        "com1",
        "lpt9",
        "skill\u0000name",
        "a" * 65,
    ),
)
def test_skill_id_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(InvalidSkillId, match="canonical lowercase kebab-case"):
        SkillId(value)


def test_skill_id_is_stable_hashable_and_round_trips() -> None:
    value = SkillId.parse("research-synthesis")
    assert str(value) == value.to_canonical_text() == "research-synthesis"
    assert value == SkillId("research-synthesis")
    assert hash(value) == hash(SkillId("research-synthesis"))
    assert repr(value) == "SkillId(value='research-synthesis')"
    assert SkillId("abc").value == "abc"
    assert len(SkillId("a" + "b" * 62 + "c").value) == 64


@pytest.mark.parametrize(
    "value",
    (
        "",
        "1",
        "1.0",
        "01.0.0",
        "1.00.0",
        "1.0.00",
        "latest",
        "*",
        "^1.0.0",
        "v1.0.0",
        "1.0.0-01",
        "1.0.0+bad_metadata",
        "1\u0662.0.0",
    ),
)
def test_skill_version_rejects_non_semver_and_moving_values(value: str) -> None:
    with pytest.raises(InvalidSkillVersion):
        SkillVersion.parse(value)


def test_skill_version_parsing_round_trip_and_deterministic_ordering() -> None:
    values = (
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
        "1.0.0+build.1",
        "2.0.0",
    )
    parsed = tuple(SkillVersion.parse(value) for value in values)
    assert tuple(sorted(parsed)) == parsed
    assert tuple(str(value) for value in parsed) == values


def test_semver_official_precedence_examples() -> None:
    ordered = tuple(
        SkillVersion.parse(value)
        for value in (
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            "1.0.0-beta",
            "1.0.0-beta.2",
            "1.0.0-beta.11",
            "1.0.0-rc.1",
            "1.0.0",
        )
    )
    assert all(left < right for left, right in zip(ordered, ordered[1:]))


def test_semver_build_is_identity_but_not_precedence() -> None:
    first = SkillVersion.parse("1.0.0+build.1")
    second = SkillVersion.parse("1.0.0+build.2")
    assert first != second
    assert len({first, second}) == 2
    assert first.has_same_precedence(second)
    assert first.compare_precedence(second) == 0
    assert not first < second and not second < first
    assert str(first) == "1.0.0+build.1"


@pytest.mark.parametrize(
    "value",
    (
        "",
        "*",
        "latest",
        "1.0.0",
        "^1.0",
        "~1.2.3",
        ">=1.0.0,*",
        ">=1.0.0",
        "<2.0.0",
        ">=2.0.0,<1.0.0",
        ">=1.0.0,<=1.0.0",
        " >=1.0.0,<2.0.0",
        ">=1.0.0, <2.0.0",
        ">=1.0.0,<2.0.0 ",
        "^1.2.\u0663",
    ),
)
def test_version_constraint_is_distinct_and_strict(value: str) -> None:
    with pytest.raises(InvalidSkillVersionConstraint):
        SkillVersionConstraint(value)
    assert SkillVersionConstraint("^1.2.3") != SkillVersion.parse("1.2.3")


def test_version_constraint_accepts_only_documented_deterministic_forms() -> None:
    caret = SkillVersionConstraint("^1.2.3")
    bounded = SkillVersionConstraint(">=1.2.3,<2.0.0")
    exclusive = SkillVersionConstraint(">1.2.3,<=2.0.0")
    assert caret.kind == "caret"
    assert bounded.kind == exclusive.kind == "bounded_range"


def test_fingerprints_require_canonical_sha256() -> None:
    for factory in (
        SkillManifestFingerprint,
        SkillContentFingerprint,
        SkillPackageFingerprint,
    ):
        assert str(factory(SHA_A)) == SHA_A
        with pytest.raises(InvalidSkillFingerprint):
            factory(SHA_A.upper())
        with pytest.raises(InvalidSkillFingerprint):
            factory("abc")


def test_fingerprint_types_cannot_be_substituted() -> None:
    manifest_fingerprint = SkillManifestFingerprint(SHA_A)
    with pytest.raises(InvalidSkillContentReference):
        SkillContentRef(  # type: ignore[arg-type]
            SkillLogicalPath("SKILL.md"),
            manifest_fingerprint,
            SkillContentKind.INSTRUCTIONS,
            "text/plain",
            10,
        )
    with pytest.raises(ImmutableSkillIdentityMismatch):
        PublishedSkillVersionId(  # type: ignore[arg-type]
            SkillId("research-synthesis"),
            SkillVersion.parse("1.0.0"),
            SkillContentFingerprint(SHA_A),
            SkillManifestFingerprint(SHA_B),
        )


def test_manifest_format_rejects_unknown_versions_without_migration() -> None:
    assert str(SkillManifestFormatVersion.parse(1)) == "1"
    for value in (0, 2, -1, True):
        with pytest.raises(UnsupportedSkillManifestFormat):
            SkillManifestFormatVersion(value)
    with pytest.raises(UnsupportedSkillManifestFormat):
        SkillManifestFormatVersion("1")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    (
        "",
        "/absolute/file",
        r"C:\private\file",
        r"\\server\share",
        "../secret",
        "docs/../secret",
        "docs//file",
        "./file",
        "uri:https://example.test",
        "docs/file name.md",
        "dir/",
        "dir/\u0000file",
        "dír/file",
        "a" * 513,
    ),
)
def test_content_reference_rejects_unsafe_logical_paths(path: str) -> None:
    with pytest.raises(InvalidSkillContentReference):
        SkillLogicalPath(path)


def test_content_reference_contains_no_payload_or_filesystem_behavior() -> None:
    reference = _ref("docs/guide.md", SkillContentKind.DOCUMENTATION)
    assert fields(reference)
    assert not hasattr(reference, "payload")
    assert not hasattr(reference, "read")
    assert reference.logical_path == SkillLogicalPath("docs/guide.md")
    empty = SkillContentRef(
        SkillLogicalPath("empty.txt"),
        SkillContentFingerprint(SHA_A),
        SkillContentKind.RESOURCE,
        "text/plain",
        0,
    )
    assert empty.size_bytes == 0
    with pytest.raises(InvalidSkillContentReference):
        SkillContentRef(
            SkillLogicalPath("bad.txt"),
            SkillContentFingerprint(SHA_A),
            SkillContentKind.RESOURCE,
            "not-a-media-type",
            1,
        )
    with pytest.raises(InvalidSkillContentReference):
        SkillContentRef(
            SkillLogicalPath("bad.txt"),
            SkillContentFingerprint(SHA_A),
            SkillContentKind.RESOURCE,
            "text/plain",
            -1,
        )


def test_dependency_requires_exact_version_or_constraint_but_not_both() -> None:
    common = (SkillId("base-skill"), SkillDependencyReason.REQUIRED_WORKFLOW)
    with pytest.raises(InvalidSkillDependencyDeclaration):
        SkillDependencyDeclaration(*common)
    with pytest.raises(InvalidSkillDependencyDeclaration):
        SkillDependencyDeclaration(
            *common,
            version=SkillVersion.parse("1.0.0"),
            constraint=SkillVersionConstraint("^1.0.0"),
        )


def test_compatibility_is_declaration_not_decision() -> None:
    declaration = SkillCompatibilityDeclaration(
        platforms=(SkillRequirementId("linux"), SkillRequirementId("windows")),
        python_constraint=SkillVersionConstraint(">=3.12.0,<4.0.0"),
    )
    assert not hasattr(declaration, "compatible")
    assert not hasattr(declaration, "decision")


def test_security_declaration_cannot_grant_authority() -> None:
    with pytest.raises(InvalidSkillSecurityDeclaration):
        SkillSecurityDeclaration(
            network_requirement=NetworkRequirement.NONE,
            egress_requirement=EgressRequirement.DECLARED,
        )
    declaration = SkillSecurityDeclaration()
    assert {
        "network_requirement",
        "external_processing_requirement",
        "filesystem_requirement",
        "egress_requirement",
        "sandbox_profile_requirement",
        "secret_reference_requirements",
    }.issubset(field.name for field in fields(declaration))
    for forbidden in ("permission", "trusted", "approved", "credential", "token"):
        assert not hasattr(declaration, forbidden)


def test_execution_declaration_is_non_executable_and_schema_typed() -> None:
    entrypoint = _ref(
        "entrypoints/main.wasm",
        SkillContentKind.ENTRYPOINT,
        media_type="application/wasm",
    )
    declaration = SkillExecutionDeclaration(
        entrypoint,
        SkillExecutionRuntime.WASM,
        SkillSemanticReference("sandbox:restricted"),
        SkillResourceRequirement(10, 128, 250),
    )
    for forbidden in ("execute", "callable", "command", "arguments", "environment"):
        assert not hasattr(declaration, forbidden)
    with pytest.raises(InvalidPublishedSkillManifest):
        SkillExecutionDeclaration(
            _ref("docs/guide.md", SkillContentKind.DOCUMENTATION),
            SkillExecutionRuntime.WASM,
            SkillSemanticReference("sandbox:restricted"),
            SkillResourceRequirement(10, 128, 250),
        )


def test_manifest_is_deeply_immutable_and_has_no_lifecycle_or_payload() -> None:
    manifest = _manifest()
    with pytest.raises(FrozenInstanceError):
        manifest.display_name = "Changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        manifest.content.append("value")  # type: ignore[attr-defined]
    forbidden = {
        "status",
        "active",
        "disabled",
        "deprecated",
        "installed",
        "trusted",
        "approved",
        "evaluated",
        "promoted",
        "revoked",
        "local_path",
        "metadata",
        "payload",
    }
    assert forbidden.isdisjoint(field.name for field in fields(manifest))


def test_manifest_canonical_serialization_and_fingerprint_ignore_input_order() -> None:
    first = _manifest()
    second = _manifest(reverse=True)
    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.fingerprint() == second.fingerprint()
    assert b"status" not in first.canonical_bytes()
    assert b"local_path" not in first.canonical_bytes()


def test_manifest_rejects_duplicates_and_self_dependency() -> None:
    manifest = _manifest()
    with pytest.raises(InvalidPublishedSkillManifest, match="unique"):
        replace(manifest, content=(manifest.content[0], manifest.content[0]))
    self_dependency = SkillDependencyDeclaration(
        manifest.skill_id,
        SkillDependencyReason.REQUIRED_WORKFLOW,
        version=SkillVersion.parse("1.0.0"),
    )
    with pytest.raises(InvalidPublishedSkillManifest, match="depend on itself"):
        replace(manifest, dependencies=(self_dependency,))


def test_manifest_hash_and_fingerprint_survive_failed_nested_mutation() -> None:
    manifest = _manifest()
    original_hash = hash(manifest)
    original_fingerprint = manifest.fingerprint()
    nested = manifest.compatibility.operating_profiles
    with pytest.raises(AttributeError):
        nested.append(SkillRequirementId("new-profile"))  # type: ignore[attr-defined]
    with pytest.raises(FrozenInstanceError):
        manifest.provenance.publisher_ref = SkillSemanticReference(  # type: ignore[misc]
            "publisher:changed"
        )
    assert hash(manifest) == original_hash
    assert manifest.fingerprint() == original_fingerprint


def test_manifest_semantic_changes_and_build_metadata_change_fingerprint() -> None:
    manifest = _manifest()
    assert replace(manifest, display_name="Changed display").fingerprint() != manifest.fingerprint()
    assert replace(manifest, description="Changed description").fingerprint() != manifest.fingerprint()
    changed_build = replace(
        manifest,
        version=SkillVersion.parse("2.1.0-rc.1+build.8"),
    )
    assert changed_build.fingerprint() != manifest.fingerprint()


def test_manifest_canonical_golden_vector_is_process_independent() -> None:
    manifest = _manifest()
    expected = "d7b299d31602dfbdc2b67664e33cb67b4985ab09b8a0ccea5b585740728d8534"
    assert str(manifest.fingerprint()) == expected
    assert manifest.canonical_bytes().startswith(b'{"capabilities":')
    assert manifest.canonical_bytes().endswith(b'"version":"2.1.0-rc.1+build.7"}')
    assert b'"format_version":1' in manifest.canonical_bytes()
    assert manifest.fingerprint() == _manifest(reverse=True).fingerprint()


def test_manifest_constructor_rejects_unknown_and_missing_fields() -> None:
    with pytest.raises(TypeError):
        PublishedSkillManifest(unknown="value")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PublishedSkillManifest()  # type: ignore[call-arg]


def test_domain_constructors_reject_runtime_type_coercion() -> None:
    manifest = _manifest()
    values = {
        field.name: getattr(manifest, field.name)
        for field in fields(manifest)
    }
    values["skill_id"] = "research-synthesis"
    with pytest.raises(InvalidPublishedSkillManifest):
        PublishedSkillManifest(**values)  # type: ignore[arg-type]
    with pytest.raises(InvalidSkillContentReference):
        SkillContentRef(  # type: ignore[arg-type]
            "SKILL.md",
            SkillContentFingerprint(SHA_A),
            SkillContentKind.INSTRUCTIONS,
            "text/plain",
            10,
        )
    with pytest.raises(ImmutableSkillIdentityMismatch):
        PublishedSkillVersionId(  # type: ignore[arg-type]
            "research-synthesis",
            SkillVersion.parse("1.0.0"),
            SkillManifestFingerprint(SHA_A),
            SkillContentFingerprint(SHA_B),
        )
    values["skill_id"] = SkillId("research-synthesis")
    values["content"] = list(manifest.content)
    with pytest.raises(InvalidPublishedSkillManifest):
        PublishedSkillManifest(**values)  # type: ignore[arg-type]


def test_publication_identity_is_path_and_lifecycle_independent() -> None:
    manifest = _manifest()
    identity = PublishedSkillVersionId.from_manifest(
        manifest,
        SkillContentFingerprint(SHA_C),
    )
    assert str(identity).startswith("research-synthesis@2.1.0-rc.1+build.7#manifest-sha256:")
    assert "content-sha256:" in identity.to_canonical_text()
    assert PublishedSkillVersionId.parse(identity.to_canonical_text()) == identity
    forbidden = {"path", "installed", "active", "trusted", "approved", "timestamp", "row_id"}
    assert forbidden.isdisjoint(field.name for field in fields(identity))
    identity.assert_manifest(manifest)
    with pytest.raises(ImmutableSkillIdentityMismatch):
        PublishedSkillVersionId(
            identity.skill_id,
            identity.version,
            SkillManifestFingerprint(SHA_A),
            identity.content_fingerprint,
        ).assert_manifest(manifest)


def test_publication_identity_changes_for_every_identity_component() -> None:
    original = PublishedSkillVersionId.from_manifest(_manifest(), SkillContentFingerprint(SHA_C))
    variants = (
        replace(original, skill_id=SkillId("other-skill")),
        replace(original, version=SkillVersion.parse("3.0.0")),
        replace(original, manifest_fingerprint=SkillManifestFingerprint(SHA_A)),
        replace(original, content_fingerprint=SkillContentFingerprint(SHA_B)),
    )
    assert all(item != original for item in variants)
    assert len({original, *variants}) == 5
    with pytest.raises(ImmutableSkillIdentityMismatch):
        PublishedSkillVersionId.parse("not-a-publication-identity")


def test_errors_have_fixed_safe_messages_and_do_not_leak_raw_input() -> None:
    raw = "SECRET-RAW-INPUT"
    with pytest.raises(SkillPhase2DomainError) as captured:
        SkillId(raw)
    assert raw not in str(captured.value)
    assert raw not in repr(captured.value)
    assert captured.value.__cause__ is None
    raw_identity = f"{raw}@not-semver#manifest-sha256:{SHA_A};content-sha256:{SHA_B}"
    with pytest.raises(ImmutableSkillIdentityMismatch) as parsed:
        PublishedSkillVersionId.parse(raw_identity)
    assert raw not in str(parsed.value)
    assert parsed.value.__cause__ is not None
    assert raw not in str(parsed.value.__cause__)
    assert raw not in repr(parsed.value.__cause__)


def test_public_phase2_surface_is_exactly_the_eight_domain_contracts() -> None:
    expected = {
        "PublishedSkillManifest",
        "PublishedSkillVersionId",
        "SkillContentFingerprint",
        "SkillId",
        "SkillManifestFingerprint",
        "SkillManifestFormatVersion",
        "SkillVersion",
        "SkillVersionConstraint",
    }
    assert expected.issubset(skills_api.__all__)
    internal = {
        "SkillSecurityDeclaration",
        "SkillExecutionDeclaration",
        "SkillProvenance",
        "canonical_json_bytes",
        "domain_data",
    }
    assert internal.isdisjoint(skills_api.__all__)


def test_phase1_models_coexist_without_becoming_phase2_authority() -> None:
    assert "active" in SKILL_STATUSES
    assert "status" in {field.name for field in fields(SkillManifest)}
    assert "status" not in {field.name for field in fields(PublishedSkillManifest)}
