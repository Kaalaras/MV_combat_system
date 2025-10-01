from typing import Dict, Iterable, Optional


class AttackPoolCacheComponent:
    """Stores precomputed dice pools for quick access during gameplay."""

    def __init__(
        self,
        weapon_pools: Optional[Dict[str, int]] = None,
        defense_pools: Optional[Dict[str, int]] = None,
        utility_pools: Optional[Dict[str, int]] = None,
    ) -> None:
        self.weapon_pools: Dict[str, int] = dict(weapon_pools or {})
        self.defense_pools: Dict[str, int] = dict(defense_pools or {})
        self.utility_pools: Dict[str, int] = dict(utility_pools or {})

    # ------------------------------------------------------------------
    # Convenience helpers
    def get(self, slot: str, default: int = 0) -> int:
        """Return the cached attack dice pool for ``slot``."""

        return self.weapon_pools.get(slot, default)

    def get_defense(self, name: str, default: int = 0) -> int:
        """Return the cached defense dice pool identified by ``name``."""

        return self.defense_pools.get(name, default)

    def get_utility(self, name: str, default: int = 0) -> int:
        """Return the cached utility dice pool identified by ``name``."""

        return self.utility_pools.get(name, default)

    def update(
        self,
        *,
        weapon_pools: Optional[Dict[str, int]] = None,
        defense_pools: Optional[Dict[str, int]] = None,
        utility_pools: Optional[Dict[str, int]] = None,
        overwrite_missing: bool = True,
    ) -> None:
        """Update cached dice pools while preserving shared references."""

        if weapon_pools is not None:
            _assign(self.weapon_pools, weapon_pools, overwrite_missing)
        if defense_pools is not None:
            _assign(self.defense_pools, defense_pools, overwrite_missing)
        if utility_pools is not None:
            _assign(self.utility_pools, utility_pools, overwrite_missing)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "AttackPoolCacheComponent("
            f"weapon_pools={self.weapon_pools!r}, "
            f"defense_pools={self.defense_pools!r}, "
            f"utility_pools={self.utility_pools!r}"
            ")"
        )


def _assign(target: Dict[str, int], source: Dict[str, int], overwrite_missing: bool) -> None:
    """Mutate ``target`` so it mirrors ``source`` with minimal churn."""

    if overwrite_missing:
        stale_keys: Iterable[str] = tuple(k for k in target.keys() if k not in source)
        for key in stale_keys:
            target.pop(key, None)

    for key, value in source.items():
        target[key] = value
