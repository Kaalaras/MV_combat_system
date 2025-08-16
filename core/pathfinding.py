import heapq
from typing import List, Tuple, Dict, Set

def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """Distance de Manhattan entre deux points (orthogonal only)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def is_adjacent_to_enemy(cell: Tuple[int, int], enemy_cells: Set[Tuple[int, int]]) -> bool:
    """Détecte si une cellule est adjacente à une cellule ennemie."""
    x, y = cell
    adjacent_positions = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return any(adj in enemy_cells for adj in adjacent_positions)

def find_path(
    start: Tuple[int, int],
    goal: Tuple[int, int],
    grid_map: List[List[int]],
    occupied_cells: List[Tuple[int, int]],
    enemy_cells: List[Tuple[int, int]],
    terrain=None  # Optional: pass Terrain instance for precomputed paths
) -> List[Tuple[int, int]]:
    """
    Trouve le chemin le plus sûr en évitant obstacles, alliés et en minimisant
    l'exposition aux ennemis. Utilise les chemins pré-calculés si disponibles.

    Args:
        start: Coordonnées de départ (x, y)
        goal: Coordonnées d'arrivée (x, y)
        grid_map: Grille 2D (0 = libre, 1 = obstacle)
        occupied_cells: Coordonnées des cases occupées
        enemy_cells: Coordonnées des ennemis
        terrain: Instance optionnelle contenant des chemins pré-calculés

    Returns:
        Liste de coordonnées du chemin trouvé ou [] si inaccessible.
    """
    # Use precomputed path if available and not blocked
    if terrain and hasattr(terrain, 'path_cache') and (start, goal) in terrain.path_cache:
        path = terrain.path_cache[(start, goal)]
        # Check if any cell in path (except start) is currently occupied
        occupied_set = set(occupied_cells)
        for cell in path[1:]:
            if cell in occupied_set:
                break  # Path blocked, fallback to dynamic
        else:
            return path

    width = len(grid_map)
    height = len(grid_map[0]) if width > 0 else 0

    occupied_set = set(occupied_cells)
    enemy_set = set(enemy_cells)

    open_set: List[Tuple[int, Tuple[int, int]]] = []
    heapq.heappush(open_set, (0, start))

    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    g_score: Dict[Tuple[int, int], int] = {start: 0}
    visited: Set[Tuple[int, int]] = set()

    while open_set:
        current_f, current = heapq.heappop(open_set)

        if current == goal:
            # Reconstruction du chemin
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path

        visited.add(current)
        x, y = current

        neighbors = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        for neighbor in neighbors:
            nx, ny = neighbor
            if not (0 <= nx < width and 0 <= ny < height):
                continue  # En dehors de la grille

            if grid_map[nx][ny] == 1:
                continue  # Mur/Obstacle
            if neighbor in occupied_set:
                continue  # Autre personnage
            if neighbor in visited:
                continue  # Déjà visité

            # Calcul du coût
            base_cost = 1
            if is_adjacent_to_enemy(neighbor, enemy_set):
                base_cost += 1  # Pondération supplémentaire

            tentative_g = g_score[current] + base_cost

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + heuristic(neighbor, goal)
                heapq.heappush(open_set, (f_score, neighbor))

    return []  # Aucun chemin trouvé
