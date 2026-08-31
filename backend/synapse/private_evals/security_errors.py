from __future__ import annotations

from .errors import PrivateEvalDomainError


class EvalSecurityError(PrivateEvalDomainError):
    code = "eval_security_error"


class AssetNotFound(EvalSecurityError):
    code = "asset_not_found"


class AssetRevisionMismatch(EvalSecurityError):
    code = "asset_revision_mismatch"


class AssetChecksumMismatch(EvalSecurityError):
    code = "asset_checksum_mismatch"


class AssetOwnerMismatch(EvalSecurityError):
    code = "asset_owner_mismatch"


class AssetClassificationMismatch(EvalSecurityError):
    code = "asset_classification_mismatch"


class CustodyNotGoverned(EvalSecurityError):
    code = "custody_not_governed"


class DesktopSourceProhibited(EvalSecurityError):
    code = "desktop_source_prohibited"


class ProviderProjectionMismatch(EvalSecurityError):
    code = "provider_projection_mismatch"


class SecurityProjectionMismatch(EvalSecurityError):
    code = "security_projection_mismatch"


class CanonicalEgressResponseInvalid(EvalSecurityError):
    code = "canonical_egress_response_invalid"


class DerivedAssetInvalid(EvalSecurityError):
    code = "derived_asset_invalid"


class ProvenanceIncomplete(EvalSecurityError):
    code = "provenance_incomplete"
