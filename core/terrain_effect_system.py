"""Terrain Effect System

Processes dynamic terrain effects each round / turn:
- Currents: displace entities at round start.
- Start-of-turn hazard triggers: re-trigger dangerous / very dangerous / aura tests.

Listens to:
  round_start(round_number=int)
  turn_start(entity_id=str)

Publishes (already defined in terrain_manager):
  EVT_TERRAIN_CURRENT_MOVED
  EVT_TERRAIN_EFFECT_TRIGGER (delegated via terrain.handle_entity_enter or forced re-trigger)
"""
from typing import Any, Tuple
from core.terrain_manager import (
    EFFECT_CURRENT,
    EVT_TERRAIN_CURRENT_MOVED,
    EFFECT_VERY_DANGEROUS,
    EFFECT_DANGEROUS,
    EFFECT_DANGEROUS_AURA,
    EVT_TERRAIN_EFFECT_TRIGGER,
)

class TerrainEffectSystem:
    def __init__(self, game_state: Any, terrain: Any, event_bus: Any):
        self.game_state = game_state
        self.terrain = terrain
        self.event_bus = event_bus
        if event_bus:
            event_bus.subscribe("round_start", self.on_round_start)
            event_bus.subscribe("turn_start", self.on_turn_start)

    # --- Event handlers -------------------------------------------------
    def on_round_start(self, round_number: int, **kwargs):  # kwargs for bus compatibility
        """Process currents: push entities in current tiles.
        Each entity checked once using its starting anchor position.
        If multiple current effects on same tile, apply the first in list (legacy simple behavior)."""
        # Get all entities with position components using ECS
        from ecs.components.position import PositionComponent
        
        if not self.game_state.ecs_manager:
            return
            
        try:
            entities_with_position = self.game_state.ecs_manager.get_components(PositionComponent)
        except AttributeError:
            # Fallback if get_components doesn't exist
            entities_with_position = []
            for entity_id in self.game_state.ecs_manager.get_all_entities():
                try:
                    pos = self.game_state.ecs_manager.get_component(entity_id, PositionComponent)
                    if pos:
                        entities_with_position.append((entity_id, (pos,)))
                except:
                    continue
        
        for entity_id, (pos,) in entities_with_position:
            if not pos:
                continue
            x, y = pos.x, pos.y
            effects = self.terrain.get_effects(x, y) if hasattr(self.terrain, 'get_effects') else []
            if not effects:
                continue
            current_eff = next((e for e in effects if e.get('name') == EFFECT_CURRENT), None)
            if not current_eff:
                continue
            data = current_eff.get('data', {})
            dx = int(data.get('dx', 0)); dy = int(data.get('dy', 0)); magnitude = int(data.get('magnitude', 1))
            if dx == 0 and dy == 0 or magnitude <= 0:
                continue
            # Attempt stepwise displacement; stop if blocked/invalid
            steps = 0
            cur_x, cur_y = x, y
            while steps < magnitude:
                nx, ny = cur_x + dx, cur_y + dy
                if not self.terrain.is_valid_position(nx, ny, getattr(pos,'width',1), getattr(pos,'height',1)):
                    break
                if not self.terrain.is_walkable(nx, ny, getattr(pos,'width',1), getattr(pos,'height',1)):
                    break
                if self.terrain.is_occupied(nx, ny, getattr(pos,'width',1), getattr(pos,'height',1), entity_id_to_ignore=entity_id):
                    break
                moved = self.terrain.move_entity(entity_id, nx, ny)
                if not moved:
                    break
                pos.x, pos.y = nx, ny
                cur_x, cur_y = nx, ny
                steps += 1
            if (cur_x, cur_y) != (x, y):
                if self.event_bus:
                    self.event_bus.publish(EVT_TERRAIN_CURRENT_MOVED,
                                           entity_id=entity_id,
                                           old_position=(x, y),
                                           new_position=(cur_x, cur_y),
                                           dx=dx, dy=dy, magnitude=steps)

    def on_turn_start(self, entity_id: str, **kwargs):
        """Force hazard re-trigger for entity standing in a hazardous tile at start of its turn.
        Always publishes new events (very_dangerous/dangerous/aura) if effects present under footprint."""
        ent = self.game_state.get_entity(entity_id)
        if not ent:
            return
        pos = ent.get('position')
        if not pos:
            return
        w = getattr(pos,'width',1); h = getattr(pos,'height',1)
        tiles = [(pos.x+dx, pos.y+dy) for dx in range(w) for dy in range(h)]
        vd_data = None; dang_data = None; aura_data = None
        for tx,ty in tiles:
            for eff in self.terrain.get_effects(tx,ty):
                nm = eff.get('name'); data = eff.get('data', {})
                if nm == EFFECT_VERY_DANGEROUS:
                    if vd_data is None or data.get('difficulty',0) > (vd_data.get('difficulty',0)) or data.get('damage',0) > vd_data.get('damage',0):
                        vd_data = data
                elif nm == EFFECT_DANGEROUS:
                    if dang_data is None or data.get('difficulty',0) > (dang_data.get('difficulty',0)) or data.get('damage',0) > dang_data.get('damage',0):
                        dang_data = data
                elif nm == EFFECT_DANGEROUS_AURA:
                    if aura_data is None or data.get('intensity',0) > aura_data.get('intensity',0):
                        aura_data = data
        if vd_data is not None and self.event_bus:
            self.event_bus.publish(EVT_TERRAIN_EFFECT_TRIGGER, entity_id=entity_id, position=(pos.x,pos.y), effect=EFFECT_VERY_DANGEROUS, auto_fail=True, **vd_data)
        if dang_data is not None and self.event_bus:
            self.event_bus.publish(EVT_TERRAIN_EFFECT_TRIGGER, entity_id=entity_id, position=(pos.x,pos.y), effect=EFFECT_DANGEROUS, **dang_data)
        if aura_data is not None and self.event_bus:
            self.event_bus.publish(EVT_TERRAIN_EFFECT_TRIGGER, entity_id=entity_id, position=(pos.x,pos.y), effect=EFFECT_DANGEROUS_AURA, **aura_data)
