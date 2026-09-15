"""Tests for scheduler clients using fake runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask_tools.utils.scheduler.common import register_scheduler_tools
from flask_tools.utils.scheduler.common.models import (
    AllocationRequest,
    AllocationStatus,
    ExecutionRequest,
    ExecutionStatus,
    SchedulerReference,
)
from flask_tools.utils.scheduler.flux import FluxClient
from flask_tools.utils.scheduler.flux.server import register_flux_tools
from flask_tools.utils.scheduler.slurm import SlurmClient
from flask_tools.utils.scheduler.slurm.server import register_slurm_tools


@dataclass
class Completed:
    returncode: int = 0
    stdout: str = "12345\n"
    stderr: str = ""


class FakeServer:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def add_tool(self, handler: object, *, name: str) -> None:
        self.tools[name] = handler


def test_slurm_client_parses_allocation_id_from_stderr_and_uses_injected_runner() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: Any) -> Completed:
        calls.append(command)
        return Completed(stdout="", stderr="salloc: Granted job allocation 2468\n")

    client = SlurmClient(runner=runner)
    reference = client.allocate({"walltime_seconds": 30, "resource_count": 1})
    assert reference == SchedulerReference(scheduler="slurm", reference="2468")
    assert calls == [["salloc", "--no-shell", "--time", "30", "--ntasks", "1"]]


def test_scheduler_specific_mcp_registration_uses_actual_tool_names() -> None:
    slurm = FakeServer()
    flux = FakeServer()
    register_slurm_tools(slurm, SlurmClient(runner=lambda *args, **kwargs: Completed()))
    register_flux_tools(flux, FluxClient(api=object()))
    assert set(slurm.tools) == {
        "allocate_job", "attach_job", "release_job", "list_allocations", "list_queue", "get_cluster_info"
    }
    assert set(flux.tools) == {
        "create_allocation", "attach_allocation", "release_allocation", "list_allocations",
        "list_resources", "list_jobs", "get_cluster_info"
    }
    assert "run_command" not in slurm.tools
    assert "run_command" not in flux.tools


def test_slurm_client_uses_generic_commands_without_chemistry_defaults() -> None:
    calls: list[list[str]] = []
    kwargs_by_command: dict[str, dict[str, Any]] = {}

    def runner(command: list[str], **kwargs: Any) -> Completed:
        calls.append(command)
        kwargs_by_command[command[0]] = kwargs
        if command[0] == "squeue":
            return Completed(stdout="12345 RUNNING\n")
        if command[0] == "sinfo":
            return Completed(stdout="general|up|4\n")
        return Completed()

    client = SlurmClient(runner=runner)
    reference = client.allocate(AllocationRequest(walltime_seconds=60, resource_count=2))
    assert reference == SchedulerReference(scheduler="slurm", reference="12345")
    assert [item.reference for item in client.list_allocations()] == ["12345"]
    assert client.attach({"scheduler": "slurm", "reference": "12345"}) == reference
    handle = client.submit(
        ExecutionRequest(
            command=("trusted-app", "input.dat"),
            allocation=reference,
            working_directory="/private/run",
            environment={"APP_FLAG": "1"},
        )
    )
    assert handle.scheduler == "slurm"
    assert handle.reference == "12345"
    assert ["srun", "--jobid=12345", "trusted-app", "input.dat"] in calls
    assert all("NWChem" not in item and "ORCA" not in item for call in calls for item in call)
    assert all("module" not in item for call in calls for item in call)
    assert kwargs_by_command["srun"]["cwd"] == "/private/run"
    assert kwargs_by_command["srun"]["env"]["APP_FLAG"] == "1"
    assert client.execution_status(handle).status is AllocationStatus.COMPLETED
    client.collect_logs(handle, stdout_path="/tmp/public-slurm-test.out", stderr_path="/tmp/public-slurm-test.err")
    assert client.release(reference) is AllocationStatus.CANCELLED
    assert client.list_allocations() == []


def test_flux_client_translates_generic_requests_and_states() -> None:
    calls: list[tuple[str, Any]] = []

    class FakeFlux:
        def flux_submit_job(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(("submit", kwargs))
            return {"success": True, "job_id": 77}

        def flux_get_job_info(self, job_id: int, uri: str | None) -> dict[str, Any]:
            calls.append(("info", (job_id, uri)))
            return {"success": True, "info": {"state": "RUN", "returncode": ""}}

        def flux_cancel_job(self, job_id: int, uri: str | None) -> dict[str, Any]:
            calls.append(("cancel", (job_id, uri)))
            return {"success": True}

        def flux_get_job_logs(self, job_id: int, uri: str | None) -> dict[str, Any]:
            calls.append(("logs", (job_id, uri)))
            return {"success": True, "lines": ["output\n"]}

        def flux_resource_list(self, uri: str | None) -> list[dict[str, Any]]:
            calls.append(("resources", uri))
            return [{"name": "cpu", "count": 8}]

        def flux_list_jobs(self, *, uri: str | None) -> list[dict[str, Any]]:
            calls.append(("jobs", uri))
            return []

    client = FluxClient(api=FakeFlux(), uri="flux://alloc")
    reference = client.allocate(AllocationRequest(resource_count=2))
    assert reference.scheduler == "flux"
    assert [item.reference for item in client.list_allocations()] == [reference.reference]
    assert client.attach({"scheduler": "flux", "reference": reference.reference}) == reference
    handle = client.submit(
        ExecutionRequest(
            command=("trusted-app",),
            allocation=reference,
            working_directory="/private/run",
            environment={"APP_FLAG": "1"},
            resource_count=3,
        )
    )
    assert handle.reference == "77"
    assert client.execution_status(handle).status is AllocationStatus.RUNNING
    assert client.cancel(handle).status is AllocationStatus.CANCELLED
    assert ("cancel", (77, "flux://alloc")) in calls
    assert ("info", (77, "flux://alloc")) in calls
    client.collect_logs(handle, stdout_path="/tmp/public-flux-test.out", stderr_path="/tmp/public-flux-test.err")
    assert ("logs", (77, "flux://alloc")) in calls
    assert client.list_resources()[0].name == "cpu"
    assert client.list_jobs() == []
    assert ("jobs", "flux://alloc") in calls
    assert client.get_cluster_info()[0]["name"] == "cpu"
    submit_kwargs = next(
        kwargs
        for kind, kwargs in calls
        if kind == "submit" and kwargs["command"] == ["trusted-app"]
    )
    assert submit_kwargs["command"] == ["trusted-app"]
    assert submit_kwargs["cwd"] == "/private/run"
    assert submit_kwargs["environment"] == {"APP_FLAG": "1"}
    assert "NWChem" not in repr(submit_kwargs)
    assert "ORCA" not in repr(submit_kwargs)


def test_default_scheduler_mcp_excludes_unrestricted_run_command() -> None:
    class FakeClient:
        scheduler_name = "fake"

        def allocate(self, request: Any) -> SchedulerReference:
            return SchedulerReference(scheduler="fake", reference="a")

        def attach(self, reference: SchedulerReference) -> SchedulerReference:
            return reference

        def status(self, reference: SchedulerReference) -> AllocationStatus:
            return AllocationStatus.RUNNING

        def list_resources(self) -> list[Any]:
            return []

        def release(self, reference: SchedulerReference) -> AllocationStatus:
            return AllocationStatus.CANCELLED

        def submit(self, request: Any) -> Any:
            raise AssertionError("default scheduler MCP must not expose execution")

        def execution_status(self, handle: Any) -> ExecutionStatus:
            raise AssertionError

        def cancel(self, handle: Any) -> ExecutionStatus:
            raise AssertionError

    server = FakeServer()
    register_scheduler_tools(server, FakeClient())
    assert "run_command" not in server.tools
    assert {"allocate_job", "attach_job", "release_job", "get_status", "list_resources"} <= set(server.tools)


def test_scheduler_specific_mcp_surfaces_are_distinct_and_safe() -> None:
    class SlurmFake(SlurmClient):
        def __init__(self) -> None:
            pass

        def allocate(self, request: Any) -> Any:
            return SchedulerReference(scheduler="slurm", reference="1")

        def attach(self, reference: Any) -> Any:
            return SchedulerReference(scheduler="slurm", reference="1")

        def release(self, reference: Any) -> AllocationStatus:
            return AllocationStatus.CANCELLED

        def list_allocations(self) -> list[SchedulerReference]:
            return []

        def list_queue(self) -> list[dict[str, str]]:
            return []

        def get_cluster_info(self) -> list[dict[str, str]]:
            return []

    class FluxFake(FluxClient):
        def __init__(self) -> None:
            pass

        def allocate(self, request: Any) -> Any:
            return SchedulerReference(scheduler="flux", reference="2")

        def attach(self, reference: Any) -> Any:
            return SchedulerReference(scheduler="flux", reference="2")

        def release(self, reference: Any) -> AllocationStatus:
            return AllocationStatus.CANCELLED

        def list_allocations(self) -> list[SchedulerReference]:
            return []

        def list_resources(self) -> list[Any]:
            return []

        def list_jobs(self) -> list[dict[str, Any]]:
            return []

        def get_cluster_info(self) -> list[dict[str, Any]]:
            return []

    slurm = FakeServer()
    flux = FakeServer()
    register_slurm_tools(slurm, SlurmFake())
    register_flux_tools(flux, FluxFake())
    assert set(slurm.tools) == {
        "allocate_job", "attach_job", "release_job", "list_allocations", "list_queue", "get_cluster_info"
    }
    assert set(flux.tools) == {
        "create_allocation", "attach_allocation", "release_allocation", "list_allocations", "list_resources", "list_jobs", "get_cluster_info"
    }
    assert "run_command" not in slurm.tools
    assert "run_command" not in flux.tools
