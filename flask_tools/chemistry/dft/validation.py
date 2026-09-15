"""Helpers for validating DFT requests and references."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CalculationReference, DftRequest


def normalize_request(payload: DftRequest | Mapping[str, Any]) -> DftRequest:
    """Validate a request and return the model used by providers."""
    if isinstance(payload, DftRequest):
        return payload
    return DftRequest.model_validate(payload)


def normalize_reference(reference: CalculationReference | str) -> CalculationReference:
    """Wrap a reference without interpreting its contents."""
    if isinstance(reference, CalculationReference):
        return reference
    return CalculationReference(value=reference)


__all__ = ["normalize_reference", "normalize_request"]
