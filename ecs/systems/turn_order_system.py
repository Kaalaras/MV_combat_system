# ecs/systems/turn_order_system.py
"""
Turn Order System Module
=======================

This module implements a turn order management system for turn-based games using an Entity Component System (ECS)
architecture. It handles initiative calculation, turn sequencing, and round progression.

The system supports:
- Initiative calculation based on character attributes
- Random tie-breaking for equal initiatives
- Round tracking
- Turn sequencing and management
- Delaying turns within the initiative order

Example:
    # Create a game state
    game_state = GameState()

    # Initialize characters in the game state
    game_state.add_entity("player1", {"character_ref": PlayerCharacter(...)})
    game_state.add_entity("enemy1", {"character_ref": EnemyCharacter(...)})

    # Initialize the turn order system
    turn_system = TurnOrderSystem(game_state)

    # Get the current active entity
    active_entity_id = turn_system.current_entity()

    # When an entity's turn is complete
    next_entity_id = turn_system.next_turn()

    # Get the full initiative order
    initiative_order = turn_system.get_turn_order()

    # If an entity wants to delay their turn
    turn_system.delay_current_entity()
"""
import random
from typing import List, Dict, Optional, Any


class TurnOrderSystem:
    """
    Manages the initiative order and turn progression for entities in a turn-based game.

    This system calculates initiative values for each entity, maintains the turn order,
    and provides methods for progressing through turns and rounds.

    Attributes:
        game_state: The central game state containing all entities
        turn_order (List[str]): Ordered list of entity IDs representing the initiative order
        turn_index (int): Current index in the turn order
        round_number (int): Current round number (starts at 1)
        tie_breakers (Dict[str, int]): Random numbers used to break initiative ties
    """

    def __init__(self, game_state: Any):
        """
        Initialize the TurnOrderSystem.

        Args:
            game_state: The central game state containing all entities
        """
        self.game_state = game_state
        self.turn_order: List[str] = []
        self.turn_index: int = 0
        self.round_number: int = 0
        self.tie_breakers: Dict[str, int] = {}  # Stores random tie-breaker for each entity
        self.reserved_tiles = set()
        self.start_new_round()

    def get_or_create_tie_breaker(self, entity_id: str) -> int:
        """
        Get or generate a random tie-breaker value for an entity.

        This ensures that each entity has a consistent tie-breaker value
        throughout a game session.

        Args:
            entity_id (str): The entity identifier

        Returns:
            int: The tie-breaker value for this entity
        """
        if entity_id not in self.tie_breakers:
            self.tie_breakers[entity_id] = random.randint(0, int(1e9))
        return self.tie_breakers[entity_id]

    def calculate_initiative(self, entity: Dict[str, Any]) -> int:
        """
        Calculate an initiative value for an entity based on its traits.

        The initiative is calculated as the higher of Self-Control or Instinct virtues,
        plus the Wits attribute.

        Args:
            entity (Dict[str, Any]): The entity object containing character traits

        Returns:
            int: The calculated initiative value

        Example:
            > entity = {"character_ref": character_with_traits}
            > turn_system.calculate_initiative(entity)
            7
        """
        char_ref = entity.get("character_ref")
        character = getattr(char_ref, 'character', None) if char_ref else None
        traits = getattr(character, 'traits', {}) or {}
        virtues = traits.get("Virtues", {}) if isinstance(traits, dict) else {}
        mental_attrs = {}
        if isinstance(traits, dict):
            attributes = traits.get("Attributes", {})
            if isinstance(attributes, dict):
                mental_attrs = attributes.get("Mental", {}) or {}
        def _safe_value(mapping, key):
            try:
                return int(mapping.get(key, 0)) if isinstance(mapping, dict) else 0
            except (TypeError, ValueError):
                return 0

        return max(_safe_value(virtues, "Self-Control"), _safe_value(virtues, "Instinct")) + _safe_value(mental_attrs, "Wits")

    def start_new_round(self) -> None:
        """
        Start a new round by incrementing the round counter and recalculating turn order.

        This method:
        1. Increments the round number
        2. Collects all living entities with character components
        3. Sorts them by initiative (and tie-breaker) in descending order
        4. Resets the turn index to the beginning

        Returns:
            None
        """
        self.round_number += 1
        self.reserved_tiles.clear()
        
        # Get all entities with character_ref using ECS
        from ecs.components.character_ref import CharacterRefComponent
        
        living_entities = []
        reverse_mapping = getattr(self.game_state, "_reverse_entity_id_mapping", {})

        def _to_external_id(raw_id: Any) -> str:
            """Translate internal ECS identifiers back to the original game IDs."""
            try:
                lookup_key = int(raw_id)
            except (TypeError, ValueError):
                lookup_key = raw_id

            if lookup_key in reverse_mapping:
                return reverse_mapping[lookup_key]
            return str(raw_id)
        if self.game_state.ecs_manager:
            try:
                entities_with_char_ref = self.game_state.ecs_manager.get_components(CharacterRefComponent)
                for eid, (char_ref_comp,) in entities_with_char_ref:
                    if not char_ref_comp.character.is_dead:
                        living_entities.append(_to_external_id(eid))
            except AttributeError:
                # Fallback if get_components doesn't exist
                for entity_id in self.game_state.ecs_manager.get_all_entities():
                    try:
                        char_ref_comp = self.game_state.ecs_manager.get_component(entity_id, CharacterRefComponent)
                        if char_ref_comp and not char_ref_comp.character.is_dead:
                            living_entities.append(_to_external_id(entity_id))
                    except:
                        continue

        self.turn_order = living_entities
        # Sort by initiative desc, tie-breaker desc
        self.turn_order.sort(
            key=lambda eid: (
                self.calculate_initiative(self.game_state.get_entity(eid)),
                self.get_or_create_tie_breaker(eid)
            ),
            reverse=True
        )
        self.turn_index = 0
        # Publish round started event
        if getattr(self.game_state, 'event_bus', None):
            self.game_state.event_bus.publish('round_started', round_number=self.round_number, turn_order=list(self.turn_order))
        # Also publish first turn started if exists
        if self.turn_order and getattr(self.game_state, 'event_bus', None):
            self.game_state.event_bus.publish('turn_started', round_number=self.round_number, entity_id=self.turn_order[0])

    def get_turn_order(self) -> List[str]:
        """
        Get the current initiative order as a list of entity IDs.

        Returns:
            List[str]: A copy of the turn order list

        Example:
            > turn_system.get_turn_order()
            ["player1", "enemy2", "enemy1", "player2"]
        """
        return list(self.turn_order)

    def current_entity(self) -> Optional[str]:
        """
        Get the ID of the entity whose turn it currently is.

        Returns:
            Optional[str]: The entity ID, or None if the turn order is empty
                          or the turn index is out of bounds

        Example:
            > turn_system.current_entity()
            "player1"
        """
        if not self.turn_order or self.turn_index >= len(self.turn_order):
            return None
        return self.turn_order[self.turn_index]

    def delay_current_entity(self) -> None:
        """
        Delay the current entity's turn by moving them later in the initiative order.

        If the entity is already last in the order, they are removed from the current round.

        Returns:
            None

        Example:
            > turn_system.turn_order
            ["player1", "enemy1", "player2"]
            > turn_system.turn_index = 0
            > turn_system.delay_current_entity()
            > turn_system.turn_order
            ["enemy1", "player1", "player2"]
        """
        # Move current entity down one rank if possible
        if self.turn_index < len(self.turn_order) - 1:
            eid = self.turn_order.pop(self.turn_index)
            self.turn_order.insert(self.turn_index + 1, eid)
        else:
            # If already at the bottom, remove entirely for this round
            self.turn_order.pop()

    def next_turn(self) -> Optional[str]:
        """
        Advance to the next entity's turn.

        If the end of the turn order is reached, a new round is started.

        Returns:
            Optional[str]: The ID of the next entity in the turn order,
                          or None if the turn order is empty

        Example:
            > turn_system.current_entity()
            "player1"
            > turn_system.next_turn()
            "enemy1"
            > turn_system.round_number  # If enemy1 was the last in order
            2
        """
        current_entity_id = self.current_entity()
        if getattr(self.game_state, 'event_bus', None) and current_entity_id is not None:
            self.game_state.event_bus.publish('turn_ended', round_number=self.round_number, entity_id=current_entity_id)
        self.turn_index += 1
        if self.turn_index >= len(self.turn_order):
            self.start_new_round()
        # Publish new turn started
        new_entity = self.current_entity()
        if getattr(self.game_state, 'event_bus', None) and new_entity is not None:
            self.game_state.event_bus.publish('turn_started', round_number=self.round_number, entity_id=new_entity)
        return new_entity
