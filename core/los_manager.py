from dataclasses import dataclass
from typing import Tuple, List, Dict, Any
import numpy as np

"""This module manages line-of-sight (LoS) between entities on a terrain grid.

It has been extended to optionally leverage the Python bindings of libtcod
(`python-tcod`) to compute permissive field-of-view (FOV) masks. When tcod is
available, a FOV map is constructed from the terrain and entity positions and
cached. This provides a quick pre-check to determine if a target cell is even
visible before performing expensive ray‐casting logic. If tcod is not
installed, the original Bresenham/sampling-based LoS logic continues to be
used without modification.

Key implementation notes:

* The FOV map is rebuilt whenever the terrain changes or an entity moves.
* Visibility masks are cached per origin to avoid recomputation on repeated
  queries in the same game state.
* The permissive FOV algorithm (level 8) is used to approximate a realistic
  "peek around the corner" behaviour while remaining symmetric.
* When computing FOV via `tcod.map.compute_fov`, the `pov` argument is
  provided as a tuple `(x, y)` rather than two separate positional arguments.
  Passing both positional x/y and a keyword radius at the same time would
  otherwise trigger a `TypeError: compute_fov() got multiple values for
  argument 'radius'` error. This patch addresses that issue by using the
  correct call signature.
"""

from core.event_bus import EventBus
from core.game_state import GameState
from core.terrain_manager import Terrain, EFFECT_DARK_TOTAL, EFFECT_DARK_LOW  # extended import
from utils.condition_utils import INVISIBLE, SEE_INVISIBLE, NIGHT_VISION_PARTIAL, NIGHT_VISION_TOTAL

# Attempt to import tcod and constants for permissive field of view.  If tcod
# isn't available, the variables below will be set accordingly and the
# fallback Bresenham-based LoS algorithm will be used.
try:
    import tcod  # type: ignore
    # Import libtcodpy for constants.  The tcod module will stop exposing
    # these constants directly in a future release.  See
    # https://python-tcod.readthedocs.io for details.
    try:
        from tcod import libtcodpy as _libtcod
        FOV_PERMISSIVE_8 = _libtcod.FOV_PERMISSIVE_8  # type: ignore
    except Exception:
        # Fallback: still try to get the constant from tcod.constants or tcod
        try:
            from tcod import constants as _tcod_constants
            FOV_PERMISSIVE_8 = _tcod_constants.FOV_PERMISSIVE_8  # type: ignore
        except Exception:
            FOV_PERMISSIVE_8 = getattr(tcod, 'FOV_PERMISSIVE_8', 0)  # type: ignore
    # Newer python-tcod deprecates the Map class; we avoid importing it
    # and instead work directly with a transparency array + compute_fov.
    _TcodMap = None  # type: ignore
    _HAS_TCOD: bool = True
except Exception:
    # If tcod isn't available, mark the flag so that the FOV logic can be
    # bypassed.  Assign default stub values to satisfy type checkers.
    tcod = None  # type: ignore  # noqa: F401
    FOV_PERMISSIVE_8 = 0  # type: ignore  # noqa: F401
    _TcodMap = None  # type: ignore  # noqa: F401
    _HAS_TCOD = False

EVT_WALL_ADDED = "wall_added"
EVT_ENTITY_MOVED = "entity_moved"
EVT_WALL_REMOVED = "wall_removed"
EVT_COVER_DESTROYED = "cover_destroyed"


@dataclass
class VisibilityEntry:
    terrain_v: int
    blocker_v: int
    has_los: bool
    partial_wall: bool
    cover_sum: int
    wall_bonus: int
    total_cover: int
    total_rays: int
    clear_rays: int
    cover_ids: Tuple[str, ...]
    intervening_cells: Tuple[Tuple[int,int], ...]


