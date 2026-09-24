"""SLURM scheduler client."""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Callable

from ..common.models import (
    AllocationRequest,
    AllocationStatus,
    ExecutionHandle,
    ExecutionRequest,
    ExecutionStatus,
    ResourceInfo,
    SchedulerReference,
)

Runner = Callable[..., subprocess.CompletedProcess[str]]
_JOB_ID = re.compile(r"^(?:.*?\bjob\s+(?:allocation\s+)?|)(\d+)\b", re.IGNORECASE)


class SlurmClient:
    """SLURM client with injectable subprocess execution for tests."""

    scheduler_name = "slurm"

    def __init__(self, *, runner: Runner = subprocess.run) -> None:
        self._runner = runner
        self._allocations: dict[str, SchedulerReference] = {}
        self._execution_logs: dict[str, tuple[str, str]] = {}
        self._execution_statuses: dict[str, ExecutionStatus] = {}

    def allocate(self, request: AllocationRequest | dict[str, Any]) -> SchedulerReference:
        request = AllocationRequest.model_validate(request)
        command = ["salloc", "--no-shell"]
        if request.walltime_seconds is not None:
            command.extend(["--time", str(request.walltime_seconds)])
        if request.resource_count is not None:
            command.extend(["--ntasks", str(request.resource_count)])
        completed = self._run(command)
        reference = self._job_reference(completed.stdout or completed.stderr)
        if completed.returncode != 0 or reference is None:
            raise RuntimeError("SLURM allocation failed")
        result_reference = SchedulerReference(scheduler="slurm", reference=reference)
        self._allocations[result_reference.reference] = result_reference
        return result_reference

    def attach(self, reference: SchedulerReference | dict[str, str]) -> SchedulerReference:
        reference = SchedulerReference.model_validate(reference)
        self._require(reference)
        completed = self._run(["squeue", "--noheader", "--jobs", reference.reference])
        if completed.returncode != 0 or not completed.stdout.strip():
            raise RuntimeError("SLURM allocation is not available")
        return reference

    def status(self, reference: SchedulerReference | dict[str, str]) -> AllocationStatus:
        reference = SchedulerReference.model_validate(reference)
        self._require(reference)
        completed = self._run(["squeue", "--noheader", "--jobs", reference.reference, "--format", "%T"])
        if completed.returncode == 0 and completed.stdout.strip():
            return self._status(completed.stdout.strip())
        accounting = self._run(["sacct", "--noheader", "--jobs", reference.reference, "--format", "State"])
        if accounting.returncode == 0 and accounting.stdout.strip():
            return self._status(accounting.stdout.strip().splitlines()[0])
        return AllocationStatus.NOT_FOUND

    def list_resources(self) -> list[ResourceInfo]:
        completed = self._run(["sinfo", "--noheader", "--format", "%P|%a|%D"])
        if completed.returncode != 0:
            return []
        resources: list[ResourceInfo] = []
        for line in completed.stdout.splitlines():
            fields = line.strip().split("|")
            if len(fields) != 3:
                continue
            try:
                available = int(fields[2])
            except ValueError:
                available = None
            resources.append(ResourceInfo(name=fields[0].rstrip("*"), available=available, unit="nodes"))
        return resources

    def list_queue(self) -> list[dict[str, str]]:
        completed = self._run(["squeue", "--noheader", "--format", "%i|%T|%P"])
        if completed.returncode != 0:
            return []
        entries: list[dict[str, str]] = []
        for line in completed.stdout.splitlines():
            fields = line.split("|", 2)
            if len(fields) == 3:
                entries.append({"reference": fields[0], "status": fields[1], "partition": fields[2]})
        return entries

    def get_cluster_info(self) -> list[dict[str, str]]:
        completed = self._run(["sinfo", "--noheader", "--format", "%P|%a|%D|%T"])
        if completed.returncode != 0:
            return []
        entries: list[dict[str, str]] = []
        for line in completed.stdout.splitlines():
            fields = line.split("|", 3)
            if len(fields) == 4:
                entries.append({"partition": fields[0].rstrip("*"), "availability": fields[1], "nodes": fields[2], "state": fields[3]})
        return entries

    def list_allocations(self) -> list[SchedulerReference]:
        return list(getattr(self, "_allocations", {}).values())

    def release(self, reference: SchedulerReference | dict[str, str]) -> AllocationStatus:
        reference = SchedulerReference.model_validate(reference)
        self._require(reference)
        completed = self._run(["scancel", reference.reference])
        if completed.returncode == 0:
            getattr(self, "_allocations", {}).pop(reference.reference, None)
            return AllocationStatus.CANCELLED
        return AllocationStatus.FAILED

    def submit(self, request: ExecutionRequest) -> ExecutionHandle:
        if request.allocation is not None:
            self._require(request.allocation)
            # SLURM allocation references identify the parent allocation, but
            # an attached ``srun`` step has its own transient reference. Keep
            # the parent ID available to status/log consumers without
            # pretending it is a completed allocation job.
            command = ["srun", f"--jobid={request.allocation.reference}", *request.command]
        else:
            command = ["sbatch", "--parsable", "--wait", *request.command]
        completed = self._run(
            command,
            cwd=request.working_directory,
            env={**os.environ, **request.environment},
        )
        if completed.returncode != 0:
            raise RuntimeError("SLURM execution submission failed")
        reference = self._job_reference(completed.stdout or completed.stderr)
        if reference is None and request.allocation is not None:
            reference = request.allocation.reference
        if reference is None:
            reference = "local-execution"
        self._execution_logs[reference] = (completed.stdout or "", completed.stderr or "")
        self._execution_statuses[reference] = ExecutionStatus(
            status=AllocationStatus.COMPLETED,
            return_code=completed.returncode,
        )
        return ExecutionHandle(scheduler="slurm", reference=reference)

    def execution_status(self, handle: ExecutionHandle) -> ExecutionStatus:
        stored = self._execution_statuses.get(handle.reference)
        if stored is not None:
            return stored
        status = self.status(SchedulerReference(scheduler="slurm", reference=handle.reference))
        return ExecutionStatus(status=status)

    def collect_logs(
        self,
        handle: ExecutionHandle,
        *,
        stdout_path: str,
        stderr_path: str,
    ) -> None:
        """Write captured stdout and stderr to the requested files."""
        stdout, stderr = self._execution_logs.get(handle.reference, ("", ""))
        stdout_target = os.fspath(stdout_path)
        stderr_target = os.fspath(stderr_path)
        os.makedirs(os.path.dirname(stdout_target) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(stderr_target) or ".", exist_ok=True)
        with open(stdout_target, "w", encoding="utf-8") as output:
            output.write(stdout)
        with open(stderr_target, "w", encoding="utf-8") as error:
            error.write(stderr)

    def cancel(self, handle: ExecutionHandle) -> ExecutionStatus:
        status = self.release(SchedulerReference(scheduler="slurm", reference=handle.reference))
        return ExecutionStatus(status=status)

    def _run(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return self._runner(command, check=False, capture_output=True, text=True, **kwargs)

    @staticmethod
    def _job_reference(stdout: str) -> str | None:
        match = _JOB_ID.search(stdout.strip())
        return match.group(1) if match else None

    @staticmethod
    def _status(value: str) -> AllocationStatus:
        normalized = value.strip().upper().split()[0]
        if normalized in {"PENDING", "CONFIGURING"}:
            return AllocationStatus.PENDING
        if normalized in {"RUNNING", "COMPLETING"}:
            return AllocationStatus.RUNNING
        if normalized in {"COMPLETED"}:
            return AllocationStatus.COMPLETED
        if normalized in {"CANCELLED", "CANCELED"}:
            return AllocationStatus.CANCELLED
        if normalized in {"FAILED", "TIMEOUT", "OUT_OF_MEMORY"}:
            return AllocationStatus.FAILED
        return AllocationStatus.NOT_FOUND

    @staticmethod
    def _require(reference: SchedulerReference) -> None:
        if reference.scheduler != "slurm":
            raise ValueError("SLURM client requires a SLURM reference")


__all__ = ["SlurmClient"]
