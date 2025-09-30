# Arcade Demo Modernization Notes

## Legacy behaviours

The original `main.Game.setup` relied on helper methods that no longer exist in the
current architecture:

- `PreparationManager.create_simple_arena()` and
  `PreparationManager.create_obstacle_pattern()` handled grid creation and
  obstacle scattering.
- `PreparationManager.place_character()` registered a `Character` directly on the
  terrain without configuring ECS components.
- `GameState.add_weapon()` / `PreparationManager.place_random_weapons()` dropped
  equipment onto the grid instead of attaching it to ECS entities.

Those utilities were removed during the ECS refactor, which meant the demo tried
calling undefined methods and crashed during initialization.

## Modern equivalents

| Feature | Modern API | Notes |
| --- | --- | --- |
| Terrain creation | `PreparationManager.create_grid_terrain()` | Creates a `Terrain` bound to the `GameState` and exposes its `cell_size`. |
| Obstacle scattering | `PreparationManager.scatter_walls()` | Adds randomized cover while respecting spawn points and border margins. |
| Character placement | `PreparationManager.spawn_character()` | Builds the ECS component bundle (inventory, equipment, position, facing, etc.), registers the entity in `GameState`, and places it on the `Terrain`. |
| Equipment management | `EquipmentComponent` inside `spawn_character()` | Weapons are equipped via the ECS component loadout instead of separate terrain items. |

## Initialization flow

1. Construct `GameState` with no size arguments and attach an `EventBus`.
2. Use `PreparationManager` to create terrain and scatter cover.
3. Create `Character` instances and spawn them via `spawn_character()` so that all
   ECS components are registered consistently.
4. Call `PreparationManager.prepare()` once entities and terrain exist to run path
   optimizations and cache combat pools.

These steps keep the demo aligned with the systems used by the manual game
initializers under `tests/manual/` while keeping the visual Arcade loop intact.
