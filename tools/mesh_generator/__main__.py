"""Generate triangulated placeholder geometry for the Dömitz Unreal level."""

import argparse
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re

from shapely import constrained_delaunay_triangles, orient_polygons, set_precision, union_all
from shapely.geometry import LineString, shape
from shapely.ops import nearest_points

from tools.geo_import.export import geometry_parts, write_json
from tools.mesh_generator.architecture import ROOF_STYLES, WALL_STYLES, add_stylized_building
from tools.mesh_generator.citizens import build_citizens
from tools.mesh_generator.props import add_street_lamps, add_stylized_trees
from tools.mesh_generator.traffic import build_vehicle_route


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENE = ROOT / "data/processed/doemitz-altstadt/scene.json"
STREET_LAYOUT = ROOT / "data/manifests/doemitz-altstadt-streets.json"
CITIZENS_LAYOUT = ROOT / "data/manifests/doemitz-altstadt-citizens.json"
PALETTE = {
    "Terrain": (0.22, 0.42, 0.14),
    "Water": (0.06, 0.34, 0.42),
    "Roads": (0.24, 0.24, 0.25),
    "Paving": (0.38, 0.32, 0.27),
    "Paths": (0.42, 0.36, 0.26),
    "Sidewalks": (0.60, 0.52, 0.43),
    "WallsCream": (0.86, 0.78, 0.62),
    "WallsOchre": (0.82, 0.56, 0.22),
    "WallsTerracotta": (0.74, 0.31, 0.21),
    "WallsSage": (0.48, 0.58, 0.42),
    "WallsSand": (0.76, 0.68, 0.52),
    "WallsBrick": (0.58, 0.24, 0.16),
    "RoofsTerracotta": (0.62, 0.20, 0.12),
    "RoofsClay": (0.48, 0.22, 0.14),
    "RoofsSlate": (0.20, 0.23, 0.28),
    "StoneTrim": (0.48, 0.46, 0.43),
    "TimberTrim": (0.22, 0.13, 0.08),
    "WindowGlass": (0.08, 0.14, 0.20),
    "ShuttersGreen": (0.14, 0.36, 0.22),
    "ShuttersRed": (0.58, 0.16, 0.14),
    "ShuttersBlue": (0.18, 0.34, 0.52),
    "Doors": (0.28, 0.16, 0.09),
    "FlowerBoxes": (0.78, 0.22, 0.36),
    "LampMetal": (0.11, 0.12, 0.13),
    "LanternGlow": (1.00, 0.84, 0.48),
    "TreeTrunks": (0.26, 0.17, 0.11),
    "FoliageLight": (0.24, 0.54, 0.16),
    "FoliageMid": (0.15, 0.42, 0.14),
    "FoliageDark": (0.10, 0.30, 0.11),
}
WALLS = WALL_STYLES
ROOFS = ROOF_STYLES
ROAD_WIDTHS_M = {
    "primary": 7.0, "secondary": 7.0, "tertiary": 6.5, "residential": 6.0,
    "living_street": 5.0, "service": 3.5, "track": 3.0, "pedestrian": 4.0,
    "cycleway": 2.5, "footway": 1.8, "path": 1.8, "steps": 1.5,
}
STONE_SURFACES = {"cobblestone", "unhewn_cobblestone", "sett", "paving_stones", "pebblestone"}
PATH_CLASSES = {"footway", "cycleway", "path", "steps"}
ROAD_MESHES = ("Paving", "Roads", "Paths")
STREET_GRID_M = 0.002
ROAD_ELEVATION_M = 0.08
CURB_HEIGHT_M = 0.12


