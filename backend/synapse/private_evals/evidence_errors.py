from __future__ import annotations

from .errors import PrivateEvalDomainError


class EvalEvidenceError(PrivateEvalDomainError):
    code = "eval_evidence_error"


class IncompleteEvidence(EvalEvidenceError):
    code = "incomplete_evidence"


class InvalidEvidenceSource(EvalEvidenceError):
    code = "invalid_evidence_source"


class GovernanceBindingMismatch(EvalEvidenceError):
    code = "governance_binding_mismatch"


class EvalRequirementMismatch(EvalEvidenceError):
    code = "eval_requirement_mismatch"


class RFCRevisionMissing(EvalEvidenceError):
    code = "rfc_revision_missing"


class MetricNotAllowed(EvalEvidenceError):
    code = "metric_not_allowed"


class ProjectionFingerprintMismatch(EvalEvidenceError):
    code = "projection_fingerprint_mismatch"


class ProjectionChecksumMismatch(EvalEvidenceError):
    code = "projection_checksum_mismatch"


class SensitiveEvidenceContent(EvalEvidenceError):
    code = "sensitive_evidence_content"


class IncompatibleEvidenceSource(EvalEvidenceError):
    code = "incompatible_evidence_source"
