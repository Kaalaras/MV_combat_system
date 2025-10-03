# ecs/systems/ai/main.py
# -------------------------------------------------------------------------------------------------
# AI QUICK OVERVIEW (At a Glance)
# Decision order (first success stops):
#   1. Immediate Ranged  -> Safe damage now (only if no adjacent enemies & inside base range)
#   2. Immediate Melee   -> Already adjacent; strike instead of moving
#   3. Move + Ranged     -> Reposition to gain LOS / base range shot
#   4. Move + Melee      -> Close distance to enable melee
#   5. Reload            -> Only if ranged weapon empty
#   6. Strategic Retreat -> Move to tile maximizing (future DPS - incoming threats)
#   7. Take Cover        -> Minimize enemy LOS while keeping mobility options
#   8. End Turn          -> Fallback when nothing productive to do
# Supporting heuristics:
#   * Tile scoring caches metrics (dps, threat, mobility, distance)
#   * Reserved tiles prevent multiple AIs selecting same destination this round
#   * Immediate ranged attacks are skipped if target only in penalized range band
# -------------------------------------------------------------------------------------------------
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field

from . import targeting
from . import movement
from . import utils
from core.los_manager import LineOfSightManager
from interface.event_constants import CoreEvents

class TurnOrderSystemWrapper:
    """
    Wraps a turn_order_system to ensure reserved_tiles are cleared
    when start_new_round is called, even if overridden in tests.
    """
    def __init__(self, inner):
        object.__setattr__(self, '_inner', inner)
        # Mirror the reserved_tiles set
        object.__setattr__(self, 'reserved_tiles', inner.reserved_tiles)

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if name == 'start_new_round' and callable(attr):
            def wrapped(*args, **kwargs):
                # Always clear reserved_tiles first
                try:
                    self.reserved_tiles.clear()
                except Exception:
                    pass
                return attr(*args, **kwargs)
            return wrapped
        return attr

    def __setattr__(self, name, value):
        # Allow setting inner and reserved_tiles on this wrapper
        if name in ('_inner', 'reserved_tiles'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)