@dataclass
class Mesh:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    triangles: list[tuple[int, int, int]] = field(default_factory=list)
    indices: dict[tuple[float, float, float], int] = field(default_factory=dict)

    def vertex(self, xy, elevation_m):
        coordinate = (xy[0], xy[1], elevation_m)
        if coordinate not in self.indices:
            self.indices[coordinate] = len(self.vertices)
            self.vertices.append(coordinate)
        return self.indices[coordinate]

    def add_surface(self, polygon, elevation_m):
        triangles = orient_polygons(constrained_delaunay_triangles(polygon))
        for triangle in triangles.geoms:
            self.triangles.append(
                tuple(self.vertex(xy, elevation_m) for xy in list(triangle.exterior.coords)[:3])
            )

    def add_walls(self, polygon, height_m, base_m):
        for ring in (polygon.exterior, *polygon.interiors):
            points = list(ring.coords)
            for start, end in zip(points, points[1:]):
                # Separate face vertices keep hard edges and permit shared parcel walls.
                if start == end:
                    continue
                offset = len(self.vertices)
                self.vertices.extend(
                    [(*start, base_m), (*end, base_m), (*end, base_m + height_m), (*start, base_m + height_m)]
                )
                self.triangles.extend(((offset, offset + 1, offset + 2), (offset, offset + 2, offset + 3)))


def positive_length(value, maximum):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*m?\s*", value)
    if match:
        number = float(match[1])
        if isfinite(number) and 0 < number <= maximum:
            return number
    return None


def building_height(tags):
    height = positive_length(tags.get("height", ""), 150)
    if height is not None:
        return height, "osm_height"
    levels = positive_length(tags.get("building:levels", ""), 30)
    if levels is not None:
        return 3.0 * levels, "estimated_from_levels"
    if tags.get("building") in {"garage", "garages", "shed", "roof", "hut"}:
        return 2.8, "estimated_default"
    return 6.5, "estimated_default"


def road_width(tags):
    width = positive_length(tags.get("width", ""), 30)
    if width is not None:
        return width, "osm_width"
    return ROAD_WIDTHS_M.get(tags["highway"], 5.5), "estimated_from_highway"


def add_streets(meshes, roads, bounds, obstacles, base_m, sidewalk_widths, default_sidewalk_widths=None):
    surfaces = {name: [] for name in ROAD_MESHES}
    sidewalk_envelopes = []
    eligible_ids = set()
    sidewalk_road_ids = set()
    width_sources = Counter()
    default_sidewalk_widths = default_sidewalk_widths or {}
    bounds = set_precision(bounds, STREET_GRID_M)
    for road in roads:
        tags = road["properties"]
        if tags.get("tunnel", "no") != "no":
            continue
        highway = tags["highway"]
        width, source = road_width(tags)
        width_sources[source] += 1
        axis = shape(road["geometry"])
        name = "Roads"
        if tags.get("surface") in STONE_SURFACES:
            name = "Paving"
        elif highway in PATH_CLASSES:
            name = "Paths"
        surfaces[name].append(axis.buffer(width / 2, quad_segs=3))

        road_id = road["id"]
        sidewalk_width = None
        if road_id in sidewalk_widths and highway not in PATH_CLASSES:
            sidewalk_width = sidewalk_widths[road_id]
            eligible_ids.add(road_id)
        elif highway in default_sidewalk_widths and highway not in PATH_CLASSES:
            sidewalk_width = default_sidewalk_widths[highway]

        if sidewalk_width is not None:
            if not 0 < sidewalk_width <= 5:
                raise ValueError(f"invalid sidewalk width for {road_id}: {sidewalk_width}")
            sidewalk_road_ids.add(road_id)
            sidewalk_envelopes.append(
                axis.buffer(width / 2 + sidewalk_width, quad_segs=3, cap_style="flat")
            )

    if eligible_ids != sidewalk_widths.keys():
        raise ValueError(f"missing eligible roads for sidewalks: {sorted(sidewalk_widths.keys() - eligible_ids)}")

    occupied = union_all([], grid_size=STREET_GRID_M)
    for name, parts in surfaces.items():
        area = set_precision(union_all(parts, grid_size=STREET_GRID_M), STREET_GRID_M).intersection(bounds)
        for polygon in geometry_parts(area.difference(occupied), "Polygon"):
            meshes[name].add_surface(polygon, base_m + ROAD_ELEVATION_M)
        occupied = occupied.union(area)

    envelopes = set_precision(union_all(sidewalk_envelopes, grid_size=STREET_GRID_M), STREET_GRID_M)
    excluded = occupied.union(set_precision(obstacles, STREET_GRID_M))
    sidewalk_area = envelopes.intersection(bounds).difference(excluded)
    sidewalks = []
    for polygon in geometry_parts(orient_polygons(sidewalk_area), "Polygon"):
        if polygon.area < 0.08:
            continue
        sidewalks.append(polygon)
        meshes["Sidewalks"].add_surface(polygon, base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M)
        meshes["Sidewalks"].add_walls(polygon, ROAD_ELEVATION_M + CURB_HEIGHT_M, base_m)
    return width_sources, sidewalks


