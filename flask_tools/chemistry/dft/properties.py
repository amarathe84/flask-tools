"""DFT property names and their common aliases."""

from __future__ import annotations

from enum import Enum


class CalculatedProperty(str, Enum):
    """Properties supported by the public DFT contract."""

    ENERGY = "energy"
    FREQUENCY = "frequency"
    ELECTROSTATIC_POTENTIAL = "electrostatic_potential"
    ELECTRON_DENSITY = "electron_density"
    HEAT_OF_FORMATION = "heat_of_formation"


_PROPERTY_ALIASES: dict[str, CalculatedProperty] = {
    "total_energy": CalculatedProperty.ENERGY,
    "hf_energy": CalculatedProperty.ENERGY,
    "freq": CalculatedProperty.FREQUENCY,
    "esp": CalculatedProperty.ELECTROSTATIC_POTENTIAL,
    "density": CalculatedProperty.ELECTRON_DENSITY,
    "hof": CalculatedProperty.HEAT_OF_FORMATION,
    "heat_of_formation": CalculatedProperty.HEAT_OF_FORMATION,
    "heatofformation": CalculatedProperty.HEAT_OF_FORMATION,
    "formation_enthalpy": CalculatedProperty.HEAT_OF_FORMATION,
    "enthalpy_of_formation": CalculatedProperty.HEAT_OF_FORMATION,
    "delta_hf": CalculatedProperty.HEAT_OF_FORMATION,
    "dhf": CalculatedProperty.HEAT_OF_FORMATION,
}


def normalize_property_name(value: str | CalculatedProperty) -> str:
    """Return the standard name for a property or one of its aliases."""
    if isinstance(value, CalculatedProperty):
        return value.value
    if not isinstance(value, str):
        raise ValueError("property_name must be a string")

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        raise ValueError("property_name must not be blank")
    if normalized in {item.value for item in CalculatedProperty}:
        return normalized
    try:
        return _PROPERTY_ALIASES[normalized].value
    except KeyError as exc:
        raise ValueError(f"Unsupported public DFT property: {value!r}") from exc


__all__ = ["CalculatedProperty", "normalize_property_name"]
