# entities/effects.py
from abc import ABC, abstractmethod
from typing import List, Any, Tuple, Dict
from math import floor, degrees, sqrt
import numpy as np

class _Position:
    """Simple position wrapper for entities/effects.py internal use."""
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
    
    def __getitem__(self, index):
        """Allow subscript access for compatibility."""
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        else:
            raise IndexError("Position index out of range")

def _get_distance(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
    """Helper function to calculate Manhattan distance."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

class AttackEffect(ABC):
    """Base class for all special effects that can be applied by an attack."""

    @abstractmethod
    def apply(self, game_state: Any, context: Dict[str, Any]) -> None:
        """
        Apply the effect to the game state.

        Args:
            game_state: The current state of the game.
            context: A dictionary containing contextual information for the effect,
                     such as attacker_id, target_id, weapon, initial_dice_pool, etc.
        """
        pass

class PenetrationEffect(AttackEffect):
    """
    Effect for attacks that can hit multiple targets in a line.
    The attack continues until it runs out of dice or hits its max penetration count.
    """
    def __init__(self, max_penetration: int = 1):
        self.max_penetration = max_penetration

    def apply(self, game_state: Any, context: Dict[str, Any]) -> None:
        """
        Traces a line from the attacker past the primary target, attacking subsequent
        targets in the path until the dice pool is depleted or max penetrations reached.
        """
        attack_action = context.get("attack_action")
        if not attack_action:
            return

        remaining_pool = context.get("remaining_dice_pool", 0)
        if remaining_pool <= 0:
            return

        attacker_entity = game_state.get_entity(context["attacker_id"])
        primary_target_entity = game_state.get_entity(context["primary_target_id"])
        if not attacker_entity or not primary_target_entity:
            return

        start_pos = attacker_entity.get("position")
        primary_target_pos = primary_target_entity.get("position")
        if not start_pos or not primary_target_pos:
            return

        # Determine the attack vector
        dx = primary_target_pos.x - start_pos.x
        dy = primary_target_pos.y - start_pos.y

        # Sort potential secondary targets by distance from the primary target along the attack vector
        potential_targets = []
        for entity_id, entity_pos_tuple in game_state.terrain.entity_positions.items():
            if entity_id in [context["attacker_id"], context["primary_target_id"]]:
                continue

            entity_pos = _Position(entity_pos_tuple[0], entity_pos_tuple[1])

            # Check if the entity is roughly "behind" the primary target
            vec_to_entity_x = entity_pos.x - start_pos.x
            vec_to_entity_y = entity_pos.y - start_pos.y

            # Simple dot product check to see if it's in the same general direction
            if (dx * vec_to_entity_x + dy * vec_to_entity_y) > 0:
                dist = _get_distance((primary_target_pos.x, primary_target_pos.y), entity_pos_tuple)
                potential_targets.append((dist, entity_id, entity_pos))

        potential_targets.sort(key=lambda t: t[0]) # Sort by distance

        penetrations = 0
        for _, target_id, target_pos in potential_targets:
            if penetrations >= self.max_penetration or remaining_pool <= 0:
                break

            # Check LoS from the original attacker to the new target
            if game_state.los_manager.has_los(start_pos, target_pos):
                print(f"[Penetration] Attack continues, hitting {target_id} with {remaining_pool} dice.")
                _, new_remaining_pool = attack_action._resolve_single_attack(
                    target_id,
                    remaining_pool
                )
                remaining_pool = new_remaining_pool
                penetrations += 1
            else:
                # If LoS is blocked, the penetration chain might be stopped
                # depending on game rules. We'll assume it stops here.
                print(f"[Penetration] LoS to {target_id} is blocked. Stopping penetration.")
                break

class AreaOfEffect(AttackEffect):
    """Base class for Area of Effect (AoE) attacks."""
    def __init__(self, decay: float):
        self.decay = decay  # How much the dice pool diminishes per unit of distance

    @abstractmethod
    def get_affected_entities(self, game_state: Any, origin_pos: Tuple[int, int], context: Dict[str, Any]) -> List[str]:
        """
        Determines which entities are within the AoE.

        Args:
            game_state: The current state of the game.
            origin_pos: The (x, y) coordinate of the AoE's center.
            context: The attack context for additional info (like attacker position).

        Returns:
            A list of entity IDs that are affected.
        """
        pass

    def apply(self, game_state: Any, context: Dict[str, Any]) -> None:
        """
        Finds all targets in the AoE and triggers a separate attack against each one,
        with a dice pool reduced by distance from the impact point.
        """
        attack_action = context.get("attack_action")
        if not attack_action:
            return

        impact_pos = context["impact_pos"]
        initial_pool = context["initial_dice_pool"]
        primary_target_id = context["primary_target_id"]

        affected_entities = self.get_affected_entities(game_state, impact_pos, context)

        for target_id in affected_entities:
            if target_id == primary_target_id:
                continue  # Primary target already handled

            target_entity = game_state.get_entity(target_id)
            if not target_entity:
                continue

            target_pos = target_entity.get("position")
            if not target_pos:
                continue

            # Check LoS from impact point to the secondary target
            if not game_state.los_manager.has_los(impact_pos, (target_pos.x, target_pos.y)):
                print(f"[AoE] Target {target_id} is in range but not in LoS from impact point.")
                continue

            distance = _get_distance(impact_pos, (target_pos.x, target_pos.y))
            if distance < 1: # Treat targets within 1 unit of impact as having no distance decay
                decayed_pool = initial_pool
            else:
                decayed_pool = floor(initial_pool * (self.decay ** distance))

            if decayed_pool > 0:
                print(f"[AoE] Hitting secondary target {target_id} with decayed pool of {decayed_pool}.")
                attack_action._resolve_single_attack(target_id, decayed_pool)
            else:
                print(f"[AoE] Attack on {target_id} fizzles out. Decayed pool is {decayed_pool}.")


class RadiusAoE(AreaOfEffect):
    """An AoE that affects all entities within a certain radius of a point."""
    def __init__(self, radius: int, decay: float = 0.5):
        super().__init__(decay)
        self.radius = radius

    def get_affected_entities(self, game_state: Any, origin_pos: Tuple[int, int], context: Dict[str, Any]) -> List[str]:
        """Finds all entities within a simple radius."""
        affected = []
        # Iterate over all entities known by the terrain manager
        for entity_id, entity_pos in game_state.terrain.entity_positions.items():
            if _get_distance(origin_pos, entity_pos) <= self.radius:
                affected.append(entity_id)
        return affected

class ConeAoE(AreaOfEffect):
    """An AoE that affects all entities within a cone shape."""
    def __init__(self, length: int, angle: int, decay: float = 0.5):
        super().__init__(decay)
        self.length = length
        self.angle = angle

    def get_affected_entities(self, game_state: Any, origin_pos: Tuple[int, int], context: Dict[str, Any]) -> List[str]:
        """Finds all entities within a cone originating from the attacker and extending from the impact point.
        For multi-tile entities, if any occupied tile is within the cone, the entity is affected."""
        affected = []
        attacker_entity = game_state.get_entity(context["attacker_id"])
        if not attacker_entity:
            return []
        attacker_pos = attacker_entity.get("position")
        if not attacker_pos:
            return []

        attacker_pos_tuple = (attacker_pos.x, attacker_pos.y)
        impact_pos = context.get("impact_pos", origin_pos)

        # Vector representing the cone's central axis is from attacker to impact point
        direction_vec = (impact_pos[0] - attacker_pos_tuple[0], impact_pos[1] - attacker_pos_tuple[1])

        # Normalize the direction vector
        vec_len = sqrt(direction_vec[0]**2 + direction_vec[1]**2)
        if vec_len == 0:
             # This can happen in melee if attacker is at the same spot as impact.
             # Fallback: use attacker's orientation if available.
             attacker_char_ref = attacker_entity.get("character_ref")
             attacker_char = attacker_char_ref.character if attacker_char_ref else None
             orientation = getattr(attacker_char, 'orientation', 'up') if attacker_char else 'up'
             orient_map = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
             direction_vec = orient_map.get(orientation, (0, -1))
             vec_len = 1

        norm_direction_vec = (direction_vec[0] / vec_len, direction_vec[1] / vec_len)

        # The cone originates from the impact point for damage calculation
        cone_origin = impact_pos

        for entity_id, entity_pos_tuple in game_state.terrain.entity_positions.items():
            if entity_id in [context["attacker_id"], context["primary_target_id"]]:
                continue # Skip attacker and primary target

            # --- Multi-tile support: get all occupied tiles ---
            entity = game_state.get_entity(entity_id)
            if hasattr(entity, 'get_occupied_tiles'):
                occupied_tiles = entity.get_occupied_tiles()
            elif hasattr(entity, 'occupied_tiles'):
                occupied_tiles = entity.occupied_tiles
            else:
                occupied_tiles = [entity_pos_tuple]

            # If any tile is in the cone, mark as affected
            for tile in occupied_tiles:
                dist_from_origin = _get_distance(cone_origin, tile)
                if dist_from_origin > self.length:
                    continue
                angle_check_vec = (tile[0] - attacker_pos_tuple[0], tile[1] - attacker_pos_tuple[1])
                angle_check_len = sqrt(angle_check_vec[0]**2 + angle_check_vec[1]**2)
                if angle_check_len == 0:
                    continue
                norm_target_vec = (angle_check_vec[0] / angle_check_len, angle_check_vec[1] / angle_check_len)
                dot_product = norm_direction_vec[0] * norm_target_vec[0] + norm_direction_vec[1] * norm_target_vec[1]
                dot_product = max(-1.0, min(1.0, dot_product))
                angle_rad = np.arccos(dot_product)
                angle_deg = degrees(angle_rad)
                if angle_deg <= self.angle / 2:
                    affected.append(entity_id)
                    break  # No need to check other tiles for this entity

        return affected
