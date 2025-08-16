from math import factorial

from utils.logger import log_calls
import random


class Dice:
    __slots__ = ()

    @log_calls
    def roll_die(self) -> int:
        """ Lance un seul dé D10. """
        return random.randint(1, 10)

    @log_calls
    def roll_pool(self, pool_size: int, hunger_dice: int = 0) -> dict:
        """
        Lance un pool de dés de 10 faces.
        - pool_size : nombre total de dés à jeter.
        - hunger_dice : nombre de dés de soif (doit être <= pool_size).

        Retourne un dictionnaire contenant :
          - successes
          - bestial_failures
          - critical_successes
          - hunger_bestial_successes
          - hunger_bestial_failures
        """
        if hunger_dice > pool_size:
            raise ValueError("hunger_dice cannot exceed pool_size.")

        normal_dice = pool_size - hunger_dice
        # Use random.choices for faster dice generation
        dice_results = random.choices(range(1, 11), k=pool_size)

        successes = 0
        bestial_failures = 0
        critical_successes = 0
        hunger_bestial_successes = 0
        hunger_bestial_failures = 0

        for idx, die in enumerate(dice_results):
            is_hunger = idx >= normal_dice

            if die >= 6:
                successes += 1
            if die == 10:
                if is_hunger:
                    hunger_bestial_successes += 1
                else:
                    critical_successes += 1
            if die == 1 and is_hunger:
                hunger_bestial_failures += 1
            if die == 1 and not is_hunger:
                bestial_failures += 1

        # Use integer division for combinations: n * (n-1) // 2
        new_critical_successes = critical_successes * (critical_successes - 1) // 2 if critical_successes >= 2 else 0

        print("\t\t", dice_results)

        return {
            "successes": successes,
            "bestial_failures": bestial_failures,
            "critical_successes": new_critical_successes,
            "hunger_bestial_successes": hunger_bestial_successes,
            "hunger_bestial_failures": hunger_bestial_failures
        }

