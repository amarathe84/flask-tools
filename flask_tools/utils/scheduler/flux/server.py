"""Build and register the Flux lifecycle MCP server."""

from __future__ import annotations

from typing import Any

from ..common.server import register_named_tool
from .client import FluxClient


def register_flux_tools(server: Any, client: FluxClient) -> None:
    """Register the Flux lifecycle tools."""

    def create_allocation(walltime_seconds: int | None = None, resource_count: int | None = None) -> dict[str, str]:
        return client.allocate({"walltime_seconds": walltime_seconds, "resource_count": resource_count}).model_dump(mode="json")

    def attach_allocation(reference: str) -> dict[str, str]:
        return client.attach({"scheduler": "flux", "reference": reference}).model_dump(mode="json")

    def release_allocation(reference: str) -> str:
        return client.release({"scheduler": "flux", "reference": reference}).value

    def list_allocations() -> list[dict[str, str]]:
        return [item.model_dump(mode="json") for item in client.list_allocations()]

    def list_resources() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in client.list_resources()]

    def list_jobs() -> list[dict[str, Any]]:
        return client.list_jobs()

    def get_cluster_info() -> list[dict[str, Any]]:
        return client.get_cluster_info()

    register_named_tool(server, create_allocation, "create_allocation")
    register_named_tool(server, attach_allocation, "attach_allocation")
    register_named_tool(server, release_allocation, "release_allocation")
    register_named_tool(server, list_allocations, "list_allocations")
    register_named_tool(server, list_resources, "list_resources")
    register_named_tool(server, list_jobs, "list_jobs")
    register_named_tool(server, get_cluster_info, "get_cluster_info")


def build_flux_mcp_server(*, client: FluxClient | None = None, name: str = "flux") -> Any:
    from fastmcp import FastMCP

    server = FastMCP(name, instructions="Generic Flux allocation lifecycle tools.")
    register_flux_tools(server, client or FluxClient())
    return server


__all__ = ["build_flux_mcp_server", "register_flux_tools"]