class LineOfSightManager:
    """Unified LOS + cover visibility cache with versioned pair entries."""
    def __init__(self, game_state: GameState, terrain_manager: Terrain, event_bus: EventBus, los_granularity: int = 10, sampling_mode: str = 'sparse'):
        self.game_state = game_state
        self.terrain = terrain_manager
        self.event_bus = event_bus
        self.event_bus.subscribe(EVT_WALL_ADDED, self._on_env_changed)
        self.event_bus.subscribe(EVT_WALL_REMOVED, self._on_env_changed)
        self.event_bus.subscribe(EVT_ENTITY_MOVED, self._on_entity_moved)
        self.event_bus.subscribe(EVT_COVER_DESTROYED, self._on_env_changed)
        self._pair_cache: Dict[Tuple[Tuple[int,int],Tuple[int,int]], VisibilityEntry] = {}
        self.los_granularity = los_granularity
        self._edge_offsets = self._build_edge_offsets(los_granularity)
        self.sampling_mode = sampling_mode  # 'sparse' or 'full'
        self.stats = {
            'pair_recomputes': 0,
            'rays_cast_total': 0,
            'cache_hits': 0,
            'fastpath_skips': 0
        }

        # Internal FOV state.  When tcod is available, a FOV map and a
        # per-origin cache of visibility masks are maintained.  These are
        # invalidated when the terrain or entity positions change.  When
        # _HAS_TCOD is False these remain unused.
        if _HAS_TCOD:
            # Stored transparency ndarray (height, width) with True for transparent cells.
            self._fov_map = None  # type: Any  # kept name for backward compatibility; now ndarray
            self._fov_cache: Dict[Tuple[int, int], Any] = {}

    # ---- Event hooks ----
    def _on_env_changed(self, **kwargs):
        self._pair_cache.clear()
        # Invalidate FOV caches when the environment changes (e.g. walls
        # added/removed, covers destroyed).  Only relevant if tcod FOV is in
        # use.  Clearing both the FOV map and per-origin masks ensures that
        # subsequent calls rebuild the map with the latest terrain state.
        if _HAS_TCOD:
            self._fov_map = None
            self._fov_cache.clear()

    def _on_entity_moved(self, **kwargs):
        self._pair_cache.clear()
        if _HAS_TCOD:
            # When entities move they may reveal or obstruct lines of sight.
            # Rebuild the FOV map and masks accordingly.
            self._fov_map = None
            self._fov_cache.clear()

    # ---- Public API ----
    def invalidate_cache(self, **kwargs):
        self._pair_cache.clear()

    def get_visibility_entry(self, a: Tuple[int,int] | Any, b: Tuple[int,int] | Any) -> VisibilityEntry:
        if hasattr(a,'x') and hasattr(a,'y'): a=(a.x,a.y)
        if hasattr(b,'x') and hasattr(b,'y'): b=(b.x,b.y)
        if a == b:
            gv = getattr(self.game_state,'terrain_version',0)
            bv = getattr(self.game_state,'blocker_version',0)
            return VisibilityEntry(gv,bv,True,False,0,0,0,0,0,(),())
        key = (a,b) if a<=b else (b,a)
        gv = getattr(self.game_state,'terrain_version',0)
        bv = getattr(self.game_state,'blocker_version',0)
        entry = self._pair_cache.get(key)
        if entry and entry.terrain_v==gv and entry.blocker_v==bv:
            self.stats['cache_hits'] += 1
            return entry
        entry = self._recompute_visibility_entry(a,b, gv, bv)
        self._pair_cache[key]=entry
        return entry

    def has_los(self, start_pos, end_pos) -> bool:
        entry = self.get_visibility_entry(start_pos, end_pos)
        return entry.has_los

    def visibility_profile(self, start_pos, end_pos) -> Tuple[int,int]:
        entry = self.get_visibility_entry(start_pos,end_pos)
        if entry.total_rays==0:
            return (1,1)
        return (entry.total_rays, entry.clear_rays)

    def can_see(self, attacker_id: str, defender_id: str) -> bool:
        att = self.game_state.get_entity(attacker_id)
        dfn = self.game_state.get_entity(defender_id)
        if not att or not dfn or 'position' not in att or 'position' not in dfn:
            return False
        apos = att['position']; dpos = dfn['position']
        att_states = set()
        def_states = set()
        if 'character_ref' in att:
            att_states = getattr(att['character_ref'].character, 'states', set())
        if 'character_ref' in dfn:
            def_states = getattr(dfn['character_ref'].character, 'states', set())
        # Darkness gating
        if hasattr(self.terrain, 'has_effect'):
            attacker_dark_total = self.terrain.has_effect(apos.x, apos.y, EFFECT_DARK_TOTAL)
            defender_dark_total = self.terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_TOTAL)
            if attacker_dark_total and NIGHT_VISION_TOTAL not in att_states:
                return False
            if defender_dark_total and NIGHT_VISION_TOTAL not in att_states:
                return False
        # Geometric LOS
        if not self.has_los((apos.x, apos.y), (dpos.x, dpos.y)):
            return False
        # Invisibility
        if INVISIBLE in def_states and SEE_INVISIBLE not in att_states:
            return False
        return True

    # New helper for darkness penalty (attack roll system can call this)
    
    def get_darkness_attack_modifier(self, attacker_id: str, defender_id: str) -> int:
        """Return attack modifier from darkness, delegating to VisionSystem when available.

        Prefer VisionSystem.get_attack_modifier(attacker_id, defender_id) if the game_state
        exposes one; otherwise fall back to local terrain-effect logic (-1 for low darkness
        if the attacker lacks partial NV; 0 otherwise). We never apply a penalty for total
        darkness here because can_see() should already gate that via LoS/NV rules.
        """
        # 1) Delegate to VisionSystem if present and exposes the method
        vision_sys = getattr(self.game_state, 'vision_system', None)
        if vision_sys and hasattr(vision_sys, 'get_attack_modifier'):
            try:
                return int(vision_sys.get_attack_modifier(attacker_id, defender_id)) or 0
            except Exception:
                # Fall through to local fallback logic
                pass

        # 2) Fallback: compute from terrain effects + attacker states
        terrain = getattr(self.game_state, 'terrain', None)
        if not terrain or not hasattr(terrain, 'has_effect'):
            return 0
        attacker = self.game_state.get_entity(attacker_id)
        defender = self.game_state.get_entity(defender_id)
        if not attacker or not defender or 'position' not in attacker or 'position' not in defender:
            return 0
        dpos = defender['position']
        att_states = set()
        if 'character_ref' in attacker:
            att_states = getattr(attacker['character_ref'].character, 'states', set()) or set()

        # Total darkness: LoS/vision rules should have blocked earlier; do not stack extra penalty.
        if terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_TOTAL):
            return 0

        # Low darkness: -1 if attacker lacks partial NV (or total NV)
        if terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_LOW):
            if (NIGHT_VISION_PARTIAL in att_states) or (NIGHT_VISION_TOTAL in att_states):
                return 0
            return -1

        return 0
        if not terrain or not hasattr(terrain, 'has_effect'):
            return 0
        attacker = self.game_state.get_entity(attacker_id)
        defender = self.game_state.get_entity(defender_id)
        if not attacker or not defender or 'position' not in attacker or 'position' not in defender:
            return 0
        dpos = defender['position']
        att_states = set()
        if 'character_ref' in attacker:
            att_states = getattr(attacker['character_ref'].character, 'states', set())
        if terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_TOTAL):
            # Already blocked in can_see unless attacker has total night vision; treat as no additional mod
            return 0
        if terrain.has_effect(dpos.x, dpos.y, EFFECT_DARK_LOW):
            if NIGHT_VISION_PARTIAL in att_states or NIGHT_VISION_TOTAL in att_states:
                return 0
            return -1
        return 0

    def reset_stats(self):
        for k in self.stats:
            self.stats[k] = 0

    def get_stats(self):
        return dict(self.stats)

    def set_sampling_mode(self, mode: str):
        if mode in ('sparse','full'):
            self.sampling_mode = mode
        return self.sampling_mode

    # ---- Internals ----
    def _build_edge_offsets(self, granularity: int) -> List[Tuple[float,float]]:
        if granularity == 0:
            return [(0,0),(1,0),(1,1),(0,1)]
        pts = []
        corners = [(0,0),(1,0),(1,1),(0,1)]
        for i in range(4):
            p1 = corners[i]; p2 = corners[(i+1)%4]
            pts.append(p1); pts.append(p2)
            for j in range(1, granularity+1):
                f = j/(granularity+1)
                pts.append((p1[0]+f*(p2[0]-p1[0]), p1[1]+f*(p2[1]-p1[1])))
        seen=set(); uniq=[]
        for p in pts:
            if p not in seen:
                seen.add(p); uniq.append(p)
        return uniq

    # ------------------------------------------------------------------
    # FOV helper methods (tcod integration)
    # ------------------------------------------------------------------
    def _build_fov_map(self) -> Any:
        """Build and return a transparency ndarray (height, width) boolean.

        True = transparent, False = opaque. Only terrain walls are marked
        opaque. Dynamic entities & cover are left transparent so that the
        detailed ray logic, not the coarse FOV, determines partial cover.
        """
        try:
            width = int(getattr(self.terrain, 'width', 0))
            height = int(getattr(self.terrain, 'height', 0))
        except Exception:
            return None
        transparency = np.ones((height, width), dtype=bool)
        for (wx, wy) in getattr(self.terrain, 'walls', []):
            if 0 <= wy < height and 0 <= wx < width:
                transparency[wy, wx] = False
        return transparency

    def _get_fov_for_origin(self, origin: Tuple[int, int]) -> Any:
        """Return a visibility mask for the given origin using permissive FOV.

        If tcod is not available, this returns None.  Otherwise it ensures
        that the FOV map is up-to-date and then computes or retrieves a
        cached visibility mask for the origin.  The returned mask is a 2D
        boolean NumPy array of shape `(height, width)` where a True value
        indicates that the cell is visible from `origin` according to the
        permissive FOV algorithm.
        """
        # If tcod isn't available, skip FOV and return None.
        if not _HAS_TCOD:
            return None
        ox, oy = origin
        # Attempt to coerce the terrain dimensions to integers.  In some unit
        # tests, width and height may be MagicMock objects.  If conversion
        # fails, FOV will be disabled for this call.
        try:
            width = int(getattr(self.terrain, 'width'))
            height = int(getattr(self.terrain, 'height'))
        except Exception:
            return None
        # Build the base FOV map if needed.
        if self._fov_map is None:
            self._fov_map = self._build_fov_map()
            if self._fov_map is None:
                return None
            self._fov_cache.clear()
        # Check the cache for this origin.
        vis_mask = self._fov_cache.get((ox, oy))
        if vis_mask is not None:
            return vis_mask
        # Compute the FOV from this origin.  Use the Map method when available
        # to avoid parameter ambiguity with the radius.  radius=0 means
        # unlimited distance; light_walls=True illuminates walls as well.
        try:
            vis_mask = tcod.map.compute_fov(self._fov_map, (oy, ox), 0, True, FOV_PERMISSIVE_8)  # type: ignore
        except Exception:
            vis_mask = None
        # Cache the computed mask for this origin (even if None).
        self._fov_cache[(ox, oy)] = vis_mask
        return vis_mask

    def _get_los_points(self, pos: Tuple[int,int]) -> set[Tuple[float,float]]:
        x,y=pos
        return {(x+dx, y+dy) for dx,dy in self._edge_offsets}

    def benchmark_visibility(self, a: Tuple[int,int], b: Tuple[int,int], mode: str) -> VisibilityEntry:
        """Compute visibility for a pair using specified mode (does not cache)."""
        prev_mode = self.sampling_mode
        self.sampling_mode = mode
        entry = self._recompute_visibility_entry(a,b, getattr(self.game_state,'terrain_version',0), getattr(self.game_state,'blocker_version',0))
        self.sampling_mode = prev_mode
        return entry

    def _recompute_visibility_entry(self, a: Tuple[int,int], b: Tuple[int,int], gv:int, bv:int) -> VisibilityEntry:
        self.stats['pair_recomputes'] += 1
        line = self._bresenham_line(a[0],a[1],b[0],b[1])
        walls_present=False; clear_between=False
        cover_ids: List[str] = []; cover_sum=0; intervening: List[Tuple[int,int]] = []
        terrain = self.terrain
        if len(line) <= 2:
            self.stats['fastpath_skips'] += 1
            return VisibilityEntry(gv,bv,True,False,0,0,0,0,0,(),tuple(line))
        for cell in line[1:-1]:
            intervening.append(cell)
            if cell in terrain.walls: walls_present=True
            else: clear_between=True
            occ_id = terrain.grid.get(cell) if hasattr(terrain,'grid') else None
            if occ_id:
                ent = self.game_state.get_entity(occ_id)
                if ent:
                    if 'character_ref' in ent and INVISIBLE in getattr(ent['character_ref'].character,'states', set()):
                        continue
                    if 'cover' in ent:
                        cover_comp = ent['cover']
                        cover_ids.append(occ_id)
                        cover_sum += getattr(cover_comp,'bonus',0)

        # Optional FOV pre-check using tcod.  If the tcod FOV implementation is
        # available, compute a visibility mask for the origin and test if the
        # destination cell is visible at all.  This helps avoid expensive
        # ray-casting when the FOV algorithm has already determined that the
        # target is fully obscured by obstacles.  The mask is indexed as
        # [y, x], hence we use b[1] and b[0] respectively.
        # NOTE: If there are walls directly on the Bresenham path we *skip*
        # this early rejection so that partial-wall logic can determine
        # whether a partial cover (+2) situation applies instead of treating
        # the line as fully blocked.
        if _HAS_TCOD and not walls_present:
            vis_mask = self._get_fov_for_origin(a)
            # Only proceed if a mask was successfully computed.
            if vis_mask is not None:
                bx, by = b
                try:
                    if not vis_mask[by, bx]:
                        total_cover = cover_sum
                        return VisibilityEntry(gv, bv, False, False, cover_sum, 0, total_cover, 0, 0, tuple(cover_ids), tuple(intervening))
                except Exception:
                    pass
        if walls_present and not clear_between:
            self.stats['fastpath_skips'] += 1
            total_cover = cover_sum
            return VisibilityEntry(gv,bv,False,False,cover_sum,0,total_cover,0,0,tuple(cover_ids),tuple(intervening))
        partial_wall_candidate = walls_present and clear_between
        wall_bonus = 0
        has_los = True
        total_rays = 0
        clear_rays = 0
        if partial_wall_candidate:
            if self.sampling_mode == 'full':
                start_offsets = list(self._get_los_points(a))
                end_offsets = list(self._get_los_points(b))
                for sp in start_offsets:
                    for ep in end_offsets:
                        total_rays += 1
                        if self._is_ray_clear(sp,ep):
                            clear_rays +=1
                has_los = clear_rays>0
                wall_bonus = 2 if has_los and clear_rays < total_rays else 0
                if wall_bonus == 0 and has_los and clear_rays==total_rays:
                    partial_wall_candidate = False
                self.stats['rays_cast_total'] += total_rays
            else:  # sparse mode
                start_offsets = list(self._get_los_points(a))
                end_offsets = list(self._get_los_points(b))
                def corner_set(base, origin):
                    ox,oy = origin
                    targets = [(ox+dx,oy+dy) for dx,dy in [(0,0),(1,0),(1,1),(0,1)]]
                    return [p for p in base if p in targets] or base[:4]
                sx_set = corner_set(start_offsets, a)
                ey_set = corner_set(end_offsets, b)
                seen_blocked=False; seen_clear=False
                for sp in sx_set:
                    for ep in ey_set:
                        total_rays += 1
                        if self._is_ray_clear(sp,ep):
                            clear_rays +=1; seen_clear=True
                        else:
                            seen_blocked=True
                        if seen_blocked and seen_clear:
                            break
                    if seen_blocked and seen_clear:
                        break
                if seen_blocked and seen_clear:
                    wall_bonus = 2; has_los = True
                elif seen_clear and not seen_blocked:
                    # escalate sample subset of remaining
                    for sp in start_offsets:
                        if seen_blocked: break
                        for ep in end_offsets:
                            if (sp in sx_set) and (ep in ey_set): continue
                            total_rays += 1
                            if self._is_ray_clear(sp,ep):
                                clear_rays += 1
                            else:
                                seen_blocked=True
                                break
                    if seen_blocked:
                        wall_bonus = 2; has_los = True
                    else:
                        wall_bonus = 0; has_los = True; partial_wall_candidate=False
                elif seen_blocked and not seen_clear:
                    # escalate to confirm blocked
                    for sp in start_offsets:
                        if seen_clear: break
                        for ep in end_offsets:
                            if (sp in sx_set) and (ep in ey_set): continue
                            total_rays += 1
                            if self._is_ray_clear(sp,ep):
                                clear_rays +=1; seen_clear=True; break
                    if seen_clear:
                        wall_bonus = 2; has_los = True
                    else:
                        has_los = False; partial_wall_candidate=False
                else:
                    has_los = True; partial_wall_candidate=False
                self.stats['rays_cast_total'] += total_rays
        if not partial_wall_candidate:
            self.stats['fastpath_skips'] += 1
        partial_wall = partial_wall_candidate and has_los
        if partial_wall_candidate and not has_los:
            # Edge case: single thin wall cell caused every integer-rounded ray to hit.
            # Treat as partial cover (grant LOS + wall bonus) since there are
            # clear cells on both sides (clear_between True earlier).
            has_los = True
            partial_wall = True
            wall_bonus = 2
        if not partial_wall:
            wall_bonus = 0
        total_cover = cover_sum + wall_bonus
        return VisibilityEntry(gv,bv,has_los,partial_wall,cover_sum,wall_bonus,total_cover,total_rays,clear_rays,tuple(cover_ids),tuple(intervening))

    def _is_ray_clear(self, start_coord: Tuple[float,float], end_coord: Tuple[float,float]) -> bool:
        x1,y1 = start_coord; x2,y2 = end_coord
        ix1,iy1 = int(x1),int(y1); ix2,iy2 = int(x2),int(y2)
        dx = abs(ix2-ix1); dy = -abs(iy2-iy1)
        sx = 1 if ix1<ix2 else -1; sy = 1 if iy1<iy2 else -1
        err = dx + dy
        attacker_cell=(int(start_coord[0]),int(start_coord[1])); target_cell=(int(end_coord[0]),int(end_coord[1]))
        terrain = self.terrain
        while True:
            if terrain.is_wall(ix1,iy1) and (ix1,iy1) not in (attacker_cell,target_cell):
                return False
            occ_id = terrain.grid.get((ix1,iy1)) if hasattr(terrain,'grid') else None
            if occ_id and (ix1,iy1) not in (attacker_cell,target_cell):
                ent = self.game_state.get_entity(occ_id)
                if ent:
                    if 'character_ref' in ent:
                        ch = ent['character_ref'].character
                        if INVISIBLE in getattr(ch,'states', set()):
                            pass
                        else:
                            return False
                    elif 'cover' in ent:
                        return False
            if ix1==ix2 and iy1==iy2: break
            e2 = 2*err
            if e2 >= dy:
                err += dy; ix1 += sx
            if e2 <= dx:
                err += dx; iy1 += sy
        return True

    def _bresenham_line(self, x0:int, y0:int, x1:int, y1:int) -> List[Tuple[int,int]]:
        pts=[]; dx=abs(x1-x0); dy=-abs(y1-y0); sx=1 if x0<x1 else -1; sy=1 if y0<y1 else -1; err=dx+dy
        while True:
            pts.append((x0,y0))
            if x0==x1 and y0==y1: break
            e2=2*err
            if e2>=dy:
                if x0==x1: break
                err+=dy; x0+=sx
            if e2<=dx:
                if y0==y1: break
                err+=dx; y0+=sy
        return pts
