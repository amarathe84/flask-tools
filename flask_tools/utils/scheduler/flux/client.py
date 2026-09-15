"""Flux scheduler client."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from ..common.models import (
    AllocationRequest,
    AllocationStatus,
    ExecutionHandle,
    ExecutionRequest,
    ExecutionStatus,
    ResourceInfo,
    SchedulerReference,
)


class FluxRuntimeUnavailableError(RuntimeError):
    """Raised when the optional Flux runtime is unavailable."""


class FluxClient:
    """Flux client with an injectable API for tests."""

    scheduler_name = "flux"

    def __init__(self, *, api: Any | None = None, uri: str | None = None) -> None:
        self._api = api
        self.uri = uri
        self._allocations: dict[str, SchedulerReference] = {}
        self._allocation_uris: dict[str, str | None] = {}
        self._execution_uris: dict[str, str | None] = {}

    def _runtime(self) -> Any:
        if self._api is not None:
            return self._api
        try:
            core = import_module("flux_mcp.job.core")
        except Exception as exc:  # pragma: no cover - environment dependent
            raise FluxRuntimeUnavailableError("Flux runtime is unavailable") from exc
        return core

    def allocate(self, request: AllocationRequest | dict[str, Any]) -> SchedulerReference:
        request = AllocationRequest.model_validate(request)
        api = self._runtime()
        command = ["sleep", str(request.walltime_seconds or 86400)]
        result = api.flux_submit_job(
            command=command,
            uri=self.uri,
            num_tasks=request.resource_count or 1,
            cores_per_task=1,
        )
        if not result.get("success"):
            raise RuntimeError("Flux allocation failed")
        reference = SchedulerReference(scheduler="flux", reference=str(result["job_id"]))
        self._allocations[reference.reference] = reference
        self._allocation_uris[reference.reference] = (
            result.get("flux_uri")
            or (result.get("info") or {}).get("uri")
            or (result.get("info") or {}).get("flux_uri")
            or self.uri
        )
        return reference

    def attach(self, reference: SchedulerReference | dict[str, str]) -> SchedulerReference:
        reference = SchedulerReference.model_validate(reference)
        self._require(reference)
        uri = self._allocation_uris.get(reference.reference, self.uri)
        info = self._runtime().flux_get_job_info(int(reference.reference), uri)
        if not info.get("success", True) or not info.get("info"):
            raise RuntimeError("Flux allocation is not available")
        allocations = getattr(self, "_allocations", None)
        if allocations is not None:
            allocations[reference.reference] = reference
        allocation_uris = getattr(self, "_allocation_uris", None)
        if allocation_uris is not None:
            allocation_uris[reference.reference] = (
            (info.get("info") or {}).get("flux_uri")
            or (info.get("info") or {}).get("uri")
            or self.uri
            )
        return reference

    def status(self, reference: SchedulerReference | dict[str, str]) -> AllocationStatus:
        reference = SchedulerReference.model_validate(reference)
        self._require(reference)
        uri = getattr(self, "_allocation_uris", {}).get(reference.reference, self.uri)
        info = self._runtime().flux_get_job_info(int(reference.reference), uri).get("info") or {}
        state = str(info.get("state", "")).upper()
        if state in {"NEW", "DEPEND", "SCHED", "PRIORITY"}:
            return AllocationStatus.PENDING
        if state in {"RUN", "RUNNING"}:
            return AllocationStatus.RUNNING
        if state in {"CANCELLED", "CANCELED"}:
            return AllocationStatus.CANCELLED
        if state in {"DONE", "INACTIVE"}:
            return AllocationStatus.COMPLETED if info.get("returncode", 0) == 0 else AllocationStatus.FAILED
        return AllocationStatus.NOT_FOUND

    def list_resources(self) -> list[ResourceInfo]:
        result = self._runtime().flux_resource_list(self.uri)
        if isinstance(result, dict):
            raw = result.get("resources") or result.get("R") or []
        else:
            raw = result or []
        return [
            ResourceInfo(name=str(item.get("name", item.get("type", "resource"))), available=item.get("count"), unit="units")
            for item in raw
            if isinstance(item, dict)
        ]

    def list_jobs(self) -> list[dict[str, Any]]:
        api = self._runtime()
        if hasattr(api, "flux_list_jobs"):
            result = api.flux_list_jobs(uri=self.uri)
            return result.get("jobs", result) if isinstance(result, dict) else result
        return []

    def get_cluster_info(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.list_resources()]

    def list_allocations(self) -> list[SchedulerReference]:
        return list(getattr(self, "_allocations", {}).values())

    def release(self, reference: SchedulerReference | dict[str, str]) -> AllocationStatus:
        reference = SchedulerReference.model_validate(reference)
        self._require(reference)
        uri = getattr(self, "_allocation_uris", {}).get(reference.reference, self.uri)
        result = self._runtime().flux_cancel_job(int(reference.reference), uri)
        if result.get("success"):
            getattr(self, "_allocations", {}).pop(reference.reference, None)
            getattr(self, "_allocation_uris", {}).pop(reference.reference, None)
            return AllocationStatus.CANCELLED
        return AllocationStatus.FAILED

    def submit(self, request: ExecutionRequest) -> ExecutionHandle:
        if request.allocation is not None:
            self._require(request.allocation)
        api = self._runtime()
        effective_uri = self._uri_for_allocation(request.allocation) if request.allocation else self.uri
        result = api.flux_submit_job(
            command=list(request.command),
            uri=effective_uri,
            num_tasks=request.resource_count or 1,
            cores_per_task=1,
            duration=request.timeout_seconds,
            cwd=request.working_directory,
            environment=dict(request.environment) if request.environment else None,
        )
        if not result.get("success"):
            raise RuntimeError(
                f"Flux execution submission failed: {result.get('error') or 'unknown error'}"
            )
        handle = ExecutionHandle(scheduler="flux", reference=str(result["job_id"]))
        self._execution_uris[handle.reference] = effective_uri
        return handle

    def _uri_for_allocation(self, allocation: SchedulerReference) -> str:
        """Find the Flux URI associated with an allocation."""
        return getattr(self, "_allocation_uris", {}).get(allocation.reference) or allocation.reference

    def execution_status(self, handle: ExecutionHandle) -> ExecutionStatus:
        return self._execution_status(handle)

    def cancel(self, handle: ExecutionHandle) -> ExecutionStatus:
        uri = self._execution_uris.get(handle.reference, self.uri)
        return ExecutionStatus(
            status=self._release_with_uri(handle.reference, uri)
        )

    def collect_logs(
        self,
        handle: ExecutionHandle,
        *,
        stdout_path: str,
        stderr_path: str,
    ) -> None:
        """Write captured execution logs to the requested files."""
        api = self._runtime()
        uri = self._execution_uris.get(handle.reference, self.uri)
        get_logs = getattr(api, "flux_get_job_logs", None)
        if get_logs is None:
            raise RuntimeError("Flux log retrieval is unavailable")
        response = get_logs(int(handle.reference), uri)
        lines = response.get("lines") or []
        Path(stdout_path).parent.mkdir(parents=True, exist_ok=True)
        with open(stdout_path, "w", encoding="utf-8") as stdout:
            stdout.write("".join(str(line) for line in lines))
        error = "" if response.get("success", True) else str(response.get("error") or "")
        Path(stderr_path).parent.mkdir(parents=True, exist_ok=True)
        with open(stderr_path, "w", encoding="utf-8") as stderr:
            stderr.write(error)

    def _execution_status(self, handle: ExecutionHandle) -> ExecutionStatus:
        uri = self._execution_uris.get(handle.reference, self.uri)
        info_response = self._runtime().flux_get_job_info(int(handle.reference), uri)
        info = info_response.get("info") or {}
        state = str(info.get("state", "")).upper()
        if state in {"NEW", "DEPEND", "SCHED", "PRIORITY"}:
            status = AllocationStatus.PENDING
        elif state in {"RUN", "RUNNING"}:
            status = AllocationStatus.RUNNING
        elif state in {"CANCELLED", "CANCELED"}:
            status = AllocationStatus.CANCELLED
        elif state in {"DONE", "INACTIVE"}:
            status = (
                AllocationStatus.COMPLETED
                if info.get("returncode", 0) == 0
                else AllocationStatus.FAILED
            )
        else:
            status = AllocationStatus.NOT_FOUND
        return ExecutionStatus(
            status=status,
            return_code=self._return_code(info.get("returncode")),
            error_code=None if info_response.get("success", True) else str(info_response.get("error") or "unknown error"),
        )

    @staticmethod
    def _return_code(value: Any) -> int | None:
        """Treat Flux's empty in-progress return code as ``None``."""
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _release_with_uri(self, reference: str, uri: str | None) -> AllocationStatus:
        result = self._runtime().flux_cancel_job(int(reference), uri)
        return AllocationStatus.CANCELLED if result.get("success") else AllocationStatus.FAILED

    @staticmethod
    def _require(reference: SchedulerReference) -> None:
        if reference.scheduler != "flux":
            raise ValueError("Flux client requires a Flux reference")


__all__ = ["FluxClient", "FluxRuntimeUnavailableError"]
