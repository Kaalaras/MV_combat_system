"""ECS component storing resource pools for an entity."""

from __future__ import annotations

from typing import Mapping, MutableMapping


class ResourcePoolComponent:
    """Track consumable resources (action points, ammunition, ...)."""

    def __init__(self, **resources: int) -> None:
        self._values: MutableMapping[str, int] = {}
        if resources:
            self.update(resources)

    def set(self, resource: str, amount: int) -> None:
        """Assign ``amount`` to ``resource`` in the pool."""

        self._values[str(resource)] = int(amount)

    def add(self, resource: str, amount: int) -> None:
        """Increase ``resource`` by ``amount`` (may be negative)."""

        key = str(resource)
        self._values[key] = int(self._values.get(key, 0) + int(amount))

    def get(self, resource: str, default: int | None = 0) -> int | None:
        """Return the stored value for ``resource`` (defaults to ``default``)."""

        if default is None and resource not in self._values:
            return None
        return int(self._values.get(str(resource), default or 0))

    def update(self, mapping: Mapping[str, int]) -> None:
        """Update the pool from ``mapping`` of resource -> amount."""

        for key, value in mapping.items():
            self.set(str(key), int(value))

    def as_dict(self) -> dict[str, int]:
        """Return a plain dictionary copy of the pool values."""

        return {key: int(value) for key, value in self._values.items()}

    def __contains__(self, resource: str) -> bool:  # pragma: no cover - convenience
        return str(resource) in self._values


__all__ = ["ResourcePoolComponent"]
