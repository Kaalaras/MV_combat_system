from utils.logger import log_calls
from entities.base_object import BaseObject
import copy
import json
from utils.character_utils import GENERATION_LIMIT, find_position_trait_in_dictionary
from typing import Callable
from math import ceil
from utils.condition_utils import evaluate_weakened_damage_based  # new import

class Character(BaseObject):
    __slots__ = (
        "name", "clan", "generation", "archetype",
        "traits", "base_traits", "clan_disciplines",
        "_health_damage", "_willpower_damage", "states",
        "orientation", "team", "alliance","is_ai_controlled", "ai_script","sprint_distance",
        "absorption", "toggle_opportunity_attack", "sprite_path", "hunger",  # add hunger & sprite_path to slots
        "_max_health_mod_total", "initiative_mod"  # cumulative temporary max health modifications + initiative mod
    )

    def __init__(self, name: str = '', clan: str = '', generation: int = 13,
                 archetype: str = '', traits=None, base_traits=None,
                 clan_disciplines=None, sprite_path: str=  None, team: str = None, is_ai_controlled: bool=False, ai_script: Callable=None,) -> None:
        super().__init__()
        self.name = name
        self.clan = clan
        self.archetype = archetype
        self.generation = generation
        self.traits = traits or {}  # à compléter selon création perso
        self.base_traits = base_traits or {}
        self.clan_disciplines = clan_disciplines or {}
        self._health_damage = {'superficial': 0, 'aggravated': 0}
        self._willpower_damage = {'superficial': 0, 'aggravated': 0}
        self.states = set()
        self.orientation = 'up'
        self.sprite_path = sprite_path
        self.team = team
        self.alliance = {}  # character_id -> "ally"/"neutral"/"enemy"
        self.is_ai_controlled = is_ai_controlled
        self.ai_script = ai_script
        self.sprint_distance = 0
        self.absorption = 0  # Default absorption value
        self.toggle_opportunity_attack = True  # New gameplay toggle (can suppress reactions / AoO)
        self.hunger = 0  # Default hunger (only meaningful for ghouls / vampires)
        self._max_health_mod_total = 0  # running sum of active max health modifiers
        self.initiative_mod = 0  # cumulative initiative modifiers

    @log_calls
    def modify_points(self, trait: str, points: int) -> bool:
        """Modifie les points d'un trait, en respectant les limites."""
        try:
            keys = find_position_trait_in_dictionary(trait)
            current_trait = self.traits
            current_base_trait = self.base_traits

            for key in keys[:-1]:
                current_trait = current_trait[key]
                current_base_trait = current_base_trait[key]

            trait_name = keys[-1]
            new_value = current_trait[trait_name] + points

            if not (current_base_trait[trait_name] <= new_value <= self.generation_limit):
                return False

            current_trait[trait_name] = new_value
            return True

        except Exception as e:
            print(f"Error modifying {trait}: {e}")
            return False

    @log_calls
    def take_damage(self, amount: int, damage_type: str = 'superficial', target: str = 'health') -> None:
        """Apply damage to health or willpower, handling overflow and conversion.
        Returns lists of (added_conditions, removed_conditions) for dynamic evaluation.
        Supports magic variants by normalizing '*_magic' suffix.
        """
        if damage_type.endswith('_magic'):
            damage_type = damage_type.replace('_magic', '')
        damage = self._health_damage if target == 'health' else self._willpower_damage
        max_value = self.max_health if target == 'health' else self.max_willpower
        if damage_type == 'superficial':
            damage['superficial'] += amount
            max_value = self.max_health if target == 'health' else self.max_willpower
            total = damage['superficial'] + damage['aggravated']
            if total > max_value:
                # Overflow rule: track collapses to full aggravated, superficial cleared
                damage['aggravated'] = max_value
                damage['superficial'] = 0
        elif damage_type == 'aggravated':
            # Add aggravated, replacing superficial if needed
            to_add = amount
            if damage['superficial'] >= to_add:
                damage['superficial'] -= to_add
                damage['aggravated'] += to_add
            else:
                to_add -= damage['superficial']
                damage['aggravated'] += damage['superficial']
                damage['superficial'] = 0
                damage['aggravated'] += to_add
            # Cap aggravated at max
            if damage['aggravated'] > max_value:
                damage['aggravated'] = max_value
        self._check_affliction(target)

    @log_calls
    def heal_damage(self, amount: int, damage_type: str = 'superficial', target: str = 'health') -> None:
        """Heal superficial or aggravated damage, prioritizing superficial first.
        Returns lists of (added_conditions, removed_conditions) for dynamic evaluation.
        """
        damage = self._health_damage if target == 'health' else self._willpower_damage
        if damage_type == 'superficial':
            healed = min(amount, damage['superficial'])
            damage['superficial'] -= healed
        elif damage_type == 'aggravated':
            healed = min(amount, damage['aggravated'])
            damage['aggravated'] -= healed
        self._check_affliction(target)

    def _check_affliction(self, target: str):
        """Evaluate dynamic damage-based conditions (e.g., Weakened variants)."""
        evaluate_weakened_damage_based(self)

    def print_health_state(self):
        print(f"Health: {self._health_damage['superficial']} superficial, {self._health_damage['aggravated']} aggravated / {self.max_health} max")

    def print_willpower_state(self):
        print(f"Willpower: {self._willpower_damage['superficial']} superficial, {self._willpower_damage['aggravated']} aggravated / {self.max_willpower} max")

    @property
    def generation_limit(self) -> int:
        return GENERATION_LIMIT[self.generation]

    @property
    def base_max_health(self) -> int:
        return 3 + self.traits.get("Attributes", {}).get("Physical", {}).get("Stamina", 0)

    @property
    def max_health(self) -> int:
        # Effective max health after temporary modifiers (can't go below 1)
        return max(1, self.base_max_health + self._max_health_mod_total)

    @property
    def max_willpower(self) -> int:
        return 3 + self.traits.get("Virtues", {}).get("Courage", 0)

    @property
    def is_dead(self):
        return self._health_damage['aggravated'] >= self.max_health or self._willpower_damage['aggravated'] >= self.max_willpower

    @log_calls
    def copy(self):
        return Character(
            name=self.name,
            clan=self.clan,
            generation=self.generation,
            archetype=self.archetype,
            traits=copy.deepcopy(self.traits),
            base_traits=copy.deepcopy(self.base_traits),
            clan_disciplines=copy.deepcopy(self.clan_disciplines)
        )

    @log_calls
    def save_to_json(self) -> str:
        return json.dumps({slot: getattr(self, slot) for slot in self.__slots__}, indent=4, sort_keys=True)

    @log_calls
    def set_orientation(self, direction: str) -> None:
        """
        Définit l'orientation du personnage parmi : 'up', 'down', 'left', 'right'.
        """
        valid_directions = {"up", "down", "left", "right"}
        if direction not in valid_directions:
            raise ValueError(f"Invalid orientation: {direction}. Must be one of {valid_directions}.")
        self.orientation = direction

    @log_calls
    def rotate_left(self) -> None:
        """Tourne l'orientation du personnage vers la gauche (anti-horaire)."""
        rotation_map = {"up": "left", "left": "down", "down": "right", "right": "up"}
        self.orientation = rotation_map[self.orientation]

    @log_calls
    def rotate_right(self) -> None:
        """Tourne l'orientation du personnage vers la droite (horaire)."""
        rotation_map = {"up": "right", "right": "down", "down": "left", "left": "up"}
        self.orientation = rotation_map[self.orientation]

    def set_team(self, team: str):
        self.team = team

    def set_alliance(self, char_id: str, status: str):
        self.alliance[char_id] = status

    def get_alliance(self, char_id: str) -> str:
        return self.alliance.get(char_id, "neutral")

    def calculate_sprint_distance(self) -> int:
        """Calculate sprint distance (Dex based). Safe against missing keys.
        Previously used a hard-coded formula; kept but with safe access.
        """
        dex = self.traits.get("Attributes", {}).get("Physical", {}).get("Dexterity", 0)
        # Ceiling of 1.5 * Dex + 10 (design note) – ensure minimum baseline
        self.sprint_distance = max(1, ceil(dex * 1.5 + 10))
        return self.sprint_distance
