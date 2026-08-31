from __future__ import annotations

from typing import Any


class PrivateEvalDomainError(ValueError):
    code = "private_eval_domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class InvalidIdentity(PrivateEvalDomainError):
    code = "invalid_identity"


class InvalidVersion(PrivateEvalDomainError):
    code = "invalid_version"


class InvalidRevision(PrivateEvalDomainError):
    code = "invalid_revision"


class InvalidChecksum(PrivateEvalDomainError):
    code = "invalid_checksum"


class InvalidFingerprint(PrivateEvalDomainError):
    code = "invalid_fingerprint"


class InvalidTimestamp(PrivateEvalDomainError):
    code = "invalid_timestamp"


class InvalidSuite(PrivateEvalDomainError):
    code = "invalid_suite"


class InvalidCase(PrivateEvalDomainError):
    code = "invalid_case"


class InvalidDatasetBinding(PrivateEvalDomainError):
    code = "invalid_dataset_binding"


class InvalidRun(PrivateEvalDomainError):
    code = "invalid_run"


class InvalidRunManifest(PrivateEvalDomainError):
    code = "invalid_run_manifest"


class InvalidResult(PrivateEvalDomainError):
    code = "invalid_result"


class InvalidScore(PrivateEvalDomainError):
    code = "invalid_score"


class InvalidBaseline(PrivateEvalDomainError):
    code = "invalid_baseline"


class InvalidComparison(PrivateEvalDomainError):
    code = "invalid_comparison"


class InvalidRegressionRule(PrivateEvalDomainError):
    code = "invalid_regression_rule"


class InvalidRegressionReport(PrivateEvalDomainError):
    code = "invalid_regression_report"


class DuplicateReference(PrivateEvalDomainError):
    code = "duplicate_reference"


class SensitivePayloadViolation(PrivateEvalDomainError):
    code = "sensitive_payload_violation"


class IncompatibleReference(PrivateEvalDomainError):
    code = "incompatible_reference"


class InvalidBaselineSource(InvalidBaseline):
    code = "invalid_baseline_source"


class BaselineFingerprintMismatch(InvalidBaseline):
    code = "baseline_fingerprint_mismatch"


class MissingBaselineAuthority(InvalidBaseline):
    code = "missing_baseline_authority"


class IncompatibleComparison(InvalidComparison):
    code = "incompatible_comparison"


class MetricDirectionMissing(InvalidComparison):
    code = "metric_direction_missing"


class IncompatibleMetricScale(InvalidComparison):
    code = "incompatible_metric_scale"


class MissingAggregate(InvalidComparison):
    code = "missing_aggregate"


class InvalidDelta(InvalidComparison):
    code = "invalid_delta"


class RegressionEvaluationFailure(PrivateEvalDomainError):
    code = "regression_evaluation_failure"


class ComparisonFingerprintMismatch(PrivateEvalDomainError):
    code = "comparison_fingerprint_mismatch"


class ReportFingerprintMismatch(PrivateEvalDomainError):
    code = "report_fingerprint_mismatch"
