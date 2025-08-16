# utils/helper_functions.py

from typing import List, Tuple

def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """
    Calcule la distance de Manhattan entre deux points.
    """
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def adjacent_cells(x: int, y: int) -> List[Tuple[int, int]]:
    """
    Retourne les coordonnées des 8 cases adjacentes (orthogonales + diagonales).
    """
    return [
        (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1),
        (x + 1, y + 1), (x + 1, y - 1), (x - 1, y + 1), (x - 1, y - 1)
    ]

def orthogonal_adjacent_cells(x: int, y: int) -> List[Tuple[int, int]]:
    """
    Retourne les coordonnées des 4 cases orthogonales (haut, bas, gauche, droite).
    """
    return [
        (x + 1, y),
        (x - 1, y),
        (x, y + 1),
        (x, y - 1)
    ]