def build(scene, report, sidewalk_widths=None, vehicle_config=None, citizens_config=None, default_sidewalk_widths=None):
    if scene["schema_version"] != 1 or scene["coordinates"]["local_axes"] != ["east", "north"]:
        raise ValueError("expected scene schema 1 with local [east, north] coordinates")
    if scene["coordinates"]["unit"] != "meter" or scene["terrain"]["kind"] != "flat_placeholder":
        raise ValueError("the prototype requires a metric scene with a flat placeholder terrain")

    meshes = {name: Mesh() for name in PALETTE}
    bounds = shape(scene["terrain"]["boundary"])
    base_m = scene["terrain"]["elevation_m"]
    meshes["Terrain"].add_surface(bounds, base_m)
    water = union_all([shape(feature["geometry"]) for feature in scene["layers"]["water"]])
    for polygon in geometry_parts(water, "Polygon"):
        meshes["Water"].add_surface(polygon, base_m + 0.04)

    height_sources = Counter()
    buildings = []
    for feature in scene["layers"]["buildings"]:
        osm_id = int(feature["id"].rsplit(":", 1)[1])
        height, source = building_height(feature["properties"])
        height_sources[source] += 1
        geometry = orient_polygons(shape(feature["geometry"]))
        buildings.append(geometry)
        for polygon in geometry_parts(geometry, "Polygon"):
            add_stylized_building(meshes, polygon, height, base_m, osm_id, feature["properties"])

    sidewalk_widths = sidewalk_widths or {}
    default_sidewalk_widths = default_sidewalk_widths or {}
    obstacles = (
        union_all([water, *buildings], grid_size=STREET_GRID_M)
        if sidewalk_widths or default_sidewalk_widths or vehicle_config or citizens_config else water
    )
    roads = scene["layers"]["roads"]
    width_sources, sidewalks = add_streets(
        meshes, roads, bounds, obstacles, base_m, sidewalk_widths, default_sidewalk_widths,
    )
    roads_by_id = {road["id"]: (road, road_width(road["properties"])[0]) for road in roads}
    road_buffers = [
        shape(road["geometry"]).buffer(width / 2, quad_segs=2)
        for road, width in roads_by_id.values()
        if road["properties"].get("tunnel", "no") == "no"
    ]
    excluded_for_trees = union_all([water, *buildings, *road_buffers, *sidewalks], grid_size=STREET_GRID_M)
    detailed_road_ids = {
        road["id"]
        for road in roads
        if road["properties"].get("tunnel", "no") == "no"
        and (
            road["id"] in sidewalk_widths
            or road["properties"]["highway"] in default_sidewalk_widths
        )
    }
    lamp_lights, lamps_placed, benches_placed, bollards_placed = add_street_lamps(
        meshes, roads, sidewalks, base_m, base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M, detailed_road_ids,
    )
    trees_placed = add_stylized_trees(meshes, bounds, excluded_for_trees, base_m)
    vehicle = None
    if vehicle_config:
        vehicle = build_vehicle_route(
            vehicle_config, roads_by_id,
            bounds, obstacles, base_m + ROAD_ELEVATION_M,
        )
    citizens = None
    if citizens_config:
        citizens = build_citizens(
            citizens_config, roads_by_id, scene["layers"]["buildings"], sidewalks,
            obstacles, base_m + ROAD_ELEVATION_M, base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M,
        )
    reference = report["reference"]
    if scene["id"] != report["id"]:
        raise ValueError("scene and report belong to different areas")
    reference_points = reference["local_points_m"]
    reference_line = LineString(reference_points)
    start = reference_line.interpolate(0.5, normalized=True)
    nearest_building = min(buildings, key=lambda building: building.distance(start))
    if nearest_building.distance(start) < 1.0 or water.distance(start) < 1.0:
        raise ValueError("player start on the reference street is obstructed")
    roof_probe = nearest_building.representative_point()
    sidewalk_interior = union_all([polygon.buffer(-0.4) for polygon in sidewalks])
    sidewalk_probe = None
    if sidewalk_widths and sidewalk_interior.is_empty:
        raise ValueError("the configured sidewalks have no walkable interior")
    if not sidewalk_interior.is_empty:
        _, point = nearest_points(start, sidewalk_interior)
        sidewalk_probe = [point.x, point.y, base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M]
    return {
        "schema_version": 1,
        "attribution": scene["attribution"],
        "attribution_url": scene["attribution_url"],
        "bounds_m": bounds.bounds,
        "reference_points_m": reference_points,
        "reference_geodesic_m": reference["geodesic_m"],
        "maximum_relative_error": reference["maximum_relative_error"],
        "start_m": [start.x, start.y, base_m + 1.0],
        "roof_probe_m": [roof_probe.x, roof_probe.y, base_m],
        "sidewalk_probe_m": sidewalk_probe,
        "vehicle": vehicle,
        "citizens": citizens,
        "sidewalks": {
            "width_source": "estimated_from_pilot_layout",
            "widths_m": sidewalk_widths,
            "area_m2": round(sum(polygon.area for polygon in sidewalks), 2),
        },
        "height_sources": dict(height_sources),
        "width_sources": dict(width_sources),
        "props": {
            "street_lamps": lamps_placed,
            "lamp_lights_m": lamp_lights,
            "benches": benches_placed,
            "bollards": bollards_placed,
            "trees_and_bushes": trees_placed,
        },
        "meshes": {
            name: {
                "color": PALETTE[name],
                "collision": name in {"Terrain", "Sidewalks"} or name in WALLS or name in ROOFS,
                "vertices": mesh.vertices,
                "triangles": mesh.triangles,
            }
            for name, mesh in meshes.items() if mesh.triangles
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    args = parser.parse_args()
    scene_bytes = args.scene.read_bytes()
    report = json.loads(args.scene.with_name("import-report.json").read_text(encoding="utf-8"))
    scene = json.loads(scene_bytes)
    street_layout = json.loads(STREET_LAYOUT.read_text(encoding="utf-8"))
    layout = street_layout if scene["id"] == street_layout["scene_id"] else {}
    citizens_config = None
    if CITIZENS_LAYOUT.exists():
        citizens_layout = json.loads(CITIZENS_LAYOUT.read_text(encoding="utf-8"))
        if scene["id"] == citizens_layout["scene_id"]:
            citizens_config = citizens_layout
    package = build(
        scene, report, layout.get("sidewalk_widths_m"), layout.get("vehicle"),
        citizens_config, layout.get("default_sidewalk_widths_m"),
    )
    package["source_scene_sha256"] = sha256(scene_bytes).hexdigest()
    destination = args.scene.with_name("unreal-city-meshes.json")
    write_json(destination, package)
    print(f"{len(package['meshes'])} meshes, "
          f"{sum(len(mesh['triangles']) for mesh in package['meshes'].values())} triangles: {destination}")


if __name__ == "__main__":
    main()
