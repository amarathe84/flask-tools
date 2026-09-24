"""Register the public DFT tools with an MCP server."""

from __future__ import annotations

from typing import Any

from .dft.protocols import DftProvider
from .dft.serialization import serialize_result
from .dft.service import DftService


def _add_named_tool(server: Any, handler: Any, name: str) -> None:
    """Support FastMCP 3.x and the small fake server used in tests."""
    try:
        server.add_tool(handler, name=name)
    except TypeError as exc:
        if "unexpected keyword argument 'name'" not in str(exc):
            raise
        server.add_tool(handler)


def register_dft_tools(server: Any, service: DftService) -> None:
    """Add the two public DFT tools to an existing server."""

    def calculate_dft(
        smiles: str,
        property_name: str,
        functional_id: str | None = None,
        basis_set: str | None = None,
        mpi_ranks: int = 1,
        temperature_kelvin: float = 298.15,
        pressure_atm: float = 1.0,
        execution_target: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Calculate a DFT property through the supplied provider."""
        payload: dict[str, Any] = {
            "smiles": smiles,
            "property_name": property_name,
            "mpi_ranks": mpi_ranks,
            "temperature_kelvin": temperature_kelvin,
            "pressure_atm": pressure_atm,
            "execution_target": execution_target,
        }
        # Keep omitted optional values omitted. Providers may use that
        # distinction when applying their own defaults.
        if functional_id is not None:
            payload["functional_id"] = functional_id
        if basis_set is not None:
            payload["basis_set"] = basis_set
        result = service.calculate(payload)
        return serialize_result(result)

    def inspect_dft_property_calculation(
        calculation_reference: str,
        property_name: str | None = None,
        wait_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Inspect a DFT calculation by its opaque reference.

        When supplied, ``wait_seconds`` asks the provider to poll an
        in-flight calculation for up to that bounded interval. A result is
        returned immediately when the calculation reaches a terminal state.
        """
        result = service.inspect(
            calculation_reference,
            property_name=property_name,
            wait_seconds=wait_seconds,
        )
        return serialize_result(result)

    _add_named_tool(server, calculate_dft, "calculate_dft")
    _add_named_tool(
        server,
        inspect_dft_property_calculation,
        "inspect_dft_property_calculation",
    )


def build_dft_mcp_server(provider: DftProvider, *, name: str = "dft") -> Any:
    """Build a DFT MCP server using the supplied provider."""
    from fastmcp import FastMCP

    server = FastMCP(
        name,
        instructions=(
            "Expose backend-neutral DFT calculation and inspection tools. "
            "The runtime provider is supplied by the deployment."
        ),
    )
    register_dft_tools(server, DftService(provider))
    return server


__all__ = ["build_dft_mcp_server", "register_dft_tools"]
