"""Command line interface to generate procedural maps for development."""
from __future__ import annotations

import argparse
from pathlib import Path

from modules.maps.gen import MapGenParams
from modules.maps.systems.map_generator import generate_map_spec
from modules.maps.spec import save_json, save_tmx


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a procedural combat map.")
    parser.add_argument("--size", required=True, choices=sorted(MapGenParams.SIZE_DIMENSIONS.keys()))
    parser.add_argument(
        "--biome",
        required=True,
        choices=[
            "building",
            "forest",
            "junkyard",
            "construction",
            "urban_dense",
            "urban_sparse",
        ],
    )
    parser.add_argument("--decor-density", default="mid", choices=["low", "mid", "high"])
    parser.add_argument("--cover-ratio", type=float, default=0.2)
    parser.add_argument("--hazard-ratio", type=float, default=0.1)
    parser.add_argument("--difficult-ratio", type=float, default=0.1)
    parser.add_argument("--chokepoint-limit", type=float, default=0.2)
    parser.add_argument("--room-count", type=int, default=None)
    parser.add_argument("--corridor-min", type=int, default=1)
    parser.add_argument("--corridor-max", type=int, default=3)
    parser.add_argument("--symmetry", default="none", choices=["none", "mirror_x", "mirror_y", "rot_180"])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", required=True, help="Path to the JSON MapSpec output.")
    parser.add_argument(
        "--tmx",
        help="Optional path to write the Tiled TMX export. When omitted the TMX file is not generated.",
    )
    return parser


def _validate_ratios(*values: float) -> None:
    for value in values:
        if not 0.0 <= value <= 1.0:
            raise ValueError("probability ratios must lie between 0 and 1")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        _validate_ratios(
            args.cover_ratio,
            args.hazard_ratio,
            args.difficult_ratio,
            args.chokepoint_limit,
        )
    except ValueError as exc:
        parser.error(str(exc))
    corridor_min = max(1, args.corridor_min)
    corridor_max = max(corridor_min, args.corridor_max)

    params = MapGenParams(
        size=args.size,
        biome=args.biome,
        decor_density=args.decor_density,
        cover_ratio=args.cover_ratio,
        hazard_ratio=args.hazard_ratio,
        difficult_ratio=args.difficult_ratio,
        chokepoint_limit=args.chokepoint_limit,
        room_count=args.room_count,
        corridor_width=(corridor_min, corridor_max),
        symmetry=args.symmetry,
        seed=args.seed,
    )

    spec = generate_map_spec(params)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(spec, out_path)

    if args.tmx:
        tmx_path = Path(args.tmx)
        tmx_path.parent.mkdir(parents=True, exist_ok=True)
        save_tmx(spec, tmx_path)


if __name__ == "__main__":
    main()

