from typing import Optional


class EntityIdComponent:
    """Stores the authoritative identifiers for an ECS entity."""

    def __init__(self, entity_id: str, base_object_id: Optional[int] = None):
        self.entity_id = entity_id
        # ``BaseObject`` already exposes an integer ``id``; keep it for cross-linking.
        self.base_object_id = base_object_id
