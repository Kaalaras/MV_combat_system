"""Battle map visualization utilities for manual testing.

This module re-exports the production battle map utilities for backwards
compatibility with existing test code.
"""

# Import all functions from the production utils
from utils.battle_map_utils import (
    get_entity_color,
    draw_battle_map,
    get_battle_subfolder,
    get_unique_battle_subfolder,
    assemble_gif
)
