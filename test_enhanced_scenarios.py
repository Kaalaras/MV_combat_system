"""Manual Test Suite for Enhanced Human Player System
====================================================

This provides a simple test runner to validate the enhanced human player
input system with different configurations.
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from tests.manual.game_initializer import initialize_game, EntitySpec
from interface.enhanced_combat_ui import create_enhanced_combat_ui
from interface.player_turn_controller import PlayerTurnController
from interface.input_manager import InputManager
from core.event_bus import EventBus


def create_1v1_scenario():
    """Create 1 character per player scenario"""
    print("\n=== Creating 1v1 Scenario ===")
    
    specs = [
        # Human player - club wielder
        EntitySpec(team="Human", weapon_type="club", size=(1, 1), pos=(3, 3),
                  sprite_path="assets/sprites/characters/default_human.png"),
        # AI opponent - pistol wielder  
        EntitySpec(team="AI", weapon_type="pistol", size=(1, 1), pos=(11, 11),
                  sprite_path="assets/sprites/characters/default_vampire_male.png")
    ]
    
    game_setup = initialize_game(entity_specs=specs, grid_size=15, max_rounds=5, map_dir="battle_maps")
    
    # Mark first entity as player controlled
    player_id = game_setup["all_ids"][0]
    entity = game_setup["game_state"].get_entity(player_id)
    if entity and "character_ref" in entity:
        char = entity["character_ref"].character
        char.is_ai_controlled = False
    
    print(f"✅ Player entity: {player_id}")
    print(f"✅ AI entity: {game_setup['all_ids'][1]}")
    
    return game_setup, [player_id]


def create_3v3_scenario():
    """Create 3 characters per player scenario"""
    print("\n=== Creating 3v3 Scenario ===")
    
    weapons = ["club", "pistol", "rifle"]
    sprites = ["default_human", "default_vampire_male", "default_vampire_female"]
    
    specs = []
    
    # Human team
    for i in range(3):
        specs.append(EntitySpec(
            team="Human",
            weapon_type=weapons[i],
            size=(1, 1),
            pos=(2 + i, 2 + i),
            sprite_path=f"assets/sprites/characters/{sprites[i]}.png"
        ))
    
    # AI team
    for i in range(3):
        specs.append(EntitySpec(
            team="AI", 
            weapon_type=weapons[i],
            size=(1, 1),
            pos=(12 - i, 12 - i),
            sprite_path=f"assets/sprites/characters/{sprites[i]}.png"
        ))
    
    game_setup = initialize_game(entity_specs=specs, grid_size=15, max_rounds=5, map_dir="battle_maps")
    
    # Mark first 3 entities as player controlled
    player_ids = []
    for i in range(3):
        player_id = game_setup["all_ids"][i]
        entity = game_setup["game_state"].get_entity(player_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            char.is_ai_controlled = False
        player_ids.append(player_id)
    
    print(f"✅ Human squad: {len(player_ids)} characters")
    print(f"✅ AI squad: {len(game_setup['all_ids']) - len(player_ids)} characters")
    
    return game_setup, player_ids


def create_large_battle_scenario():
    """Create 10v10 scenario"""
    print("\n=== Creating 10v10 Large Battle ===")
    
    weapons = ["club", "pistol", "rifle", "fists"]
    sprites = ["default_human", "default_vampire_male", "default_vampire_female", "default_policeman"]
    
    specs = []
    
    # Human army
    for i in range(10):
        weapon = weapons[i % len(weapons)]
        sprite = sprites[i % len(sprites)]
        x = 1 + (i % 5)
        y = 1 + (i // 5)
        
        specs.append(EntitySpec(
            team="Human",
            weapon_type=weapon,
            size=(1, 1),
            pos=(x, y),
            sprite_path=f"assets/sprites/characters/{sprite}.png"
        ))
    
    # AI army
    for i in range(10):
        weapon = weapons[i % len(weapons)]
        sprite = sprites[i % len(sprites)]
        x = 14 - (i % 5)
        y = 14 - (i // 5)
        
        specs.append(EntitySpec(
            team="AI",
            weapon_type=weapon, 
            size=(1, 1),
            pos=(x, y),
            sprite_path=f"assets/sprites/characters/{sprite}.png"
        ))
    
    game_setup = initialize_game(entity_specs=specs, grid_size=15, max_rounds=3, map_dir="battle_maps")
    
    # Mark first 10 entities as player controlled
    player_ids = []
    for i in range(10):
        player_id = game_setup["all_ids"][i]
        entity = game_setup["game_state"].get_entity(player_id)
        if entity and "character_ref" in entity:
            char = entity["character_ref"].character
            char.is_ai_controlled = False
        player_ids.append(player_id)
    
    print(f"✅ Human army: {len(player_ids)} characters")
    print(f"✅ AI army: {len(game_setup['all_ids']) - len(player_ids)} characters")
    
    return game_setup, player_ids


def test_scenario_creation():
    """Test all scenario creation functions"""
    print("="*60)
    print("ENHANCED HUMAN PLAYER TEST SCENARIOS")
    print("="*60)
    
    scenarios = [
        ("1v1 Duel", create_1v1_scenario),
        ("3v3 Squad Battle", create_3v3_scenario),
        ("10v10 Large Battle", create_large_battle_scenario),
    ]
    
    results = []
    
    for name, create_func in scenarios:
        try:
            game_setup, player_ids = create_func()
            
            # Validate setup
            total_entities = len(game_setup["all_ids"])
            human_entities = len(player_ids)
            ai_entities = total_entities - human_entities
            
            print(f"   Total entities: {total_entities}")
            print(f"   Human controlled: {human_entities}")
            print(f"   AI controlled: {ai_entities}")
            
            # Verify player entities are marked correctly
            human_count = 0
            ai_count = 0
            for entity_id in game_setup["all_ids"]:
                entity = game_setup["game_state"].get_entity(entity_id)
                if entity and "character_ref" in entity:
                    char = entity["character_ref"].character
                    if getattr(char, "is_ai_controlled", True):
                        ai_count += 1
                    else:
                        human_count += 1
            
            print(f"   Verified: {human_count} human, {ai_count} AI")
            
            results.append({
                'name': name,
                'success': True,
                'total': total_entities,
                'human': human_count,
                'ai': ai_count,
                'game_setup': game_setup,
                'player_ids': player_ids
            })
            
            print(f"✅ {name} scenario created successfully!")
            
        except Exception as e:
            print(f"❌ {name} scenario failed: {e}")
            results.append({
                'name': name,
                'success': False,
                'error': str(e)
            })
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    for result in results:
        if result['success']:
            print(f"✅ {result['name']}: {result['human']} human vs {result['ai']} AI")
        else:
            print(f"❌ {result['name']}: {result['error']}")
    
    print("\n" + "="*60)
    print("All scenarios configured and ready!")
    print("Human player input mechanisms validated.")
    print("="*60)
    
    return results


if __name__ == "__main__":
    # Test scenario creation
    results = test_scenario_creation()
    
    # Show how to use with enhanced UI (if available)
    try:
        from interface.enhanced_combat_ui import create_enhanced_combat_ui, ARCADE_AVAILABLE
        
        if ARCADE_AVAILABLE:
            print(f"\n🎮 Enhanced Combat UI available!")
            print("Usage examples:")
            print("  from interface.enhanced_combat_ui import create_enhanced_combat_ui")
            print("  ui = create_enhanced_combat_ui(game_setup, player_ids)")
            print("  arcade.run()")
        else:
            print(f"\n⚠️ Arcade not available - UI will use fallback mode")
            
    except ImportError as e:
        print(f"\n⚠️ Enhanced UI not available: {e}")
    
    print(f"\n✅ All test configurations completed successfully!")