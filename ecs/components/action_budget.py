from __future__ import annotations

from typing import Mapping, MutableMapping, Optional, Set


class ActionBudgetComponent:
    """Track reserved action resources for an entity."""

    def __init__(
        self,
        *,
        reserved: Optional[Mapping[str, int]] = None,
        pending: Optional[Mapping[str, int]] = None,
        transactions: Optional[Set[str]] = None,
    ) -> None:
        self.reserved: MutableMapping[str, int] = dict(reserved or {})
        self.pending: MutableMapping[str, int] = dict(pending or {})
        self._transactions: Set[str] = set(transactions or set())

    def reserve(self, costs: Mapping[str, int], *, transaction_id: Optional[str] = None) -> None:
        """Record ``costs`` as pending for ``transaction_id`` if new."""

        if transaction_id and transaction_id in self._transactions:
            return

        for resource, amount in costs.items():
            value = int(amount)
            if value <= 0:
                continue
            self.pending[resource] = self.pending.get(resource, 0) + value

        if transaction_id:
            self._transactions.add(transaction_id)

    def commit(self, transaction_id: Optional[str] = None) -> None:
        """Move pending resources to the reserved pool."""

        for resource, value in list(self.pending.items()):
            self.reserved[resource] = self.reserved.get(resource, 0) + value
        self.pending.clear()
        if transaction_id and transaction_id in self._transactions:
            self._transactions.remove(transaction_id)

    def clear(self) -> None:
        """Reset all bookkeeping data."""

        self.reserved.clear()
        self.pending.clear()
        self._transactions.clear()


__all__ = ["ActionBudgetComponent"]