@dataclass
class AITurnContext:
    """
    Per-turn snapshot for a single AI entity. Pre-computes and caches
    frequently accessed data (enemies, adjacency, equipment, etc.) so
    the rest of the AI code reads cleanly and avoids recomputation.
    """
    char_id: str
    game_state: Any
    los_manager: LineOfSightManager
    movement_system: Any
    action_system: Any
    turn_order_system: Optional[Any] = None  # Made optional with default None
    event_bus: Optional[Any] = None  # Added for test compatibility

    # Cached data
    char_pos: Tuple[int, int] = field(init=False)
    enemies: List[str] = field(init=False)
    allies: List[str] = field(init=False)
    adjacent_enemies: List[str] = field(init=False)
    engaged_enemies: List[str] = field(init=False)
    entity: Any = field(init=False)
    equipment: Any = field(init=False)
    ranged_weapon: Any = field(init=False)
    melee_weapon: Any = field(init=False)
    metrics_cache: Dict[Tuple[int, int], Tuple[float, int, int, int]] = field(default_factory=dict, init=False)
    reserved_tiles: set = field(init=False)
    tile_static_cache: Dict[Tuple[int, int], Tuple[int, int]] = field(default_factory=dict, init=False)

    def __post_init__(self):
        # Ensure we have a valid turn_order_system
        if self.turn_order_system is None:
            class _DummyTurnOrder:
                def __init__(self):
                    self.reserved_tiles = set()
                def start_new_round(self):
                    self.reserved_tiles.clear()
            self.turn_order_system = _DummyTurnOrder()
        # Wrap to intercept start_new_round calls
        self.turn_order_system = TurnOrderSystemWrapper(self.turn_order_system)

        self.entity = self.game_state.get_entity(self.char_id)
        entity_pos = self.entity['position']

        # Handle different position formats
        if isinstance(entity_pos, tuple):
            self.char_pos = entity_pos
        elif hasattr(entity_pos, 'x') and hasattr(entity_pos, 'y'):
            self.char_pos = (entity_pos.x, entity_pos.y)
        else:
            self.char_pos = entity_pos

        self.equipment = self.entity['equipment']
        self.ranged_weapon = self.equipment.weapons.get('ranged')
        self.melee_weapon = self.equipment.weapons.get('melee')

        self.enemies = utils.get_enemies(self.game_state, self.char_id)
        self.allies = utils.get_allies(self.game_state, self.char_id)
        self.adjacent_enemies = utils.get_adjacent_enemies(self.game_state, self.enemies, self.char_id)
        self.engaged_enemies = utils.get_engaged_enemies(self.game_state, self.allies, self.enemies, self.char_id)
        self.reserved_tiles = self.turn_order_system.reserved_tiles

    def has_los(self, pos1, pos2) -> bool:
        """
        Check line of sight using the provided manager.
        For entities, this checks from the center of the source to the center of the target.
        A more complex implementation could check corner to corner.
        """
        # For multi-tile entities, a simple approach is to check from the center of the bounding boxes.
        box1 = utils.get_entity_bounding_box(self.game_state, self.char_id)

        # pos2 can be an entity's position component or a tile tuple.
        target_entity_id = None
        if not isinstance(pos2, tuple):
            for eid, entity in self.game_state.entities.items():
                if entity.get("position") is pos2:
                    target_entity_id = eid
                    break

        if target_entity_id:
            box2 = utils.get_entity_bounding_box(self.game_state, target_entity_id)
        elif isinstance(pos2, tuple):
            box2 = {'x1': pos2[0], 'y1': pos2[1], 'x2': pos2[0], 'y2': pos2[1]}
        else: # Fallback for other position-like objects
            width = getattr(pos2, 'width', 1)
            height = getattr(pos2, 'height', 1)
            box2 = {'x1': pos2.x, 'y1': pos2.y, 'x2': pos2.x + width - 1, 'y2': pos2.y + height - 1}

        center1 = ((box1['x1'] + box1['x2']) / 2, (box1['y1'] + box1['y2']) / 2)
        center2 = ((box2['x1'] + box2['x2']) / 2, (box2['y1'] + box2['y2']) / 2)

        return self.los_manager.has_los(center1, center2)


