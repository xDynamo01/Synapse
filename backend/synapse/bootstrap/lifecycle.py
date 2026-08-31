from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event, Lock, Thread
from time import perf_counter
from typing import Any, Callable, Protocol


class Startable(Protocol):
    def start(self) -> None: ...


class Closable(Protocol):
    def close(self) -> None: ...


LifecycleAction = Callable[[], Any]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class LifecycleResource:
    name: str
    feature: str = "unspecified"
    reason: str = ""
    start: LifecycleAction | None = None
    close: LifecycleAction | None = None
    required: bool = True
    startup_timeout_seconds: float = 30.0
    shutdown_timeout_seconds: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LifecycleActionResult:
    resource: str
    action: str
    status: str
    duration_ms: int
    required: bool = True
    error_type: str | None = None
    error: str | None = None
    causal_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class LifecycleReport:
    phase: str
    status: str
    started_at: str
    completed_at: str
    results: tuple[LifecycleActionResult, ...]


class LifecycleStartupError(RuntimeError):
    def __init__(self, report: LifecycleReport, failed: LifecycleActionResult | None = None):
        if failed is None:
            message = "Required lifecycle resource failed during startup"
        else:
            cause = f"{failed.error_type}: {failed.error}" if failed.error_type and failed.error else failed.status
            message = (
                "Required lifecycle resource failed: "
                f"resource={failed.resource} action={failed.action} cause={cause}"
            )
        super().__init__(message)
        self.report = report
        self.failed = failed


@dataclass(frozen=True)
class _LifecycleInvocation:
    result: LifecycleActionResult
    exception: BaseException | None = None


class LifecycleManager:
    """Starts registered resources in order and closes them in reverse order."""

    def __init__(self) -> None:
        self._resources: list[LifecycleResource] = []
        self._started: list[LifecycleResource] = []
        self._lock = Lock()
        self._start_report: LifecycleReport | None = None
        self._close_report: LifecycleReport | None = None

    @property
    def resources(self) -> tuple[LifecycleResource, ...]:
        return tuple(self._resources)

    @property
    def start_report(self) -> LifecycleReport | None:
        return self._start_report

    @property
    def close_report(self) -> LifecycleReport | None:
        return self._close_report

    def register(self, resource: LifecycleResource) -> None:
        with self._lock:
            if self._start_report is not None:
                raise RuntimeError("Lifecycle resources cannot be registered after startup")
            if any(item.name == resource.name for item in self._resources):
                raise ValueError(f"Lifecycle resource already registered: {resource.name}")
            self._resources.append(resource)

    def start(self) -> LifecycleReport:
        with self._lock:
            if self._start_report is not None:
                return self._start_report
            started_at = _now()
            results: list[LifecycleActionResult] = []
            for resource in self._resources:
                _log_lifecycle("startup begin", resource.name, resource.required)
                if resource.start is None:
                    self._started.append(resource)
                    results.append(_skipped(resource.name, "start", resource.required))
                    _log_lifecycle("startup success", resource.name, resource.required)
                    continue
                invocation = _invoke(
                    resource.name,
                    "start",
                    resource.start,
                    resource.startup_timeout_seconds,
                    resource.required,
                )
                result = invocation.result
                results.append(result)
                if result.status == "ok":
                    self._started.append(resource)
                    _log_lifecycle("startup success", resource.name, resource.required)
                    continue
                _log_lifecycle(
                    "startup failure",
                    resource.name,
                    resource.required,
                    result.error_type,
                    result.error,
                    result.causal_chain,
                )
                if resource.required:
                    rollback = self._close_started()
                    results.extend(rollback)
                    report = _report("startup", "failed", started_at, results)
                    self._start_report = report
                    self._close_report = _report(
                        "shutdown",
                        "completed"
                        if all(item.status in {"ok", "skipped"} for item in rollback)
                        else "degraded",
                        started_at,
                        rollback,
                    )
                    if invocation.exception is not None:
                        raise LifecycleStartupError(report, result) from invocation.exception
                    raise LifecycleStartupError(report, result)
            self._start_report = _report(
                "startup",
                "ready"
                if all(item.status in {"ok", "skipped"} for item in results)
                else "degraded",
                started_at,
                results,
            )
            return self._start_report

    def close(self) -> LifecycleReport:
        with self._lock:
            if self._close_report is not None:
                return self._close_report
            started_at = _now()
            results = self._close_started()
            self._close_report = _report(
                "shutdown",
                "completed"
                if all(item.status in {"ok", "skipped"} for item in results)
                else "degraded",
                started_at,
                results,
            )
            return self._close_report

    def _close_started(self) -> list[LifecycleActionResult]:
        results: list[LifecycleActionResult] = []
        while self._started:
            resource = self._started.pop()
            if resource.close is None:
                results.append(_skipped(resource.name, "close", resource.required))
                continue
            results.append(
                _invoke(
                    resource.name,
                    "close",
                    resource.close,
                    resource.shutdown_timeout_seconds,
                    resource.required,
                ).result
            )
        return results


