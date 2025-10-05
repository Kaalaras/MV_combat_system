# Convention des cartes Tiled (TMX/TSX)

## Calques attendus

### Calques de tuiles
- `layer.collision` : masque booléen pour les collisions et les murs infranchissables.
- `layer.terrain` : terrain jouable principal (coût de déplacement et cover par défaut).
- `layer.hazard` : surcharges de danger (dégâts de terrain + timing).
- `layer.cover` : surcharges de couvert (light/heavy/fortification).

### Calques d'objets
- `objects.props` : décor non bloquant (information purement visuelle).
- `objects.walls` : volumes bloquant le déplacement et la ligne de vue.
- `objects.doors` : volumes ouvrables ; se comportent comme des murs tant qu'ils sont fermés.

## Propriétés de tuiles
Les propriétés peuvent être définies au niveau du tileset ou d'une tuile individuelle. Les valeurs sont lues dans cet ordre : tuile ➝ tileset ➝ valeurs de repli ci-dessous.

Propriété       | Type | Valeurs autorisées                                | Valeur de repli | Effet gameplay
----------------|------|----------------------------------------------------|-----------------|----------------
`move_cost`     | int  | ≥ 0 (`None` réservé aux murs/void internes)        | `1`             | Coût standard du sol.
`blocks_move`   | bool | `true` / `false` (`1` / `0`, `yes` / `no`, `on` / `off` acceptés) | `false`         | Bloque le déplacement.
`blocks_los`    | bool | `true` / `false` (`1` / `0`, `yes` / `no`, `on` / `off` acceptés) | `false`         | Bloque la ligne de vue.
`cover`         | str  | `"none"`, `"light"`, `"heavy"`, `"fortification"` | `"none"`       | Flags de couvert appliqués.
`hazard`        | str  | `"none"`, `"dangerous"`, `"very_dangerous"`      | `"none"`       | Flags + dégâts de terrain.
`hazard_timing` | str  | `"on_enter"`, `"end_of_turn"`, `"per_tile"`      | `"on_enter"`   | Moment d'application des dégâts.

Les valeurs de repli correspondent au terrain « sol » (floor). Elles sont appliquées dès qu'une propriété est absente afin de garantir un état jouable cohérent.

> **Note :** Les parseurs traitent les valeurs vides (par exemple, chaîne vide ou espaces) comme « absentes » pour les propriétés `move_cost`, `cover`, `hazard` et `hazard_timing`. Dans ces cas, la valeur de repli est appliquée.
## Unités et coordonnées
Toutes les conversions se font en coordonnées de grille (cases). Les objets et formes issus de Tiled doivent donc être convertis avant usage gameplay, sans utiliser les pixels comme référence.
