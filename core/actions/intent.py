"""Definitions for declarative action intents and related specifications.

This module contains lightweight, serializable dataclasses that describe the
intent of an actor without performing any direct game state mutations.  These
structures are meant to be shared between different layers (UI, AI, network)
and therefore avoid dependencies on the runtime game state objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True, slots=True)
class CostSpec:
    """Basic description of resource costs tied to an action intent."""

    action_points: int = 0
    movement_points: int = 0
    blood: int = 0
    willpower: int = 0
    ammunition: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the cost specification."""

        return {
            "action_points": self.action_points,
            "movement_points": self.movement_points,
            "blood": self.blood,
            "willpower": self.willpower,
            "ammunition": self.ammunition,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CostSpec":
        """Create a :class:`CostSpec` from a mapping."""

        return cls(
            action_points=int(payload.get("action_points", 0)),
            movement_points=int(payload.get("movement_points", 0)),
            blood=int(payload.get("blood", 0)),
            willpower=int(payload.get("willpower", 0)),
            ammunition=int(payload.get("ammunition", 0)),
        )


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """Declarative description of a target used by an action intent.

    ``kind`` describes the family of target (``"self"``, ``"entity"``,
    ``"tile"``, ``"area"``, ...).  Depending on the kind, various optional
    attributes can be filled.  Extra details can be stored in ``extra`` for
    extension while keeping the structure immutable.
    """

    kind: str
    reference: Optional[str] = None
    position: Optional[Tuple[int, ...]] = None
    area_shape: Optional[str] = None
    radius: Optional[int] = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.position is not None:
            object.__setattr__(
                self,
                "position",
                self._coerce_position(self.position),
            )

        if self.radius is not None:
            object.__setattr__(self, "radius", int(self.radius))

        if not isinstance(self.extra, Mapping):
            raise TypeError("extra must be a mapping")

        object.__setattr__(self, "extra", MappingProxyType(dict(self.extra)))

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the target specification."""

        payload: dict[str, Any] = {"kind": self.kind}
        if self.reference is not None:
            payload["reference"] = self.reference
        if self.position is not None:
            payload["position"] = list(self.position)
        if self.area_shape is not None:
            payload["area_shape"] = self.area_shape
        if self.radius is not None:
            payload["radius"] = self.radius
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TargetSpec":
        """Create a :class:`TargetSpec` from a mapping."""

        position_payload = payload.get("position")
        position: Optional[Tuple[int, ...]] = None
        if position_payload is not None:
            if isinstance(position_payload, Sequence) and not isinstance(
                position_payload, (str, bytes)
            ):
                position = cls._coerce_position(position_payload)  # type: ignore[arg-type]
            else:
                raise TypeError("position must be a sequence of coordinates")

        extra = payload.get("extra", {})
        if extra is None:
            extra = {}

        return cls(
            kind=str(payload["kind"]),
            reference=payload.get("reference"),
            position=position,
            area_shape=payload.get("area_shape"),
            radius=cls._coerce_optional_int(payload.get("radius")),
            extra=extra,
        )

    @classmethod
    def self(cls) -> "TargetSpec":
        return cls(kind="self")

    @classmethod
    def entity(cls, reference: str, **extra: Any) -> "TargetSpec":
        return cls(kind="entity", reference=reference, extra=extra)

    @classmethod
    def tile(
        cls, position: Sequence[int] | Sequence[float], **extra: Any
    ) -> "TargetSpec":
        return cls(kind="tile", position=cls._coerce_position(position), extra=extra)

    @classmethod
    def area(
        cls,
        position: Sequence[int] | Sequence[float],
        *,
        shape: str,
        radius: int,
        **extra: Any,
    ) -> "TargetSpec":
        return cls(
            kind="area",
            position=cls._coerce_position(position),
            area_shape=shape,
            radius=int(radius),
            extra=extra,
        )

    @staticmethod
    def _coerce_position(position: Sequence[int | float]) -> Tuple[int, ...]:
        coords: list[int] = []
        for coord in position:
            if type(coord) is bool:
                raise TypeError("boolean values are not valid coordinates")
            if isinstance(coord, float):
                if not coord.is_integer():
                    raise ValueError("coordinates must be integers")
                coords.append(int(coord))
            elif isinstance(coord, int):
                coords.append(int(coord))
            else:
                raise TypeError("coordinates must be numeric")
        if not coords:
            raise ValueError("at least one coordinate must be provided")
        return tuple(coords)

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        return int(value)


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """Declarative description of an action an actor wishes to perform."""

    actor_id: str
    action_id: str
    targets: Tuple[TargetSpec, ...] = field(default_factory=tuple)
    params: Mapping[str, Any] = field(default_factory=dict)
    source_player_id: Optional[str] = None
    client_tx_id: Optional[str] = None

    def __post_init__(self) -> None:
        converted_targets = []
        for target in self.targets:
            if isinstance(target, TargetSpec):
                converted_targets.append(target)
            elif isinstance(target, Mapping):
                converted_targets.append(TargetSpec.from_dict(target))
            else:
                raise TypeError(
                    "targets must be TargetSpec instances or mapping payloads"
                )

        object.__setattr__(self, "targets", tuple(converted_targets))

        if not isinstance(self.params, Mapping):
            raise TypeError("params must be a mapping")

        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation of the intent."""

        return {
            "actor_id": self.actor_id,
            "action_id": self.action_id,
            "targets": [target.to_dict() for target in self.targets],
            "params": dict(self.params),
            "source_player_id": self.source_player_id,
            "client_tx_id": self.client_tx_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionIntent":
        """Create an :class:`ActionIntent` from a mapping."""

        targets_payload = payload.get("targets", [])
        if isinstance(targets_payload, Iterable):
            targets = tuple(TargetSpec.from_dict(target) for target in targets_payload)
        else:
            raise TypeError("targets must be an iterable of mappings")

        params_payload = payload.get("params", {})
        if params_payload is None:
            params_payload = {}

        return cls(
            actor_id=str(payload["actor_id"]),
            action_id=str(payload["action_id"]),
            targets=targets,
            params=params_payload,
            source_player_id=payload.get("source_player_id"),
            client_tx_id=payload.get("client_tx_id"),
        )

