"""High-level character information queries."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def get_character_summary(actor_id: str, ecs: Any) -> dict[str, Any]:
    """
    Return a read-only summary of character data relevant to the UI layer.

    Returns:
        dict: A dictionary with the following structure:
            - actor_id (str): The unique identifier for the character.
            - name (str or None): The character's name, or None if unavailable.
            - clan (str or None): The character's clan, or None if unavailable.
            - attributes (dict): A mapping of attribute names to their values (may be empty).
            - skills (dict): A mapping of skill names to their values (may be empty).
            - disciplines (tuple): A tuple of discipline IDs (as strings), possibly empty.
            - states (tuple): A tuple of state names (as strings), possibly empty.

    All values are read-only and suitable for display in the UI layer.
    """
    manager = _locate_ecs_manager(ecs)
    summary = {
        "actor_id": actor_id,
        "name": None,
        "clan": None,
        "attributes": {},
        "skills": {},
        "disciplines": (),
        "states": (),
    }

    if manager is None:
        return summary

    try:
        from ecs.components.character_ref import CharacterRefComponent
    except ImportError:  # pragma: no cover - optional dependency guard
        return summary

    components = manager.get_components_for_entity(actor_id, CharacterRefComponent)
    if not components:
        return summary

    character_component = components[0]
    character = getattr(character_component, "character", None)
    if character is None:
        return summary

    summary["name"] = getattr(character, "name", None)
    summary["clan"] = getattr(character, "clan", None)

    traits = _ensure_mapping(getattr(character, "traits", {}))
    summary["attributes"] = _clone_mapping(traits.get("Attributes", {}))
    summary["skills"] = _clone_mapping(
        _select_first_present_mapping(
            traits,
            (
                "Abilities",
                "Skills",
                "Competences",
            ),
        )
    )

    discipline_ids: set[str] = set()
    discipline_traits = traits.get("Disciplines", {})
    if isinstance(discipline_traits, Mapping):
        for key in discipline_traits.keys():
            discipline_ids.add(str(key))

    clan_disciplines = getattr(character, "clan_disciplines", None)
    if isinstance(clan_disciplines, Mapping):
        for key in clan_disciplines.keys():
            discipline_ids.add(str(key))

    summary["disciplines"] = tuple(sorted(discipline_ids))

    states: set[str] = set()
    char_states = getattr(character, "states", None)
    if isinstance(char_states, set):
        states.update(str(state) for state in char_states)

    try:
        from ecs.components.condition_tracker import ConditionTrackerComponent
    except ImportError:  # pragma: no cover - optional dependency guard
        tracker = None
    else:
        tracker_components = manager.get_components_for_entity(actor_id, ConditionTrackerComponent)
        tracker = tracker_components[0] if tracker_components else None

    if tracker is not None:
        for attr_name in ("active_states", "dynamic_states"):
            tracker_states_attr = getattr(tracker, attr_name, None)
            tracker_states: Any = ()

            if callable(tracker_states_attr):
                try:
                    tracker_states = tracker_states_attr()
                except TypeError:  # pragma: no cover - defensive guard
                    tracker_states = ()
            elif tracker_states_attr is not None:
                tracker_states = tracker_states_attr

            for state in _iterate_state_values(tracker_states):
                states.add(str(state))

    summary["states"] = tuple(sorted(states))

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _locate_ecs_manager(ecs: Any) -> Any:
    if hasattr(ecs, "resolve_entity"):
        return ecs

    candidate = getattr(ecs, "ecs_manager", None)
    if candidate is not None and hasattr(candidate, "resolve_entity"):
        return candidate

    return None


def _ensure_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _select_first_present_mapping(
    source: Mapping[str, Any], keys: Sequence[str]
) -> Mapping[str, Any]:
    for key in keys:
        if key in source:
            candidate = source[key]
            if isinstance(candidate, Mapping):
                return candidate
    return {}


def _clone_mapping(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}

    result: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Mapping):
            result[str(key)] = _clone_mapping(value)
        else:
            result[str(key)] = value
    return result


def _iterate_state_values(candidate: Any) -> tuple[Any, ...]:
    if candidate is None:
        return ()

    if isinstance(candidate, (list, tuple, set)):
        return tuple(candidate)

    if isinstance(candidate, Mapping):
        return tuple(candidate.keys())

    if hasattr(candidate, "__iter__") and not isinstance(candidate, (str, bytes)):
        return tuple(candidate)

    return (candidate,)


__all__ = ["get_character_summary"]
