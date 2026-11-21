"""Command line entry point for the Dömitz geodata pipeline."""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from shapely.errors import GEOSException

from tools.geo_import.dgm import fetch_dgm_tiles
from tools.geo_import.export import build
from tools.geo_import.osm import fetch_snapshot


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "fetch-dgm", "build"))
    parser.add_argument("--config", type=Path, default=ROOT / "data/manifests/doemitz-altstadt.json")
    parser.add_argument("--raw-dir", type=Path, help="path to a raw snapshot")
    parser.add_argument("--output-dir", type=Path, help="path for generated data")
    parser.add_argument(
        "--terrain",
        choices=("dgm1", "flat"),
        default="dgm1",
        help="terrain elevation mode for build (default: dgm1)",
    )
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        raw_dir = args.raw_dir or ROOT / "data" / "raw" / config["id"]
        output_dir = args.output_dir or ROOT / "data" / "processed" / config["id"]
        if args.command == "fetch":
            fetch_snapshot(config, raw_dir)
            print(f"Snapshot: {raw_dir}")
        elif args.command == "fetch-dgm":
            meta = fetch_dgm_tiles(config, raw_dir)
            names = ", ".join(t["name"] for t in meta["tiles"])
            print(f"DGM1 ({meta['attribution']}): {len(meta['tiles'])} tile(s) [{names}] -> {raw_dir / 'dgm1'}")
        else:
            build(config, raw_dir, output_dir, terrain_mode=args.terrain)
    except (ET.ParseError, GEOSException, KeyError, OSError, ValueError) as error:
        parser.exit(1, f"Import failed: {error}\n")


if __name__ == "__main__":
    main()
