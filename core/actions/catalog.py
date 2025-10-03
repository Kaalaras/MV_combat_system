"""Static catalog of declarative action definitions.

This module exposes :class:`ActionDef`, a lightweight dataclass describing the
properties of an action without tying it to runtime systems.  The catalog is
intended to be consumed by selection and validation layers so they can reason
about what an actor *could* do before any state mutation occurs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from core.actions.intent import CostSpec


Prerequisite = Callable[..., bool] | str
TargetingMode = Mapping[str, Any] | str


@dataclass(frozen=True, slots=True)
class ActionDef:
    """Declarative description of an action available in the catalog."""

    id: str
    name: str
    category: str
    targeting: Sequence[TargetingMode] = field(default_factory=tuple)
    costs: CostSpec = field(default_factory=CostSpec)
    tags: Sequence[str] = field(default_factory=tuple)
    prereqs: Sequence[Prerequisite] = field(default_factory=tuple)
    effects: str | None = None
    reaction_speed: str = "none"

    def to_dict(self) -> dict[str, Any]:
        """Provide a serialisable representation of the action definition."""

        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "targeting": list(self.targeting),
            "costs": self.costs.to_dict(),
            "tags": list(self.tags),
            "prereqs": list(self.prereqs),
            "effects": self.effects,
            "reaction_speed": self.reaction_speed,
        }


ACTION_CATALOG: dict[str, ActionDef] = {
    "move": ActionDef(
        id="move",
        name="Move",
        category="move",
        targeting=(
            {
                "kind": "tile",
                "prompt": "Destination tile (x,y)",
            },
        ),
        costs=CostSpec(movement_points=1),
        tags=("basic", "movement"),
        effects="queue_move",
    ),
    "attack_melee": ActionDef(
        id="attack_melee",
        name="Melee Attack",
        category="attack",
        targeting=(
            {
                "kind": "entity",
                "prompt": "Select adjacent enemy",
            },
        ),
        costs=CostSpec(action_points=1),
        tags=("attack", "melee"),
        effects="queue_melee_attack",
    ),
    "attack_ranged": ActionDef(
        id="attack_ranged",
        name="Ranged Attack",
        category="attack",
        targeting=(
            {
                "kind": "entity",
                "prompt": "Select visible enemy",
            },
        ),
        costs=CostSpec(action_points=1, ammunition=1),
        tags=("attack", "ranged"),
        effects="queue_ranged_attack",
    ),
    "defend_dodge": ActionDef(
        id="defend_dodge",
        name="Dodge",
        category="defense",
        targeting=(
            {
                "kind": "self",
            },
        ),
        costs=CostSpec(action_points=1),
        tags=("defense", "reaction"),
        effects="queue_dodge",
        reaction_speed="fast",
    ),
    "discipline_generic": ActionDef(
        id="discipline_generic",
        name="Discipline Power",
        category="discipline",
        targeting=(),
        costs=CostSpec(action_points=1, willpower=1),
        tags=("discipline",),
        effects="queue_discipline_effect",
    ),
}


def iter_catalog() -> Iterable[ActionDef]:
    """Helper returning a stable iteration over catalog entries."""

    return ACTION_CATALOG.values()

