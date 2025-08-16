"""
TerrainComponent - Data container for terrain information.
This component stores all terrain-related data but contains no logic.
All modifications should be done through TerrainManager.
"""
from typing import Dict, List, Set, Tuple, Optional
import numpy as np


class TerrainComponent:
    """
    Data container for terrain information.

    This class holds all terrain state data but contains no game logic.
    It should be modified only through TerrainManager methods.
    """

    def __init__(self, grid_size: Tuple[int, int]):
        """
        Initialize a new terrain component.

        Args:
            grid_size: A tuple (width, height) specifying the terrain dimensions
        """
        self.grid_size: Tuple[int, int] = grid_size
        self.walls: Set[Tuple[int, int]] = set()
        self.walkable_cells: Set[Tuple[int, int]] = set()
        self.entity_positions: Dict[str, Tuple[int, int]] = {}
        self.position_to_entity: Dict[Tuple[int, int], str] = {}

        # Pathfinding data
        self.precomputed_paths: Dict[Tuple[int, int], Dict[Tuple[int, int], List[Tuple[int, int]]]] = {}

    def is_within_bounds(self, position: Tuple[int, int]) -> bool:
        """
        Check if a position is within the terrain bounds.

        Args:
            position: The (x, y) position to check

        Returns:
            bool: True if position is within bounds, False otherwise
        """
        x, y = position
        width, height = self.grid_size
        return 0 <= x < width and 0 <= y < height
