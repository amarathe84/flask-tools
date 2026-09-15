"""Generic scheduler data models without application launch policy."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SchedulerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AllocationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"


class SchedulerReference(SchedulerModel):
    scheduler: str = Field(min_length=1)
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize(self) -> "SchedulerReference":
        scheduler = self.scheduler.strip().lower()
        reference = self.reference.strip()
        if not scheduler or not reference:
            raise ValueError("scheduler and reference must not be blank")
        object.__setattr__(self, "scheduler", scheduler)
        object.__setattr__(self, "reference", reference)
        return self


class AllocationRequest(SchedulerModel):
    """Basic allocation request; deployments add their own policy."""

    walltime_seconds: int | None = Field(default=None, ge=1)
    resource_count: int | None = Field(default=None, ge=1)


class ResourceInfo(SchedulerModel):
    name: str = Field(min_length=1)
    available: int | float | None = None
    unit: str | None = None


class ExecutionRequest(SchedulerModel):
    """Execution input supplied by a trusted application provider.

    These fields are for scheduler clients and are not part of the normal
    lifecycle MCP response. The caller owns application and site policy.
    """

    command: tuple[str, ...] = Field(min_length=1)
    allocation: SchedulerReference | None = None
    working_directory: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    resource_count: int | None = Field(default=None, ge=1)
    timeout_seconds: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_command(self) -> "ExecutionRequest":
        if any(not item.strip() for item in self.command):
            raise ValueError("command entries must not be blank")
        if self.working_directory is not None and not self.working_directory.strip():
            raise ValueError("working_directory must not be blank when provided")
        return self


class ExecutionHandle(SchedulerModel):
    """Opaque handle for a scheduler execution."""

    scheduler: str = Field(min_length=1)
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize(self) -> "ExecutionHandle":
        scheduler = self.scheduler.strip().lower()
        reference = self.reference.strip()
        if not scheduler or not reference:
            raise ValueError("scheduler and reference must not be blank")
        object.__setattr__(self, "scheduler", scheduler)
        object.__setattr__(self, "reference", reference)
        return self


class ExecutionStatus(SchedulerModel):
    """Status returned by the execution interface."""

    status: AllocationStatus
    return_code: int | None = None
    error_code: str | None = None


__all__ = [
    "AllocationRequest",
    "AllocationStatus",
    "ExecutionHandle",
    "ExecutionRequest",
    "ExecutionStatus",
    "ResourceInfo",
    "SchedulerReference",
]
