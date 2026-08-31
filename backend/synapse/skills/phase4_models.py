from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from synapse.skills.phase2_models import PublishedSkillManifest, SkillContentKind
from synapse.skills.phase2_values import (
    SkillContentFingerprint,
    SkillLogicalPath,
    SkillManifestFingerprint,
    SkillSemanticReference,
)
from synapse.skills.phase4_errors import (
    InvalidSkillSnapshotCorrespondence,
    InvalidSkillVerificationPolicy,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POLICY_BOUNDS = {
    "max_manifest_bytes": (1, 1_048_576),
    "max_files": (1, 4_096),
    "max_file_bytes": (1, 268_435_456),
    "max_total_bytes": (1, 1_073_741_824),
    "max_depth": (1, 64),
    "max_path_chars": (1, 1_024),
    "max_declarations": (1, 4_096),
    "max_scalar_chars": (1, 65_536),
    "max_yaml_depth": (1, 64),
    "max_yaml_collection_items": (1, 65_536),
    "max_yaml_tokens": (1, 131_072),
    "read_chunk_bytes": (1, 1_048_576),
}


@dataclass(frozen=True, order=True)
class SkillAssetChecksum:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SHA256.fullmatch(self.value):
            raise InvalidSkillSnapshotCorrespondence()

    def __str__(self) -> str:
        return self.value

    def to_canonical_text(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillVerificationPolicyVersion:
    value: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or self.value != 1:
            raise InvalidSkillVerificationPolicy()


@dataclass(frozen=True)
class SkillVerificationPolicy:
    version: SkillVerificationPolicyVersion = SkillVerificationPolicyVersion()
    max_manifest_bytes: int = 262_144
    max_files: int = 256
    max_file_bytes: int = 16_777_216
    max_total_bytes: int = 67_108_864
    max_depth: int = 16
    max_path_chars: int = 512
    max_declarations: int = 512
    max_scalar_chars: int = 16_384
    max_yaml_depth: int = 32
    max_yaml_collection_items: int = 4_096
    max_yaml_tokens: int = 16_384
    read_chunk_bytes: int = 65_536

    def __post_init__(self) -> None:
        if not isinstance(self.version, SkillVerificationPolicyVersion):
            raise InvalidSkillVerificationPolicy()
        for name, (minimum, maximum) in _POLICY_BOUNDS.items():
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise InvalidSkillVerificationPolicy()
        if self.max_file_bytes > self.max_total_bytes:
            raise InvalidSkillVerificationPolicy()


@dataclass(frozen=True, order=True)
class VerifiedSkillAsset:
    logical_path: SkillLogicalPath
    kind: SkillContentKind
    media_type: str
    size_bytes: int
    checksum: SkillAssetChecksum
    role: SkillSemanticReference | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.logical_path, SkillLogicalPath)
            or not isinstance(self.kind, SkillContentKind)
            or not isinstance(self.media_type, str)
            or isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
            or not isinstance(self.checksum, SkillAssetChecksum)
            or (self.role is not None and not isinstance(self.role, SkillSemanticReference))
        ):
            raise InvalidSkillSnapshotCorrespondence()


@dataclass(frozen=True)
class SkillVerificationMetadata:
    verified_at: datetime
    verifier_ref: SkillSemanticReference
    verifier_version: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.verified_at, datetime)
            or self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() is None
            or not isinstance(self.verifier_ref, SkillSemanticReference)
            or not isinstance(self.verifier_version, str)
            or not self.verifier_version
        ):
            raise InvalidSkillSnapshotCorrespondence()

    @classmethod
    def now(cls) -> SkillVerificationMetadata:
        return cls(
            datetime.now(UTC),
            SkillSemanticReference("verifier:synapse-phase4-local"),
            "1",
        )


@dataclass(frozen=True)
class VerifiedSkillContentSnapshot:
    manifest: PublishedSkillManifest
    manifest_fingerprint: SkillManifestFingerprint
    content_fingerprint: SkillContentFingerprint
    assets: tuple[VerifiedSkillAsset, ...]
    policy_version: SkillVerificationPolicyVersion
    verification: SkillVerificationMetadata

    def __post_init__(self) -> None:
        if (
            not isinstance(self.manifest, PublishedSkillManifest)
            or self.manifest.fingerprint() != self.manifest_fingerprint
            or not isinstance(self.content_fingerprint, SkillContentFingerprint)
            or not isinstance(self.assets, tuple)
            or any(not isinstance(item, VerifiedSkillAsset) for item in self.assets)
            or tuple(sorted(self.assets, key=lambda item: item.logical_path.value))
            != self.assets
            or len({item.logical_path for item in self.assets}) != len(self.assets)
            or not isinstance(self.policy_version, SkillVerificationPolicyVersion)
            or not isinstance(self.verification, SkillVerificationMetadata)
            or content_fingerprint(self.assets) != self.content_fingerprint
        ):
            raise InvalidSkillSnapshotCorrespondence()

    @property
    def technical_identity(
        self,
    ) -> tuple[SkillManifestFingerprint, SkillContentFingerprint]:
        return self.manifest_fingerprint, self.content_fingerprint


def content_fingerprint(
    assets: tuple[VerifiedSkillAsset, ...],
) -> SkillContentFingerprint:
    projection = tuple(
        {
            "checksum_sha256": asset.checksum.value,
            "kind": asset.kind.value,
            "logical_path": asset.logical_path.value,
            "media_type": asset.media_type,
            "role": None if asset.role is None else asset.role.value,
            "size_bytes": asset.size_bytes,
        }
        for asset in sorted(assets, key=lambda item: item.logical_path.value)
    )
    canonical = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return SkillContentFingerprint(hashlib.sha256(canonical).hexdigest())
