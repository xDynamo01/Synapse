from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.scheduler.jobs import JOB_STATUSES, Job


class JobQueue:
    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def add(self, job: Job) -> Job:
        self._validate(job)
        self._write(job)
        return job

    def list_jobs(self, status: str | None = None) -> list[Job]:
        if status and status not in JOB_STATUSES:
            raise ValidationError(f"Invalid job status: {status}")
        jobs_dir = self.data_dir.resolve("jobs")
        jobs = [self._read(path) for path in sorted(jobs_dir.glob("*.yaml"))]
        if status:
            jobs = [job for job in jobs if job.status == status]
        return sorted(jobs, key=lambda job: (job.priority, job.created_at, job.id))

    def get(self, job_id: str) -> Job:
        path = self._path(job_id)
        if not path.exists():
            raise NotFound(f"Job not found: {job_id}")
        return self._read(path)

    def save(self, job: Job) -> Job:
        self._validate(job)
        self._write(job)
        return job

    def next_pending(self) -> Job | None:
        for job in self.list_jobs(status="pending"):
            if job.is_due():
                return job
        return None

    def _path(self, job_id: str) -> Path:
        return self.data_dir.resolve(f"jobs/{job_id}.yaml")

    def _write(self, job: Job) -> None:
        dump_structured_file(self._path(job.id), asdict(job))

    @staticmethod
    def _validate(job: Job) -> None:
        if job.status not in JOB_STATUSES:
            raise ValidationError(f"Invalid job status: {job.status}")
        if job.max_attempts < 1:
            raise ValidationError("Job max_attempts must be at least 1.")
        if job.attempts < 0:
            raise ValidationError("Job attempts cannot be negative.")

    @staticmethod
    def _read(path: Path) -> Job:
        raw = load_structured_file(path)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("parent_id", None)
        raw.setdefault("source", None)
        return Job(**raw)
