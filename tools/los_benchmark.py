import argparse, random, time
from core.game_state import GameState
from core.event_bus import EventBus
from core.terrain_manager import Terrain
from core.los_manager import LineOfSightManager


def build_terrain(gs: GameState, width: int, height: int, wall_fraction: float):
    t = Terrain(width, height, game_state=gs)
    gs.set_terrain(t)
    total = width * height
    wall_target = int(total * wall_fraction)
    placed = 0
    while placed < wall_target:
        x = random.randint(0, width-1)
        y = random.randint(0, height-1)
        if (x,y) in t.walls:
            continue
        # Avoid clustering entirely along same line by random skip
        if random.random() < 0.1:
            continue
        t.add_wall(x,y)
        placed += 1
    return t


def random_pairs(width:int, height:int, count:int):
    pairs = []
    for _ in range(count):
        ax, ay = random.randint(0,width-1), random.randint(0,height-1)
        bx, by = random.randint(0,width-1), random.randint(0,height-1)
        if (ax,ay)==(bx,by):
            bx = (bx+1) % width
        pairs.append(((ax,ay),(bx,by)))
    return pairs


def run_benchmark(width:int, height:int, wall_fraction:float, samples:int, seed:int):
    random.seed(seed)
    gs = GameState()
    gs.set_event_bus(EventBus())
    build_terrain(gs,width,height,wall_fraction)
    los = LineOfSightManager(gs, gs.terrain, gs.event_bus, los_granularity=4, sampling_mode='sparse')
    pairs = random_pairs(width,height,samples)

    # Sparse run
    sparse_rays = 0
    sparse_partial = 0
    t0 = time.perf_counter()
    for a,b in pairs:
        entry = los.benchmark_visibility(a,b,'sparse')
        sparse_rays += entry.total_rays
        if entry.partial_wall:
            sparse_partial += 1
    t1 = time.perf_counter()

    # Full run
    full_rays = 0
    full_partial = 0
    t2 = time.perf_counter()
    for a,b in pairs:
        entry = los.benchmark_visibility(a,b,'full')
        full_rays += entry.total_rays
        if entry.partial_wall:
            full_partial += 1
    t3 = time.perf_counter()

    return {
        'width': width,
        'height': height,
        'samples': samples,
        'walls_fraction': wall_fraction,
        'sparse_rays_total': sparse_rays,
        'full_rays_total': full_rays,
        'sparse_time_s': t1 - t0,
        'full_time_s': t3 - t2,
        'sparse_partial_pairs': sparse_partial,
        'full_partial_pairs': full_partial,
        'ray_reduction_pct': (1 - (sparse_rays / full_rays)) * 100 if full_rays else 0.0,
    }


def main():
    ap = argparse.ArgumentParser(description='LOS Benchmark: sparse vs full sampling')
    ap.add_argument('--width', type=int, default=40)
    ap.add_argument('--height', type=int, default=40)
    ap.add_argument('--walls', type=float, default=0.08, help='fraction of cells that are walls')
    ap.add_argument('--samples', type=int, default=500)
    ap.add_argument('--seed', type=int, default=1337)
    args = ap.parse_args()
    result = run_benchmark(args.width, args.height, args.walls, args.samples, args.seed)
    print('\n=== LOS Benchmark ===')
    for k,v in result.items():
        print(f'{k}: {v}')
    print('\nSparse rays per sample: {:.2f}'.format(result['sparse_rays_total']/args.samples))
    print('Full rays per sample:   {:.2f}'.format(result['full_rays_total']/args.samples))
    if result['sparse_partial_pairs'] != result['full_partial_pairs']:
        print('[WARN] Partial wall classification mismatch (sparse vs full).')
    else:
        print('Partial wall classifications match.')

if __name__ == '__main__':
    main()

