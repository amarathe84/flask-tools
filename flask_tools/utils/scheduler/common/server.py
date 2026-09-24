"""Generic lifecycle MCP registration for trusted scheduler clients."""

from __future__ import annotations

from typing import Any

from .protocols import SchedulerClient
from .models import AllocationRequest, SchedulerReference


def register_named_tool(server: Any, handler: Any, name: str) -> None:
    """Support FastMCP 3.x and the fake server used in tests."""
    try:
        server.add_tool(handler, name=name)
    except TypeError as exc:
        if "unexpected keyword argument 'name'" not in str(exc):
            raise
        server.add_tool(handler)


def register_scheduler_tools(server: Any, client: SchedulerClient) -> None:
    """Register lifecycle tools, but not unrestricted command execution."""

    def allocate_job(walltime_seconds: int | None = None, resource_count: int | None = None) -> dict[str, Any]:
        reference = client.allocate(
            AllocationRequest(
                walltime_seconds=walltime_seconds,
                resource_count=resource_count,
            )
        )
        return {"scheduler": reference.scheduler, "reference": reference.reference}

    def attach_job(scheduler: str, reference: str) -> dict[str, Any]:
        attached = client.attach(SchedulerReference(scheduler=scheduler, reference=reference))
        return {"scheduler": attached.scheduler, "reference": attached.reference}

    def release_job(scheduler: str, reference: str) -> str:
        return client.release(SchedulerReference(scheduler=scheduler, reference=reference)).value

    def get_status(scheduler: str, reference: str) -> str:
        return client.status(SchedulerReference(scheduler=scheduler, reference=reference)).value

    def list_resources() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in client.list_resources()]

    register_named_tool(server, allocate_job, "allocate_job")
    register_named_tool(server, attach_job, "attach_job")
    register_named_tool(server, release_job, "release_job")
    register_named_tool(server, get_status, "get_status")
    register_named_tool(server, list_resources, "list_resources")


__all__ = ["register_named_tool", "register_scheduler_tools"]
