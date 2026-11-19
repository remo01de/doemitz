"""Command line entry point for the Dömitz geodata pipeline."""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from shapely.errors import GEOSException

from tools.geo_import.export import build
from tools.geo_import.osm import fetch_snapshot


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "build"))
    parser.add_argument("--config", type=Path, default=ROOT / "data/manifests/doemitz-altstadt.json")
    parser.add_argument("--raw-dir", type=Path, help="path to a raw snapshot")
    parser.add_argument("--output-dir", type=Path, help="path for generated data")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        raw_dir = args.raw_dir or ROOT / "data" / "raw" / config["id"]
        output_dir = args.output_dir or ROOT / "data" / "processed" / config["id"]
        if args.command == "fetch":
            fetch_snapshot(config, raw_dir)
            print(f"Snapshot: {raw_dir}")
        else:
            build(config, raw_dir, output_dir)
    except (ET.ParseError, GEOSException, KeyError, OSError, ValueError) as error:
        parser.exit(1, f"Import failed: {error}\n")


if __name__ == "__main__":
    main()
