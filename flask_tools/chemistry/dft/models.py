"""Public DFT request and result models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from .properties import normalize_property_name


class DftModel(BaseModel):
    """Base class that rejects fields outside the public schema."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DftStatus(str, Enum):
    """Status values returned by a DFT provider."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class CalculationReference(DftModel):
    """Opaque reference that the provider owns and interprets."""

    value: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize(self) -> "CalculationReference":
        value = self.value.strip()
        if not value:
            raise ValueError("calculation reference must not be blank")
        object.__setattr__(self, "value", value)
        return self


class ExecutionTarget(DftModel):
    """Scheduler and reference for an execution, without launch details."""

    scheduler: str = Field(min_length=1)
    reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize(self) -> "ExecutionTarget":
        scheduler = self.scheduler.strip().lower()
        reference = self.reference.strip()
        if not scheduler:
            raise ValueError("scheduler must not be blank")
        if not reference:
            raise ValueError("execution reference must not be blank")
        object.__setattr__(self, "scheduler", scheduler)
        object.__setattr__(self, "reference", reference)
        return self


class DftRequest(DftModel):
    """Scientific request passed to a DFT provider."""

    smiles: str = Field(
        min_length=1,
        validation_alias=AliasChoices("smiles", "SMILES_string"),
    )
    property_name: str = Field(
        min_length=1,
        validation_alias=AliasChoices("property_name", "property", "prop"),
    )
    functional_id: str = Field(
        default="B3LYP",
        validation_alias=AliasChoices("functional_id", "functional"),
    )
    basis_set: str | None = Field(
        default=None,
        validation_alias=AliasChoices("basis_set", "basis"),
    )
    mpi_ranks: int = Field(
        default=1,
        ge=1,
        description=(
            "mpi_ranks is the application's requested parallelism. The provider "
            "decides how it maps to scheduler resources."
        ),
    )
    temperature_kelvin: float = Field(default=298.15, gt=0)
    pressure_atm: float = Field(default=1.0, gt=0)
    execution_target: ExecutionTarget | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_conflicting_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        alias_groups = (
            ("smiles", "SMILES_string"),
            ("property_name", "property", "prop"),
            ("functional_id", "functional"),
            ("basis_set", "basis"),
        )
        for names in alias_groups:
            supplied = [
                (name, value[name])
                for name in names
                if name in value and value[name] is not None
            ]
            if len(supplied) > 1 and any(
                item[1] != supplied[0][1] for item in supplied[1:]
            ):
                raise ValueError(
                    f"Conflicting aliases supplied: {', '.join(name for name, _ in supplied)}"
                )
        return value

    @model_validator(mode="after")
    def normalize(self) -> "DftRequest":
        smiles = self.smiles.strip()
        functional_id = self.functional_id.strip()
        basis_set = self.basis_set.strip() if self.basis_set is not None else None
        if not smiles:
            raise ValueError("smiles must not be blank")
        if not functional_id:
            raise ValueError("functional_id must not be blank")
        if basis_set == "":
            basis_set = None

        object.__setattr__(self, "smiles", smiles)
        object.__setattr__(self, "property_name", normalize_property_name(self.property_name))
        object.__setattr__(self, "functional_id", functional_id)
        object.__setattr__(self, "basis_set", basis_set)
        return self


class DftError(DftModel):
    """Safe error details that can be returned to the caller."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "DftError":
        code = self.code.strip()
        message = self.message.strip()
        if not code:
            raise ValueError("error code must not be blank")
        if not message:
            raise ValueError("error message must not be blank")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        return self


class DftResult(DftModel):
    """Result returned by a DFT provider."""

    status: DftStatus
    calculation_reference: CalculationReference | None = None
    property_name: str
    value: float | list[float] | None = None
    unit: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: DftError | None = None
    smiles: str | None = None
    canonical_smiles: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "DftResult":
        if self.status in {DftStatus.ACCEPTED, DftStatus.RUNNING}:
            if self.calculation_reference is None:
                raise ValueError(
                    f"{self.status.value} results require a calculation reference"
                )
        if self.status in {
            DftStatus.FAILED,
            DftStatus.REJECTED,
            DftStatus.UNAVAILABLE,
        }:
            if self.error is None:
                raise ValueError(
                    f"{self.status.value} results require a sanitized error"
                )
        object.__setattr__(self, "property_name", normalize_property_name(self.property_name))
        if self.smiles is not None:
            object.__setattr__(self, "smiles", self.smiles.strip() or None)
        if self.canonical_smiles is not None:
            object.__setattr__(
                self,
                "canonical_smiles",
                self.canonical_smiles.strip() or None,
            )
        return self


__all__ = [
    "CalculationReference",
    "DftError",
    "DftModel",
    "DftRequest",
    "DftResult",
    "DftStatus",
    "ExecutionTarget",
]
