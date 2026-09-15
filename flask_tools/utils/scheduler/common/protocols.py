"""Trusted generic scheduler client protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    AllocationRequest,
    AllocationStatus,
    ExecutionHandle,
    ExecutionRequest,
    ExecutionStatus,
    ResourceInfo,
    SchedulerReference,
)


@runtime_checkable
class SchedulerClient(Protocol):
    """Common lifecycle and execution methods for a scheduler client."""

    scheduler_name: str

    def allocate(self, request: AllocationRequest) -> SchedulerReference:
        """Create an allocation using the deployment's policy."""
        ...

    def attach(self, reference: SchedulerReference) -> SchedulerReference:
        """Validate and attach to an existing allocation."""
        ...

    def status(self, reference: SchedulerReference) -> AllocationStatus:
        """Return the allocation status."""
        ...

    def list_resources(self) -> list[ResourceInfo]:
        """Return available resource information."""
        ...

    def release(self, reference: SchedulerReference) -> AllocationStatus:
        """Release an allocation owned by the caller."""
        ...

    def submit(self, request: ExecutionRequest) -> ExecutionHandle:
        """Submit trusted execution input from the caller."""
        ...

    def execution_status(self, handle: ExecutionHandle) -> ExecutionStatus:
        """Return the status of a trusted execution."""
        ...

    def cancel(self, handle: ExecutionHandle) -> ExecutionStatus:
        """Cancel a trusted execution."""
        ...


__all__ = ["SchedulerClient"]
