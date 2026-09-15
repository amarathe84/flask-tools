"""Service that validates requests before calling a DFT provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CalculationReference, DftRequest, DftResult
from .protocols import DftProvider
from .properties import normalize_property_name
from .validation import normalize_reference, normalize_request


class DftService:
    """Validate requests and pass them to the supplied provider."""

    def __init__(self, provider: DftProvider) -> None:
        self._provider = provider

    def calculate(self, request: DftRequest | Mapping[str, Any]) -> DftResult:
        """Validate a request and pass it to the provider."""
        normalized = normalize_request(request)
        return DftResult.model_validate(self._provider.calculate(normalized))

    def inspect(
        self,
        reference: CalculationReference | str,
        *,
        property_name: str | None = None,
    ) -> DftResult:
        """Inspect a calculation through its opaque reference."""
        normalized_property = (
            normalize_property_name(property_name) if property_name is not None else None
        )
        result = self._provider.inspect(
            normalize_reference(reference),
            property_name=normalized_property,
        )
        return DftResult.model_validate(result)


__all__ = ["DftService"]
