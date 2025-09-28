# vision_system.py
from __future__ import annotations
from typing import Any, Optional

# -- Constants (fallbacks if modules not loaded at import time)
try:
    from utils.condition_utils import NIGHT_VISION_PARTIAL, NIGHT_VISION_TOTAL
except Exception:
    NIGHT_VISION_PARTIAL = "night_vision_partial"
    NIGHT_VISION_TOTAL = "night_vision_total"

try:
    from core.terrain_manager import EFFECT_DARK_LOW, EFFECT_DARK_TOTAL
except Exception:
    EFFECT_DARK_LOW = "dark_low"
    EFFECT_DARK_TOTAL = "dark_total"


class VisionSystem:
    """
    Abstraction des capacités de vision (vision nocturne partielle/totale) et
    des interactions avec l'obscurité du terrain.

    Conventions:
      - NV tiers: 0 = aucune, 1 = partielle, 2 = totale.
      - Obscurité terrain: 0 = aucune, 1 = faible, 2 = totale.
      - Modificateurs d'attaque: bornés dans [-3, +3] (règle maison).
        Si obscurité totale et pas NV totale: la LoS devrait bloquer. Si, pour
        une raison de rules order, on applique quand même un modificateur,
        utiliser -3 (jamais -4).
    """

    def __init__(self, game_state: Any, terrain: Any, los_manager: Optional[Any] = None):
        self.game_state = game_state
        self.terrain = terrain
        self.los_manager = los_manager

    # ---------------------------- Utils internes -----------------------------

    def _get_entity(self, entity_id: str) -> Any:
        getter = getattr(self.game_state, "get_entity", None)
        return getter(entity_id) if getter else None

    def _get_char(self, entity_id: str) -> Any:
        ent = self._get_entity(entity_id)
        if not ent:
            return None
        # Support dict ou objet
        char_ref = ent.get("character_ref") if isinstance(ent, dict) else getattr(ent, "character_ref", None)
        return getattr(char_ref, "character", None) if char_ref else None

    # -------------------------- Capacités de vision --------------------------

    def get_nv_tier(self, entity_id: str) -> int:
        """0 = aucune, 1 = partielle, 2 = totale."""
        ch = self._get_char(entity_id)
        if not ch:
            return 0
        states = getattr(ch, "states", set()) or set()
        if NIGHT_VISION_TOTAL in states:
            return 2
        if NIGHT_VISION_PARTIAL in states:
            return 1
        return 0

    def has_total_night_vision(self, entity_id: str) -> bool:
        return self.get_nv_tier(entity_id) >= 2

    def has_partial_night_vision(self, entity_id: str) -> bool:
        return self.get_nv_tier(entity_id) >= 1

    # --------------------------- Obscurité du terrain ------------------------

    def is_tile_dark_total(self, x: int, y: int) -> bool:
        has_effect = getattr(self.terrain, "has_effect", None)
        return bool(has_effect and has_effect(x, y, EFFECT_DARK_TOTAL))

    def is_tile_dark_low(self, x: int, y: int) -> bool:
        has_effect = getattr(self.terrain, "has_effect", None)
        return bool(has_effect and has_effect(x, y, EFFECT_DARK_LOW))

    def defender_tile_darkness(self, defender_id: str) -> int:
        """0 = aucune, 1 = faible, 2 = totale au niveau de la case du défenseur."""
        ent = self._get_entity(defender_id)
        if not ent:
            return 0
        pos = ent.get("position") if isinstance(ent, dict) else getattr(ent, "position", None)
        if not pos:
            return 0
        x, y = getattr(pos, "x", None), getattr(pos, "y", None)
        if x is None or y is None:
            return 0
        if self.is_tile_dark_total(x, y):
            return 2
        if self.is_tile_dark_low(x, y):
            return 1
        return 0

    # ----------------------- Modificateurs d'attaque -------------------------

    def get_attack_modifier(self, attacker_id: str, defender_id: str) -> int:
        """
        Modificateur dû à l'obscurité (dés +/-) sur l'attaque de attacker -> defender.

        Règles:
          - Obscurité totale (2) + NV < 2 : la LoS devrait empêcher l'attaque;
            si pour une raison donnée l'attaque passe quand même, appliquer -3 (max).
          - Obscurité faible (1) + NV < 1 : -1.
          - NV partielle/totale annule la pénalité du niveau correspondant.
        """
        darkness = self.defender_tile_darkness(defender_id)
        nv = self.get_nv_tier(attacker_id)

        # Obscurité totale sans NV totale: privilégier le blocage LoS
        if darkness == 2 and nv < 2:
            if self.los_manager and hasattr(self.los_manager, "can_see"):
                # Si la LoS échoue, l'attaque ne devrait pas être résolue ici.
                if not self.los_manager.can_see(attacker_id, defender_id):
                    return 0
            # Fallback: appliquer le max de pénalité admis
            return -3

        # Obscurité faible sans NV partielle
        if darkness == 1 and nv < 1:
            return -1

        return 0

    # ------------------------------- Aide UI ---------------------------------

    def get_visibility_tag(self, attacker_id: str, x: int, y: int) -> str:
        """
        Tag simple pour l'UI d’overlay (« clear », « obscured », « dark ») selon la case et la NV de l’attaquant.
        """
        nv = self.get_nv_tier(attacker_id)
        if self.is_tile_dark_total(x, y):
            return "dark" if nv < 2 else "clear"
        if self.is_tile_dark_low(x, y):
            return "obscured" if nv < 1 else "clear"
        return "clear"
