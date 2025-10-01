# core/cover_factory.py
# Factory utilities for spawning cover entities.
from typing import Optional
from ecs.components.position import PositionComponent
from ecs.components.cover import CoverComponent
from ecs.components.structure import StructureComponent
from ecs.components.team import TeamComponent
import itertools

# Simple incremental id generator for unnamed covers
_cover_counter = itertools.count(1)

def spawn_cover(game_state, cover_type: str, x: int, y: int, cover_id: Optional[str] = None) -> str:
    """Create and register a cover entity on the terrain.

    Args:
        game_state: Active GameState instance.
        cover_type: 'light', 'heavy', or 'retrenchment'.
        x,y: Cell coordinates where the cover occupies (1x1 tile).
        cover_id: Optional explicit entity id. If omitted, auto-generated.

    Returns:
        The entity id of the spawned cover.
    """
    if cover_id is None:
        cover_id = f"cover_{cover_type}_{next(_cover_counter)}"
    # Build components
    position = PositionComponent(x, y, 1, 1)
    cover_comp = CoverComponent.create(cover_type)
    structure = StructureComponent(vigor_max=6, armor_level=8)
    components = {
        'position': position,
        'cover': cover_comp,
        'structure': structure,
        # Conditions list to reflect 'decor' immobilized, armored, etc.
        'conditions': set(['decor']),
        'team': TeamComponent(None),
    }
    game_state.add_entity(cover_id, components)
    # Occupy terrain tile (blocks movement & LoS rays like other entities)
    if getattr(game_state, 'terrain', None):
        game_state.terrain.add_entity(cover_id, x, y)
    if getattr(game_state,'bump_blocker_version',None):
        game_state.bump_blocker_version()
    return cover_id
