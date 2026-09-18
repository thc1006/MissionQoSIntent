"""Parse declarative YAML QoS contracts into validated Pydantic models."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import ValidationError

from mqi.contracts.errors import ContractError
from mqi.contracts.models import MissionQoSContract


def parse_contract(text: str) -> MissionQoSContract:
    """Parse and validate a YAML contract, returning a typed `MissionQoSContract`.

    Raises:
        ContractError: with a machine-readable ``code`` and a JSON ``path`` to the offending field.
    """
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContractError("invalid_yaml", "", f"malformed YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("invalid_yaml", "", "top-level document must be a mapping")
    try:
        return MissionQoSContract.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ContractError(
            code=str(first["type"]),
            path=_loc_to_path(first["loc"]),
            message=str(first["msg"]),
        ) from exc


def dump_contract(contract: MissionQoSContract) -> str:
    """Serialise a contract back to YAML such that ``parse_contract`` round-trips it identically."""
    return yaml.safe_dump(contract.model_dump(mode="json", by_alias=True), sort_keys=False)


def _loc_to_path(loc: tuple[str | int, ...]) -> str:
    """Render a Pydantic error location tuple as a dotted JSON path with ``[i]`` indices.

    The document is validated to be a mapping before this runs, so ``loc`` always starts with
    a field name (never a list index).
    """
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts[-1] = f"{parts[-1]}[{item}]"
        else:
            parts.append(item)
    return ".".join(parts)
