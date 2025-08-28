from enum import Enum
from typing import Set, Tuple

class DamageType(Enum):
    SUPERFICIAL = "superficial"
    AGGRAVATED = "aggravated"
    SUPERFICIAL_MAGIC = "superficial_magic"
    AGGRAVATED_MAGIC = "aggravated_magic"
    MIXED = "mixed"  # Placeholder for composite handling if needed later

class DamageCategory(Enum):
    PHYSICAL = "physical"
    GAS = "gas"
    MAGIC = "magic"
    FIRE = "fire"
    TRUE_FAITH = "true_faith"
    COLD = "cold"
    ELECTRIC = "electric"

VALID_DAMAGE_TYPES: Set[str] = {dt.value for dt in DamageType}
VALID_DAMAGE_CATEGORIES: Set[str] = {dc.value for dc in DamageCategory}

def is_magic(damage_type: str) -> bool:
    return damage_type.endswith('_magic') or damage_type in (DamageCategory.MAGIC.value,)

def base_type(damage_type: str) -> str:
    return damage_type.replace('_magic', '') if damage_type.endswith('_magic') else damage_type

def classify_damage(damage_type: str) -> Tuple[str, str]:
    """Return (severity, category) for an incoming damage_type string.
    Severity: superficial/aggravated/mixed/unknown
    Category: one of DamageCategory values; magic suffix implies MAGIC category.
    Unknown types default to PHYSICAL for safety.
    """
    sev = base_type(damage_type)
    if sev not in {"superficial", "aggravated", "mixed"}:
        sev = "unknown"
    if damage_type.endswith('_magic'):
        cat = DamageCategory.MAGIC.value
    else:
        # map by simple heuristics / keywords
        if any(k in damage_type for k in ("fire", "flame")):
            cat = DamageCategory.FIRE.value
        elif any(k in damage_type for k in ("cold", "ice", "frost")):
            cat = DamageCategory.COLD.value
        elif any(k in damage_type for k in ("shock", "electric", "lightning")):
            cat = DamageCategory.ELECTRIC.value
        elif "gas" in damage_type:
            cat = DamageCategory.GAS.value
        elif "faith" in damage_type or "holy" in damage_type:
            cat = DamageCategory.TRUE_FAITH.value
        else:
            cat = DamageCategory.PHYSICAL.value
    return sev, cat

__all__ = [
    'DamageType', 'DamageCategory', 'VALID_DAMAGE_TYPES', 'VALID_DAMAGE_CATEGORIES', 'is_magic', 'base_type', 'classify_damage'
]
