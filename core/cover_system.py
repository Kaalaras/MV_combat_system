from typing import Any, Tuple

class CoverSystem:
    """Computes cover bonuses for ranged attacks using LOS visibility cache.

    Rules implemented (per spec):
      - Each intervening cover entity adds its modifier (sum of their bonuses).
      - A partial wall (some but not all LOS rays blocked by walls) grants +2 successes.
      - If there is NO cover (no intervening cover entities and no partial wall) defender suffers -2 penalty.
    Assumptions:
      - LineOfSightManager provides unified VisibilityEntry with cover_sum & partial_wall.
    """
    def __init__(self, game_state: Any):
        self.game_state = game_state

    def compute_ranged_cover_bonus(self, attacker_id: str, defender_id: str) -> int:
        attacker_ent = self.game_state.get_entity(attacker_id)
        defender_ent = self.game_state.get_entity(defender_id)
        if not attacker_ent or not defender_ent:
            return 0
        apos = attacker_ent.get('position')
        dpos = defender_ent.get('position')
        if not apos or not dpos:
            return 0
        los_mgr = getattr(self.game_state, 'los_manager', None)
        if not los_mgr:
            return 0
        entry = los_mgr.get_visibility_entry((apos.x, apos.y), (dpos.x, dpos.y))
        if not entry.cover_ids and not entry.partial_wall:
            return -2  # no cover at all
        return entry.cover_sum + (2 if entry.partial_wall else 0)
