# REVIEW_TODO – Turn-Based Combat Prototype (D-30)

Legend  
- [ ] to-do - [~] in progress - [x] done  
Criticality (impact on POC deadline)  
0 = blocker 1 = high 2 = medium 3 = low 4 = stretch / nice-to-have

## 0 — Blockers (Week 1)

### Module Rename & Bootstrap
- [x] **Rename core file**
  - [x] Rename `src/core/terrain.py` → `src/core/terrain_manager.py`.
  - [X] Grep-replace all `import terrain` → `import terrain_manager as terrain`.
  - [~] Update `__all__` exports, IDE run configurations and unit-test paths.
  - [~] CI passes unchanged after rename.

### Terrain v2 — Consistency & Events
- [x] **Position footprint**
  - [x] Ensure every `PositionComponent` exposes `width` & `height`; default `(1, 1)`.
  - [x] Helper `GameState.get_entity_size(entity_id)` reused by `TerrainManager._get_entity_size`.
- [x] **Walk / Occupy rules**
  - [x] Refactor `TerrainManager.is_walkable` and `is_occupied` to consult `self.walls`
        *and* entity footprints only (remove duplicate `walkable_cells` scan).
  - [x] **Unit tests** `tests/terrain/test_walk_and_occupy.py`
        - Cases: 1×1, 2×2, 3×1 actors around walls and each other.
- [x] **Change events**
  - [x] Lightweight pub/sub inside `terrain_manager.py`
        (`_publish(evt, payload)` using global EventBus).
  - [x] Emit `EVT_TERRAIN_CHANGED` when walls change, and  
        `EVT_ENTITY_MOVED(entity_id, old_pos, new_pos)` from `move_entity`.
- [x] **Wall-matrix upkeep for optimiser**
  - [x] On any wall change call
        `OptimizedPathfinding.rebuild_wall_matrix()` so the optimiser stays coherent.
- [~] **Smoke benchmark**
  - [~] Update `bench_big_map.py`; move on 100 × 100 map must never return
        false results from `is_walkable` / `is_occupied`.

### MovementSystem sync
- [x] Replace manual footprint logic in
      `MovementSystem.get_reachable_tiles` with
      `TerrainManager.is_occupied / is_walkable`.
- [x] Remove local `all_occupied_cells_by_others` build once Terrain side is trusted.
- [x] Update docstrings to new API names (`terrain_manager`).

### Baseline performance script
*(unchanged – see `bench_big_map.py` in repo root)*

## 1 — High Priority (Days 4-9)

### Parallel Pathfinding v1
- [~] Extract pure function **`solve_path(args)`** from `pathfinding.py`.  
- [~] New module **`core/path_workers.py`**  
  - Manages a `multiprocessing.Pool` (size = CPU cores – 1).  
  - API: `precompute_paths_async(start_goals: list[tuple]) -> job_id`.  
  - Emits event `EVT_PATHS_READY(job_id, path_dict)`.  
- [~] TerrainManager queues requests right after any `EVT_ENTITY_MOVED`.  
- [~] MovementSystem listens to `EVT_PATHS_READY`, updates agents’ move queues.

### Line-of-Sight System
- [x] Module **`ecs/systems/los_system.py`**  
  - Algorithm: integer Bresenham; caches result per (`src`,`dst`).  
  - Maintains `los_cache` invalidated by `EVT_TERRAIN_CHANGED`.  
- [ ] RenderSystem greys out tiles not visible to current team.

### Objects / Obstacles
- [ ] New **`ObstacleComponent`**  
  - Kind: `BLOCKING`, `DESTRUCTIBLE`, `COVER`.  
  - HP for destructible objects.  
- [ ] TerrainManager functions `add_obstacle`, `remove_obstacle`.  
- [ ] Pathfinding and LoS must respect obstacles.

## 2 — Medium (Days 8-12)

### Parallel Basic AI
- [~] Function **`decide_actions(team_state)`** → `ai_worker.py`.  
- [~] Pool size = min(teams, CPU cores).  
- [~] Event flow:  
  1. `BasicAISystem` submits job, marks team *thinking*.  
  2. `EVT_AI_DECISION_READY(team_id, actions)` publishes when done.  
  3. `ActionSystem` executes the actions.

### Code Quality & Logging
- [ ] Remove stray `print()` calls → `logging` (DEBUG/INFO/WARN).  
- [ ] Add type hints to all new/modified modules.  
- [ ] Short docstrings + example code snippet for every public function.  
- [ ] Document the event names and payloads in `docs/event_reference.md`.

## 3 — Low (Days 10-15)

### Tiled Import Stub
- [ ] **`utils/tiled_loader.py`**  
  - CLI: `python -m utils.tiled_loader map.tmx --out map.json`.  
  - Converts TMX layers → obstacle list + spawn points.  
  - No editor UI required.

### Continuous Integration (Windows)
- [ ] GitHub Action `.github/workflows/ci.yml`  
  - Matrix: `windows-latest`, Python 3.12.  
  - Steps: `pip install -r requirements.txt`, `pytest`, `flake8`, `bench_big_map.py`.  
  - Fails if `bench_big_map` average turn > 5 s.

## 4 — Stretch Goals (Days 15-20)

### Advanced States (Phase 7 preview)
- [ ] Components `FearComponent`, `DisciplineComponent`.  
- [ ] Effects:  
  - Fear: -25 % accuracy; chance to skip turn.  
  - Frenzy (discipline 0): forced charge to nearest enemy.  
- [ ] Minimal UI: small icon over unit portrait.

## Evergreen — Refactor & Debt (keep an eye every sprint)

- [ ] Remove `basic_AI_system_fix.py` (merged into proper folder).  
- [ ] Delete dead `print_debug` helpers.  
- [ ] Consolidate duplicate vector math functions (`utils/math_vec.py`).  
- [ ] Move every system into `ecs/systems/` tree; respect naming convention `<subject>_system.py`.  
- [ ] Ensure PEP-8 compliance (`flake8`) across new code.  
- [ ] Upgrade to **Python 3.12** runtime only after all C-libs (Arcade, NumPy) tested. 

---

## Performance Log

| Date (ISO) | Map (tiles) | Agents | Avg FPS | Turn Time (s) | Notes |
|------------|-------------|--------|---------|---------------|-------|
| yyyy-mm-dd | 1000×1000 | 1000 | 65 | 4.8 | baseline after Terrain v2 |

---

### Ground Rules
1. **Every PR must build & run on Windows with Arcade.**  
2. **No new feature without at least one unit or integration test.**  
3. **Main thread budget ≤ 16 ms (60 FPS).**  
4. **Stick to pure CPython + approved deps.**  
5. **Document every event in `docs/event_reference.md`.**

*Finish all Blocker items → demo Phase 3 to the client; then branch for Phase 7.*
