from __future__ import annotations

from core.actions.catalog import ACTION_CATALOG, ActionDef, iter_catalog


def test_catalog_contains_expected_entries() -> None:
    expected_ids = {"move", "attack_melee", "attack_ranged", "defend_dodge", "discipline_generic"}
    assert expected_ids <= set(ACTION_CATALOG)

    move_def = ACTION_CATALOG["move"]
    assert isinstance(move_def, ActionDef)
    assert move_def.category == "move"
    assert move_def.reaction_speed == "none"

    dodge_def = ACTION_CATALOG["defend_dodge"]
    assert dodge_def.reaction_speed == "fast"
    assert "reaction" in dodge_def.tags


def test_iter_catalog_returns_stable_sequence() -> None:
    first = list(iter_catalog())
    second = list(iter_catalog())
    assert [action.id for action in first] == [action.id for action in second]