class BasicAISystem:
    """
    Lightweight tactical AI with a linear decision pipeline.

    High-level decision order (first succeeding step stops evaluation):
      1. Immediate ranged attack (only if no adjacent threats & within normal weapon range)
      2. Immediate melee attack (if already adjacent)
      3. Move then ranged attack (try to gain LOS / range)
      4. Move then melee attack (close distance to engage)
      5. Reload (if weapon empty)
      6. Strategic retreat (seek tile maximizing future offensive potential minus threat)
      7. Take cover (minimize lines of sight from nearest enemies)
      8. End turn (fallback)

    Each helper _try_* method returns True when it successfully queues at least
    one action via the event bus. Reserved tiles prevent multi-entity overlaps
    for planned movement within the same round.
    """

    def __init__(self,
                 game_state: Any,
                 movement_system: Any,
                 action_system: Any,
                 event_bus: Any = None,
                 los_manager: Optional[LineOfSightManager] = None,
                 turn_order_system: Optional[Any] = None,
                 debug: bool = True):
        """
        Initialize the AI system with required game systems.

        Args:
            game_state: The central game state containing all entities
            movement_system: System for calculating movement options
            action_system: System for executing game actions
            event_bus: Event bus for publishing action requests
            los_manager: Line of sight manager for visibility checks
            turn_order_system: System for managing turn order and reserved tiles
            debug: Whether to print debug messages
        """
        self.game_state = game_state
        self.movement_system = movement_system
        self.action_system = action_system
        self.event_bus = event_bus  # Don't default to None, keep the passed value
        self.los_manager = los_manager
        # Ensure turn_order_system always has reserved_tiles
        if turn_order_system is None:
            class _DummyTurnOrder:
                def __init__(self):
                    self.reserved_tiles = set()
                def start_new_round(self):
                    self.reserved_tiles.clear()
            self.turn_order_system = _DummyTurnOrder()
        else:
            self.turn_order_system = turn_order_system
        self.debug = debug

        if self.event_bus and hasattr(self.event_bus, "subscribe"):
            self.event_bus.subscribe("ai_take_turn", self._handle_ai_take_turn)

    def _debug(self, msg: str) -> None:
        """Print debug messages if debug mode is enabled."""
        if self.debug:
            print(f"[AI DEBUG] {msg}")

    # ---------------- Core selection helpers ----------------
    def _find_action(self, char_id: str, action_name: str) -> Optional[Any]:
        """
        Find an action by name from the available actions for a character.

        Args:
            char_id: The character's entity ID
            action_name: The name of the action to find

        Returns:
            The action object if found, None otherwise
        """
        available = self.action_system.available_actions.get(char_id, [])
        for action in available:
            if hasattr(action, 'name') and action.name == action_name:
                return action
        self._debug(f"Action '{action_name}' not found for {char_id}")
        return None

    def _calculate_future_score(self, ctx: AITurnContext, tile: Tuple[int, int]) -> float:
        """Estimate how good a tile will be next turn.
        Score = max(potential weapon DPS on any target) - (number of enemies that could melee us)."""
        menace_after = utils.count_future_threats(ctx, tile)
        dps_next = 0
        if ctx.ranged_weapon:
            for enemy_id in ctx.enemies:
                enemy_pos = ctx.game_state.get_entity(enemy_id)["position"]
                if ctx.has_los(tile, enemy_pos):
                    dps_next = max(dps_next, utils.get_potential_dps(ctx, ctx.ranged_weapon, enemy_id))
        if ctx.melee_weapon:
            for enemy_id in ctx.enemies:
                if utils.is_in_range(ctx.game_state, tile, enemy_id, 1):
                    dps_next = max(dps_next, utils.get_potential_dps(ctx, ctx.melee_weapon, enemy_id))
        return dps_next - menace_after

    def _find_best_retreat_tile(self, ctx: AITurnContext) -> Optional[Tuple[int, int]]:
        """Find the best tile to retreat to for the next turn."""
        reachable_tiles = self.movement_system.get_reachable_tiles(ctx.char_id, 15, reserved_tiles=ctx.reserved_tiles)
        best_tile = None
        best_score = float('-inf')
        for tile_x, tile_y, _ in reachable_tiles:
            tile = (tile_x, tile_y)
            if tile == ctx.char_pos:
                continue
            score = self._calculate_future_score(ctx, tile)
            if score > best_score:
                best_score = score
                best_tile = tile
        return best_tile

    def _find_best_cover_tile(self, ctx: AITurnContext) -> Optional[Tuple[int, int]]:
        """Pick tile minimizing exposure to closest enemies while keeping mobility.
        Scoring tuple: (LOS threats count, -free adjacent tiles, distance to nearest cover object)."""
        reachable_tiles = self.movement_system.get_reachable_tiles(ctx.char_id, 7, reserved_tiles=ctx.reserved_tiles)
        best_tile = None
        best_score = (float('inf'), float('inf'), float('inf'))  # (los_threat, -mobility, cover_dist)

        # Get all enemies sorted by distance to the character's current position
        enemies_by_dist = sorted(ctx.enemies, key=lambda eid: utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, eid))
        # Consider the 3 nearest enemies for LoS blocking
        n_nearest_enemies = enemies_by_dist[:3]

        if not n_nearest_enemies:
            return None  # No enemies to take cover from

        for tile_x, tile_y, _ in reachable_tiles:
            tile = (tile_x, tile_y)
            if tile == ctx.char_pos:
                continue
            # Skip tiles adjacent to any ally to avoid clustering
            if any(utils.is_in_range(ctx.game_state, tile, ally_id, 1) for ally_id in ctx.allies):
                continue

            los_threat = 0
            for enemy_id in n_nearest_enemies:
                enemy_pos = ctx.game_state.get_entity(enemy_id)["position"]
                # Handle different position formats for LoS check
                if isinstance(enemy_pos, tuple):
                    enemy_coords = enemy_pos
                elif hasattr(enemy_pos, 'x') and hasattr(enemy_pos, 'y'):
                    enemy_coords = (enemy_pos.x, enemy_pos.y)
                else:
                    enemy_coords = (enemy_pos[0], enemy_pos[1])

                # The LoS check should be from enemy to the potential tile.
                if self.los_manager.has_los(enemy_coords, tile):
                    los_threat += 1

            mobility = utils.count_free_adjacent_tiles(ctx, tile)
            # Distance to nearest obstacle for cover
            cover_dist = utils.find_closest_cover(ctx, tile)

            # Score: minimize LoS threats, maximize mobility, then minimize cover distance
            score = (los_threat, -mobility, cover_dist)

            if score < best_score:
                best_score = score
                best_tile = tile

        return best_tile

    def _compute_local_threats(self, ctx: AITurnContext) -> Dict[str, int]:
        """Compute quick threat metrics around current position.
        Returns dict with keys: melee_adjacent, enemies_within5, los_threats_current, allies_close."""
        melee_adjacent = len(ctx.adjacent_enemies)
        enemies_within5 = 0
        los_threats_current = 0
        allies_close = 0
        char_tile = ctx.char_pos
        for eid in ctx.enemies:
            dist = utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, eid)
            if dist <= 5:
                enemies_within5 += 1
            enemy_pos = ctx.game_state.get_entity(eid)["position"]
            # normalize enemy position to tuple for LOS
            if hasattr(enemy_pos, 'x') and hasattr(enemy_pos, 'y'):
                enemy_coords = (enemy_pos.x, enemy_pos.y)
            elif isinstance(enemy_pos, tuple):
                enemy_coords = enemy_pos
            else:
                enemy_coords = (enemy_pos[0], enemy_pos[1])
            if self.los_manager and self.los_manager.has_los(enemy_coords, char_tile):
                los_threats_current += 1
        for aid in ctx.allies:
            if utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, aid) <= 2:
                allies_close += 1
        return dict(melee_adjacent=melee_adjacent, enemies_within5=enemies_within5,
                    los_threats_current=los_threats_current, allies_close=allies_close)

    def _should_retreat(self, ctx: AITurnContext) -> bool:
        """Decide if strategic retreat should even be evaluated.
        Retreat only if: (a) engaged by 2+ adjacent enemies, OR (b) no melee weapon while an enemy is 1 tile away,
        AND not holding a clear ranged advantage (we have a ranged weapon and >=1 target in base range & LOS)."""
        metrics = self._compute_local_threats(ctx)
        # Condition A: multiple melee threats
        multi_melee_pressure = metrics['melee_adjacent'] >= 2
        # Condition B: threatened in melee but we cannot respond in melee
        threatened_without_melee = (metrics['melee_adjacent'] >= 1 and not ctx.melee_weapon)
        # Ranged advantage: we already have at least one viable immediate ranged target inside base range
        has_ranged_advantage = False
        if ctx.ranged_weapon:
            base_range = getattr(ctx.ranged_weapon, 'weapon_range', 6) or 6
            for eid in ctx.enemies:
                dist = utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, eid)
                if dist <= base_range:
                    enemy_pos = ctx.game_state.get_entity(eid)["position"]
                    if ctx.has_los(ctx.char_pos, enemy_pos):
                        has_ranged_advantage = True
                        break
        if has_ranged_advantage:
            return False  # Prefer to stay and shoot instead of retreating
        return multi_melee_pressure or threatened_without_melee

    def _should_seek_cover(self, ctx: AITurnContext) -> bool:
        """Decide if taking cover is worthwhile.
        Seek cover only if: we have a ranged weapon, are not currently adjacent to an enemy,
        at least 2 enemies have LOS to us, and moving can reduce LOS exposure."""
        if not ctx.ranged_weapon:
            return False
        if ctx.adjacent_enemies:  # In melee; cover not priority
            return False
        metrics = self._compute_local_threats(ctx)
        if metrics['los_threats_current'] < 2:
            return False
        return True

    def _los_threat_count_from_tile(self, ctx: AITurnContext, tile: Tuple[int, int]) -> int:
        count = 0
        for eid in ctx.enemies:
            enemy_pos = ctx.game_state.get_entity(eid)["position"]
            if hasattr(enemy_pos, 'x') and hasattr(enemy_pos, 'y'):
                enemy_coords = (enemy_pos.x, enemy_pos.y)
            elif isinstance(enemy_pos, tuple):
                enemy_coords = enemy_pos
            else:
                enemy_coords = (enemy_pos[0], enemy_pos[1])
            if self.los_manager and self.los_manager.has_los(enemy_coords, tile):
                count += 1
        return count

    # ---------------- New aggressive decision flow helpers ----------------
    def _count_allies_enemies_in_radius(self, ctx: AITurnContext, radius: int = 30) -> Tuple[int, int]:
        allies = 0
        enemies = 0
        for aid in ctx.allies:
            if utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, aid) <= radius:
                allies += 1
        for eid in ctx.enemies:
            if utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, eid) <= radius:
                enemies += 1
        return allies, enemies

    def _is_outnumbered(self, ctx: AITurnContext) -> bool:
        allies, enemies = self._count_allies_enemies_in_radius(ctx, 30)
        # "strictly 2 times fewer allies or worse" => enemies > 2 * allies
        # Treat 0 allies (alone) as outnumbered if any enemy present.
        if allies == 0:
            return enemies > 0
        return enemies > 2 * allies

    def _get_most_menacing_enemy(self, ctx: AITurnContext) -> Optional[str]:
        # Simple heuristic: nearest enemy; tie-breaker highest potential DPS
        best = None
        best_key = (float('inf'), float('-inf'))  # (distance, -dps)
        for eid in ctx.enemies:
            dist = utils.calculate_distance_between_entities(ctx.game_state, ctx.char_id, eid)
            dps = 0
            if ctx.ranged_weapon:
                dps = utils.get_potential_dps(ctx, ctx.ranged_weapon, eid)
            elif ctx.melee_weapon:
                dps = utils.get_potential_dps(ctx, ctx.melee_weapon, eid)
            key = (dist, -dps)
            if key < best_key:
                best_key = key
                best = eid
        return best

    def _find_cover_tile(self, ctx: AITurnContext, enemy_id: str, sprint: bool = False) -> Optional[Tuple[int, int]]:
        if not enemy_id:
            return None
        max_dist = 15 if sprint else 7
        reachable = self.movement_system.get_reachable_tiles(ctx.char_id, max_dist, reserved_tiles=ctx.reserved_tiles)
        enemy_pos_comp = ctx.game_state.get_entity(enemy_id)["position"]
        if hasattr(enemy_pos_comp, 'x'):
            enemy_pos = (enemy_pos_comp.x, enemy_pos_comp.y)
        elif isinstance(enemy_pos_comp, tuple):
            enemy_pos = enemy_pos_comp
        else:
            enemy_pos = (enemy_pos_comp[0], enemy_pos_comp[1])
        current_has_los = self.los_manager.has_los(enemy_pos, ctx.char_pos)
        best_tile = None
        best_metric = (float('inf'), float('inf'))  # (distance to enemy, movement cost)
        for tx, ty, cost in reachable:
            if (tx, ty) == ctx.char_pos:
                continue
            # Need to block LOS relative to enemy
            if self.los_manager.has_los(enemy_pos, (tx, ty)):
                continue
            # Only value moving if enemy currently has LOS OR tile improves (already handled by skip if still has LOS)
            if not current_has_los:
                continue  # Already not seen: skip hiding; stay aggressive elsewhere
            dist_enemy = abs(enemy_pos[0] - tx) + abs(enemy_pos[1] - ty)
            metric = (dist_enemy, cost)
            if metric < best_metric:
                best_metric = metric
                best_tile = (tx, ty)
        return best_tile

    def _standard_move_available(self, char_id: str) -> bool:
        move_action = self._find_action(char_id, "Standard Move")
        return bool(move_action and self.action_system.can_perform_action(char_id, move_action, **{'target_tile': (0,0)}) )  # params dummy; real check later

    def _sprint_available(self, char_id: str) -> bool:
        sprint_action = self._find_action(char_id, "Sprint")
        return bool(sprint_action and self.action_system.can_perform_action(char_id, sprint_action, **{'target_tile': (0,0)}) )

    # ---------------- Public entry point ----------------
    def choose_action(self, char_id: str) -> bool:
        # Rebuild context each call
        available = self.action_system.available_actions.get(char_id, [])
        if not available:
            self._debug(f"WARNING: {char_id} has no available actions registered!")
            return False
        ctx = AITurnContext(
            char_id=char_id,
            game_state=self.game_state,
            los_manager=self.los_manager,
            movement_system=self.movement_system,
            action_system=self.action_system,
            turn_order_system=self.turn_order_system
        )
        self._debug(f"AI decision (aggressive) for {char_id}: enemies={len(ctx.enemies)}, ranged_weapon={ctx.ranged_weapon is not None}, melee_weapon={ctx.melee_weapon is not None}")
        if not ctx.enemies:
            return self._end_turn(char_id)

        attack_action = self._find_action(char_id, "Attack")
        reload_action = self._find_action(char_id, "Reload")
        std_move_action = self._find_action(char_id, "Standard Move")
        sprint_action = self._find_action(char_id, "Sprint")

        def can_attack_with(params):
            return attack_action and self.action_system.can_perform_action(char_id, attack_action, **params)

        # Step 0: Reload if needed (not in melee) before expending attack
        if (reload_action and ctx.ranged_weapon and hasattr(ctx.ranged_weapon, 'ammunition') and ctx.ranged_weapon.ammunition <= 0
            and not ctx.adjacent_enemies and self.action_system.can_perform_action(char_id, reload_action)):
            self._debug(f"{char_id}: Reloading before attacks")
            self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=reload_action.name)
            return True

        # Step 1: Immediate ranged attack (no adjacent enemy)
        if ctx.ranged_weapon and not ctx.adjacent_enemies and attack_action:
            if self._try_immediate_ranged_attack(ctx, char_id):
                return True

        # Step 2: Immediate melee attack (if adjacent)
        if ctx.melee_weapon and ctx.adjacent_enemies and attack_action:
            if self._try_immediate_melee_attack(ctx, char_id):
                return True

        # Step 3: Move + Attack (standard move only) if both move and attack remain
        if attack_action and std_move_action and ctx.ranged_weapon:
            # Prefer ranged move+attack first
            if self._try_move_and_ranged_attack(ctx, char_id):
                return True
        if attack_action and std_move_action and ctx.melee_weapon:
            if self._try_move_and_melee_attack(ctx, char_id):
                return True

        # Re-evaluate outnumbered state for cover logic
        outnumbered = self._is_outnumbered(ctx)
        menacing_enemy = self._get_most_menacing_enemy(ctx) if outnumbered else None

        # Step 4: Standard move to cover if outnumbered & cover reachable
        if outnumbered and std_move_action and menacing_enemy:
            cover_tile = self._find_cover_tile(ctx, menacing_enemy, sprint=False)
            if cover_tile:
                self._debug(f"{char_id}: Moving to cover (standard) at {cover_tile}")
                return self._execute_move(char_id, cover_tile)

        # Step 5: Sprint to cover if outnumbered & only sprint cover available
        if outnumbered and sprint_action and menacing_enemy:
            cover_tile = self._find_cover_tile(ctx, menacing_enemy, sprint=True)
            if cover_tile:
                self._debug(f"{char_id}: Sprinting to cover at {cover_tile}")
                move_params = {'target_tile': cover_tile}
                if self.action_system.can_perform_action(char_id, sprint_action, **move_params):
                    self.turn_order_system.reserved_tiles.add(cover_tile)
                    self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=sprint_action.name, **move_params)
                    return True

        # Step 6: Sprint toward closest enemy (aggressive advance)
        if sprint_action:
            # Find closest enemy tile and attempt to sprint closer
            closest_enemy = min(ctx.enemies, key=lambda eid: utils.calculate_distance_between_entities(ctx.game_state, char_id, eid))
            enemy_pos = ctx.game_state.get_entity(closest_enemy)["position"]
            # Reuse movement helper if available
            try:
                from .movement import _find_best_tile_toward as toward
                target_tile = toward(ctx, enemy_pos, run=True)
            except Exception:
                target_tile = None
            if target_tile:
                self._debug(f"{char_id}: Sprinting toward enemy {closest_enemy} to {target_tile}")
                move_params = {'target_tile': target_tile}
                if self.action_system.can_perform_action(char_id, sprint_action, **move_params):
                    self.turn_order_system.reserved_tiles.add(target_tile)
                    self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=sprint_action.name, **move_params)
                    return True

        # Fallback: If still have attack (maybe only long range) attempt ranged again (penalized)
        if ctx.ranged_weapon and attack_action:
            if self._try_immediate_ranged_attack(ctx, char_id):
                return True

        return self._end_turn(char_id)

    # ---------------- Concrete action attempts ----------------
    def _try_immediate_ranged_attack(self, ctx, char_id: str) -> bool:
        """Fire without moving if target inside normal (no-penalty) weapon_range and LOS.
        Skips if only targets are beyond normal range to avoid futile 0-dice shots."""
        target_id = targeting.choose_ranged_target(ctx)
        if not target_id:
            return False
        # Distance check vs base (unpenalized) range; fallback to 6 if missing
        base_range = getattr(ctx.ranged_weapon, 'weapon_range', 6) or 6
        dist = utils.calculate_distance_between_entities(ctx.game_state, char_id, target_id)
        if dist > base_range:
            # Defer to move + ranged attempt instead of wasting action
            self._debug(f"{char_id}: Immediate ranged skipped (dist {dist} > base {base_range})")
            return False
        attack_action = self._find_action(char_id, "Attack")
        if not attack_action:
            return False
        params = {'target_id': target_id, 'weapon': ctx.ranged_weapon}
        if self.action_system.can_perform_action(char_id, attack_action, **params):
            self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=attack_action.name, **params)
            return True
        return False

    def _try_immediate_melee_attack(self, ctx, char_id: str) -> bool:
        """Try to attack with melee weapon from current position"""
        target_id = targeting.choose_melee_target(ctx)
        if target_id:
            attack_action = self._find_action(char_id, "Attack")
            if attack_action:
                params = {'target_id': target_id, 'weapon': ctx.melee_weapon}
                if self.action_system.can_perform_action(char_id, attack_action, **params):
                    self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=attack_action.name, **params)
                    return True
        return False

    def _try_move_and_ranged_attack(self, ctx, char_id: str) -> bool:
        """Simulate movement options; pick tile enabling best ranged shot."""
        sim_result = movement.simulate_move_and_find_ranged(ctx)
        if sim_result:
            move_target_tile, potential_target_id = sim_result
            return self._execute_move_and_attack(ctx, char_id, move_target_tile, potential_target_id, ctx.ranged_weapon)
        return False

    def _try_move_and_melee_attack(self, ctx, char_id: str) -> bool:
        """Simulate movement options; pick tile enabling best melee engagement."""
        sim_result = movement.simulate_move_and_find_melee(ctx)
        if sim_result:
            move_target_tile, potential_target_id = sim_result
            return self._execute_move_and_attack(ctx, char_id, move_target_tile, potential_target_id, ctx.melee_weapon)
        return False

    def _execute_move_and_attack(self, ctx, char_id: str, move_tile: Tuple[int, int], target_id: str, weapon) -> bool:
        """Queue a move (Standard preferred over Sprint) then opportunistic attack if still legal."""
        # Try Standard Move first
        move_action = self._find_action(char_id, "Standard Move")
        move_params = {'target_tile': move_tile}

        if move_action and self.action_system.can_perform_action(char_id, move_action, **move_params):
            self.turn_order_system.reserved_tiles.add(move_tile)
            self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=move_action.name, **move_params)

            # Try to queue attack
            attack_action = self._find_action(char_id, "Attack")
            if attack_action:
                attack_params = {'target_id': target_id, 'weapon': weapon}
                if self.action_system.can_perform_action(char_id, attack_action, **attack_params):
                    self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=attack_action.name, **attack_params)
            return True

        # Try Sprint if Standard Move failed
        sprint_action = self._find_action(char_id, "Sprint")
        if sprint_action and self.action_system.can_perform_action(char_id, sprint_action, **move_params):
            self.turn_order_system.reserved_tiles.add(move_tile)
            self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=sprint_action.name, **move_params)

            # Try to queue attack
            attack_action = self._find_action(char_id, "Attack")
            if attack_action:
                attack_params = {'target_id': target_id, 'weapon': weapon}
                if self.action_system.can_perform_action(char_id, attack_action, **attack_params):
                    self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=attack_action.name, **attack_params)
            return True

        return False

    def _try_reload(self, ctx, char_id: str) -> bool:
        """Try to reload weapon"""
        reload_action = self._find_action(char_id, "Reload")
        if reload_action and self.action_system.can_perform_action(char_id, reload_action):
            self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name="Reload")
            return True
        return False

    def _try_strategic_retreat(self, ctx, char_id: str) -> bool:
        """Try to move to a strategic retreat position"""
        best_retreat_tile = self._find_best_retreat_tile(ctx)
        if best_retreat_tile:
            self._debug(f"{char_id}: Found retreat tile at {best_retreat_tile}")
            return self._execute_move(char_id, best_retreat_tile)
        return False

    def _try_cover(self, ctx, char_id: str) -> bool:
        """Try to move to cover"""
        best_cover_tile = self._find_best_cover_tile(ctx)
        if not best_cover_tile:
            self._debug(f"{char_id}: No cover tile found")
            return False
        current_threats = self._los_threat_count_from_tile(ctx, ctx.char_pos)
        new_threats = self._los_threat_count_from_tile(ctx, best_cover_tile)
        if new_threats >= current_threats:
            self._debug(f"{char_id}: Cover tile offers no LOS improvement ({new_threats} >= {current_threats})")
            return False
        self._debug(f"{char_id}: Found cover tile at {best_cover_tile} reducing LOS {current_threats}->{new_threats}")
        return self._execute_move(char_id, best_cover_tile)

    def _execute_move(self, char_id: str, target_tile: Tuple[int, int]) -> bool:
        """Perform movement only (no follow-up attack). Standard Move preferred."""
        move_params = {'target_tile': target_tile}

        # Try Standard Move first
        move_action = self._find_action(char_id, "Standard Move")
        if move_action and self.action_system.can_perform_action(char_id, move_action, **move_params):
            self.turn_order_system.reserved_tiles.add(target_tile)
            if self.event_bus:
                self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=move_action.name, **move_params)
            return True

        # Try Sprint if Standard Move failed
        sprint_action = self._find_action(char_id, "Sprint")
        if sprint_action and self.action_system.can_perform_action(char_id, sprint_action, **move_params):
            self.turn_order_system.reserved_tiles.add(target_tile)
            if self.event_bus:
                self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name=sprint_action.name, **move_params)
            return True

        return False

    def _end_turn(self, char_id: str) -> bool:
        """End the turn"""
        end_turn_action = self._find_action(char_id, "End Turn")
        if end_turn_action and self.action_system.can_perform_action(char_id, end_turn_action):
            self.event_bus.publish(CoreEvents.ACTION_REQUESTED, entity_id=char_id, action_name="End Turn")
            return True
        else:
            self._debug(f"WARNING: End Turn action not found for {char_id}!")
            return False

    def _handle_ai_take_turn(self, entity_id: str, **kwargs: Any) -> None:
        """Bridge ``ai_take_turn`` events into decision making."""

        success = self.choose_action(entity_id)
        if not success:
            char_name = entity_id
            entity = getattr(self.game_state, "get_entity", lambda _: None)(entity_id)
            if entity and "character_ref" in entity:
                char_name = getattr(entity["character_ref"].character, "name", char_name)
            print(f"AI for {char_name} failed to choose a valid action. Ending turn.")
            if self.event_bus:
                self.event_bus.publish(CoreEvents.REQUEST_END_TURN, entity_id=entity_id)
