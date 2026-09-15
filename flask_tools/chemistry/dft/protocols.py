"""Interface that DFT providers implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import CalculationReference, DftRequest, DftResult


@runtime_checkable
class DftProvider(Protocol):
    """Interface for a provider supplied by the application."""

    def calculate(self, request: DftRequest) -> DftResult:
        """Calculate or submit a request."""
        ...

    def inspect(
        self,
        reference: CalculationReference,
        *,
        property_name: str | None = None,
    ) -> DftResult:
        """Inspect a calculation using its opaque reference."""
        ...


__all__ = ["DftProvider"]
