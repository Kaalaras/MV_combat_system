"""Battle map visualization utilities.

This module provides functions for drawing battle maps as images and creating
animations from battle sequences.
"""

from PIL import Image, ImageDraw, ImageFont
import os
import datetime
import uuid


def get_entity_color(team, weapon_type):
    """Get color for entity based on team and weapon type."""
    # Color map for teams and weapon types
    color_map = {
        "A": {
            "pistol": (173, 216, 230),    # light blue
            "club": (0, 0, 139),          # dark blue
            "shotgun": (0, 191, 255),     # deep sky blue
            "grenade": (25, 25, 112),     # midnight blue
        },
        "B": {
            "pistol": (255, 182, 193),    # light red
            "club": (139, 0, 0),          # dark red
            "shotgun": (255, 99, 71),     # tomato
            "grenade": (178, 34, 34),     # firebrick
        },
        "C": {
            "pistol": (144, 238, 144),    # light green
            "club": (0, 100, 0),          # dark green
            "shotgun": (60, 179, 113),    # medium sea green
            "grenade": (0, 128, 0),       # green
        },
        "D": {
            "pistol": (221, 160, 221),    # light purple
            "club": (75, 0, 130),         # indigo
            "shotgun": (186, 85, 211),    # medium orchid
            "grenade": (148, 0, 211),     # dark violet
        },
    }
    return color_map.get(team, {}).get(weapon_type, (128, 128, 128))  # default gray


def draw_battle_map(game_state, terrain, *team_ids, round_num, out_dir, grid_size=50, px_size=8):
    """Draw a battle map as an image file.
    
    Args:
        game_state: Current game state containing entities
        terrain: Terrain object (currently unused, kept for compatibility)
        team_ids: Variable number of team ID lists
        round_num: Round number for labeling
        out_dir: Output directory for the image
        grid_size: Size of the grid (default: 50)
        px_size: Pixel size for each grid cell (default: 8)
    """
    img = Image.new("RGB", (grid_size * px_size, grid_size * px_size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Draw empty cells as white
    for x in range(grid_size):
        for y in range(grid_size):
            draw.rectangle([
                x * px_size, y * px_size, (x + 1) * px_size - 1, (y + 1) * px_size - 1
            ], fill=(255, 255, 255))
    
    # Draw entities (with size support)
    for team in team_ids:
        for eid in team:
            ent = game_state.get_entity(eid)
            pos = ent["position"]
            char = ent["character_ref"].character
            if char.is_dead:
                continue
            team_name = char.team
            eq = ent["equipment"]
            
            # Detect weapon type
            if eq.weapons.get("grenade", None):
                weapon_type = "grenade"
            elif eq.weapons.get("shotgun", None):
                weapon_type = "shotgun"
            elif eq.weapons.get("ranged", None):
                weapon_type = "pistol"
            else:
                weapon_type = "club"
            
            color = get_entity_color(team_name, weapon_type)
            x, y = pos.x, pos.y
            width = getattr(pos, 'width', 1)
            height = getattr(pos, 'height', 1)
            draw.rectangle([
                x * px_size, y * px_size, (x + width) * px_size - 1, (y + height) * px_size - 1
            ], fill=color)
    
    # Overlay round number
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()
    draw.text((5, 5), f"Round {round_num}", fill=(0, 0, 0), font=font)
    
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    img.save(os.path.join(out_dir, f"battle_map_{round_num:03d}.png"))


def get_battle_subfolder(base_dir):
    """Create a timestamped subfolder for battle images."""
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    subfolder = os.path.join(base_dir, now_str)
    if not os.path.exists(subfolder):
        os.makedirs(subfolder)
    return subfolder


def get_unique_battle_subfolder(base_dir, prefix="game_"):
    """Create a unique subfolder for a battle run, using a timestamp and a short UUID.
    
    Returns the full path to the created subfolder.
    """
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = str(uuid.uuid4())[:8]
    subfolder = os.path.join(base_dir, f"{prefix}{now_str}_{short_id}")
    if not os.path.exists(subfolder):
        os.makedirs(subfolder)
    return subfolder


def assemble_gif(out_dir, num_rounds, gif_name="battle.gif", grid_size=50, px_size=8, duration=200):
    """Assemble battle map images into an animated GIF.
    
    Args:
        out_dir: Directory containing battle map images
        num_rounds: Number of rounds to include
        gif_name: Name for the output GIF file
        grid_size: Grid size (unused, kept for compatibility)
        px_size: Pixel size (unused, kept for compatibility)
        duration: Duration between frames in milliseconds
    """
    from PIL import Image
    frames = []
    for i in range(1, num_rounds + 1):
        path = os.path.join(out_dir, f"battle_map_{i:03d}.png")
        if os.path.exists(path):
            frames.append(Image.open(path))
    if frames:
        gif_path = os.path.join(out_dir, gif_name)
        frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
        print(f"GIF assembled at: {gif_path}")