from dataclasses import dataclass

@dataclass
class CoverComponent:
    """Represents a cover object occupying (typically) one tile.

    cover_type: one of 'light','heavy','retrenchment'.
    bonus: integer modifier applied to defender defense successes when this cover
           contributes to a ranged attack defense resolution. (Can be negative.)
           Mapping per spec (French doc):
             - light  : -1 die
             - heavy  : 0 dice
             - retrenchment : +1 die
    A wall that partially hides the defender is treated separately (+2 dice) and
    is not represented by this component (walls are terrain level).
    """
    cover_type: str
    bonus: int
    destructible: bool = True

    @staticmethod
    def create(cover_type: str) -> 'CoverComponent':
        mapping = {
            'light': -1,
            'heavy': 0,
            'retrenchment': 1,
        }
        if cover_type not in mapping:
            raise ValueError(f"Invalid cover_type {cover_type}")
        return CoverComponent(cover_type=cover_type, bonus=mapping[cover_type])

