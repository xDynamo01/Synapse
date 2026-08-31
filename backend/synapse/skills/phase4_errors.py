from __future__ import annotations


class SkillVerificationError(ValueError):
    """Base error for safe, local Phase 2 package verification."""

    code = "skill_verification_error"
    safe_message = "skill package verification failed"

    def __init__(self) -> None:
        super().__init__(self.safe_message)


class InvalidRawSkillManifest(SkillVerificationError):
    code = "invalid_raw_skill_manifest"
    safe_message = "raw skill manifest is invalid"


class InvalidSkillVerificationPolicy(SkillVerificationError):
    code = "invalid_skill_verification_policy"
    safe_message = "skill verification policy is invalid"


class DuplicateSkillManifestKey(SkillVerificationError):
    code = "duplicate_skill_manifest_key"
    safe_message = "skill manifest contains a duplicate key"


class UnsupportedSkillManifestFeature(SkillVerificationError):
    code = "unsupported_skill_manifest_feature"
    safe_message = "skill manifest uses an unsupported feature"


class UnsafeSkillManifestTag(SkillVerificationError):
    code = "unsafe_skill_manifest_tag"
    safe_message = "skill manifest contains an unsafe tag"


class UnknownSkillManifestField(SkillVerificationError):
    code = "unknown_skill_manifest_field"
    safe_message = "skill manifest contains an unknown field"


class MissingSkillManifestField(SkillVerificationError):
    code = "missing_skill_manifest_field"
    safe_message = "skill manifest is missing a required field"


class InvalidSkillPackageRoot(SkillVerificationError):
    code = "invalid_skill_package_root"
    safe_message = "skill package root is invalid"


class SkillPackagePathEscape(SkillVerificationError):
    code = "skill_package_path_escape"
    safe_message = "skill package path is unsafe"


class UnsafeSkillPackageLink(SkillVerificationError):
    code = "unsafe_skill_package_link"
    safe_message = "skill package contains an unsafe link"


class UnsupportedSkillPackageFileType(SkillVerificationError):
    code = "unsupported_skill_package_file_type"
    safe_message = "skill package contains an unsupported file type"


class SkillVerificationResourceLimitExceeded(SkillVerificationError):
    code = "skill_verification_resource_limit_exceeded"
    safe_message = "skill verification resource limit was exceeded"


class SkillAssetMissing(SkillVerificationError):
    code = "skill_asset_missing"
    safe_message = "a declared skill asset is missing"


class UndeclaredSkillAsset(SkillVerificationError):
    code = "undeclared_skill_asset"
    safe_message = "skill package contains an undeclared asset"


class SkillAssetChecksumMismatch(SkillVerificationError):
    code = "skill_asset_checksum_mismatch"
    safe_message = "skill asset checksum does not match its declaration"


class SkillContentChangedDuringVerification(SkillVerificationError):
    code = "skill_content_changed_during_verification"
    safe_message = "skill content changed during verification"


class SkillContentFingerprintMismatch(SkillVerificationError):
    code = "skill_content_fingerprint_mismatch"
    safe_message = "skill content fingerprint does not match"


class InvalidSkillSnapshotCorrespondence(SkillVerificationError):
    code = "invalid_skill_snapshot_correspondence"
    safe_message = "skill manifest and verified content do not correspond"
