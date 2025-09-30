class EntityIdComponent:
    """Stores the authoritative string identifier for an ECS entity."""

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
