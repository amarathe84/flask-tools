"""Tests for the DFT contract and MCP registration."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from flask_tools.chemistry.dft import (
    CalculationReference,
    DftError,
    DftRequest,
    DftResult,
    DftService,
    DftStatus,
    ExecutionTarget,
    serialize_result,
)
from flask_tools.chemistry.dft_tool_server import register_dft_tools
from flask_tools.utils.scheduler import ExecutionRequest


class FakeProvider:
    def calculate(self, request: DftRequest) -> DftResult:
        return DftResult(
            status=DftStatus.COMPLETED,
            calculation_reference=CalculationReference(value="opaque-calc"),
            property_name=request.property_name,
            value=-75.2,
            unit="hartree",
        )

    def inspect(
        self,
        reference: CalculationReference,
        *,
        property_name: str | None = None,
    ) -> DftResult:
        return DftResult(
            status=DftStatus.RUNNING,
            calculation_reference=reference,
            property_name=property_name or "energy",
        )


class RecordingServer:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def add_tool(self, handler: object, *, name: str) -> None:
        self.tools[name] = handler


def test_contract_normalizes_request_and_opaque_target() -> None:
    request = DftRequest(
        SMILES_string=" CCO ",
        prop="hf_energy",
        functional=" B3LYP ",
        basis=" 6-31G** ",
        mpi_ranks=4,
        execution_target={"scheduler": " SLURM ", "reference": " alloc-1 "},
    )
    assert request.smiles == "CCO"
    assert request.property_name == "energy"
    assert request.execution_target == ExecutionTarget(
        scheduler="slurm", reference="alloc-1"
    )


def test_contract_rejects_invalid_and_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        DftRequest(smiles="CCO", property_name="energy", mpi_ranks=0)
    with pytest.raises(ValidationError):
        ExecutionTarget(scheduler="slurm", reference="alloc", command="srun")
    with pytest.raises(ValidationError):
        DftResult(status="completed", property_name="energy", run_directory="/tmp")


def test_result_state_requirements_are_public_and_sanitized() -> None:
    with pytest.raises(ValidationError):
        DftResult(status="running", property_name="energy")
    with pytest.raises(ValidationError):
        DftResult(status="failed", property_name="energy")

    result = DftResult(
        status="failed",
        property_name="energy",
        error={"code": "provider_failure", "message": "safe message"},
    )
    payload = serialize_result(result)
    assert payload["error"] == {
        "code": "provider_failure",
        "message": "safe message",
        "retryable": False,
    }
    assert set(payload) == {
        "status",
        "calculation_reference",
        "property_name",
        "value",
        "unit",
        "warnings",
        "error",
        "smiles",
        "canonical_smiles",
    }


def test_service_uses_fake_provider_for_calculate_and_inspect() -> None:
    service = DftService(FakeProvider())
    completed = service.calculate({"smiles": "CCO", "property": "energy"})
    running = service.inspect("opaque-calc", property_name="freq")
    assert completed.status is DftStatus.COMPLETED
    assert running.status is DftStatus.RUNNING
    assert running.property_name == "frequency"


def test_public_mcp_registers_exactly_two_tools() -> None:
    server = RecordingServer()
    register_dft_tools(server, DftService(FakeProvider()))
    assert set(server.tools) == {
        "calculate_dft",
        "inspect_dft_property_calculation",
    }
    calculate = server.tools["calculate_dft"]
    inspect = server.tools["inspect_dft_property_calculation"]
    assert calculate("CCO", "energy")["status"] == "completed"
    assert inspect("opaque-calc")["status"] == "running"


def test_public_sources_have_no_private_or_scheduler_runtime_imports() -> None:
    package_root = Path(__file__).parents[1] / "flask_tools"
    forbidden_prefixes = (
        "nwchem_adapter",
        "private_runtime",
        "mada_tools",
        "slurm",
        "flux",
    )
    for source_path in package_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            assert all(not name.startswith(forbidden_prefixes) for name in imported), source_path


def test_trusted_scheduler_input_is_not_a_public_result_shape() -> None:
    request = ExecutionRequest(
        command=("private-provider-command", "input.dat"),
        working_directory="private-run",
        environment={"PRIVATE_SETTING": "private-value"},
    )
    assert request.command == ("private-provider-command", "input.dat")
    assert "command" not in DftResult.model_fields
    assert "environment" not in DftResult.model_fields
