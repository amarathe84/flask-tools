"""Build and register the SLURM lifecycle MCP server."""

from __future__ import annotations

from typing import Any

from ..common.server import register_named_tool
from .client import SlurmClient


def register_slurm_tools(server: Any, client: SlurmClient) -> None:
    """Register the SLURM lifecycle tools."""

    def allocate_job(walltime_seconds: int | None = None, resource_count: int | None = None) -> dict[str, str]:
        return client.allocate({"walltime_seconds": walltime_seconds, "resource_count": resource_count}).model_dump(mode="json")

    def attach_job(reference: str) -> dict[str, str]:
        return client.attach({"scheduler": "slurm", "reference": reference}).model_dump(mode="json")

    def release_job(reference: str) -> str:
        return client.release({"scheduler": "slurm", "reference": reference}).value

    def list_allocations() -> list[dict[str, str]]:
        return [item.model_dump(mode="json") for item in client.list_allocations()]

    def list_queue() -> list[dict[str, str]]:
        return client.list_queue()

    def get_cluster_info() -> list[dict[str, Any]]:
        return client.get_cluster_info()

    register_named_tool(server, allocate_job, "allocate_job")
    register_named_tool(server, attach_job, "attach_job")
    register_named_tool(server, release_job, "release_job")
    register_named_tool(server, list_allocations, "list_allocations")
    register_named_tool(server, list_queue, "list_queue")
    register_named_tool(server, get_cluster_info, "get_cluster_info")


def build_slurm_mcp_server(*, client: SlurmClient | None = None, name: str = "slurm") -> Any:
    from fastmcp import FastMCP

    server = FastMCP(name, instructions="Generic SLURM allocation lifecycle tools.")
    register_slurm_tools(server, client or SlurmClient())
    return server


__all__ = ["build_slurm_mcp_server", "register_slurm_tools"]