def _invoke(
    resource: str,
    action: str,
    callback: LifecycleAction,
    timeout_seconds: float,
    required: bool,
) -> _LifecycleInvocation:
    started = perf_counter()
    completed = Event()
    outcome: dict[str, BaseException | None] = {"error": None}

    def run() -> None:
        try:
            callback()
        except BaseException as exc:  # cleanup must report all failures
            outcome["error"] = exc
        finally:
            completed.set()

    worker = Thread(target=run, name=f"synapse-lifecycle-{action}-{resource}", daemon=True)
    worker.start()
    finished = completed.wait(max(0.001, timeout_seconds))
    duration_ms = int((perf_counter() - started) * 1000)
    if not finished:
        return _LifecycleInvocation(LifecycleActionResult(resource, action, "timeout", duration_ms, required))
    error = outcome["error"]
    if error is not None:
        return _LifecycleInvocation(
            LifecycleActionResult(
                resource,
                action,
                "failed",
                duration_ms,
                required,
                type(error).__name__,
                _safe_error_message(error),
                _safe_causal_chain(error),
            ),
            error,
        )
    return _LifecycleInvocation(LifecycleActionResult(resource, action, "ok", duration_ms, required))


def _skipped(resource: str, action: str, required: bool) -> LifecycleActionResult:
    return LifecycleActionResult(resource, action, "skipped", 0, required)


def _report(
    phase: str,
    status: str,
    started_at: str,
    results: list[LifecycleActionResult],
) -> LifecycleReport:
    return LifecycleReport(phase, status, started_at, _now(), tuple(results))


def _safe_error_message(error: BaseException) -> str:
    return _redact(str(error) or type(error).__name__)


def _safe_causal_chain(error: BaseException) -> tuple[str, ...]:
    chain: list[str] = []
    seen: set[int] = set()
    current = error.__cause__ or error.__context__
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(f"{type(current).__name__}: {_safe_error_message(current)}")
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _redact(value: str) -> str:
    sanitized = value.replace("\r", " ").replace("\n", " ")
    for marker in ("token", "api_key", "apikey", "secret", "password"):
        lowered = sanitized.lower()
        index = lowered.find(marker)
        while index >= 0:
            end = sanitized.find(" ", index)
            if end < 0:
                end = len(sanitized)
            sanitized = f"{sanitized[:index]}{marker}=<redacted>{sanitized[end:]}"
            lowered = sanitized.lower()
            index = lowered.find(marker, index + len(marker))
    return " ".join(sanitized.split())


def _log_lifecycle(
    event: str,
    resource: str,
    required: bool,
    error_type: str | None = None,
    error: str | None = None,
    causal_chain: tuple[str, ...] = (),
) -> None:
    payload = f"[lifecycle] {event}: resource={resource} required={required}"
    if error_type:
        payload += f" error_type={error_type}"
    if error:
        payload += f" error={_redact(error)}"
    if causal_chain:
        payload += f" causal_chain={' | '.join(causal_chain)}"
    print(payload, flush=True)
