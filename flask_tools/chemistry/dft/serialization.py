"""Serialization helpers for public DFT results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import DftError, DftResult


_PUBLIC_RESULT_FIELDS = (
    "status",
    "calculation_reference",
    "property_name",
    "value",
    "unit",
    "warnings",
    "error",
    "smiles",
    "canonical_smiles",
)


def serialize_error(error: DftError | None) -> dict[str, Any] | None:
    """Return only the error fields safe for the public API."""
    if error is None:
        return None
    return {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
    }


def serialize_result(result: DftResult | Mapping[str, Any]) -> dict[str, Any]:
    """Return only the fields allowed in a public DFT result."""
    normalized = DftResult.model_validate(result)
    payload: dict[str, Any] = {
        "status": normalized.status.value,
        "calculation_reference": (
            {"value": normalized.calculation_reference.value}
            if normalized.calculation_reference is not None
            else None
        ),
        "property_name": normalized.property_name,
        "value": normalized.value,
        "unit": normalized.unit,
        "warnings": list(normalized.warnings),
        "error": serialize_error(normalized.error),
        "smiles": normalized.smiles,
        "canonical_smiles": normalized.canonical_smiles,
    }
    return {key: payload[key] for key in _PUBLIC_RESULT_FIELDS}


__all__ = ["serialize_error", "serialize_result"]
