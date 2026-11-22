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
from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.architecture import ROOF_STYLES, WALL_STYLES, add_stylized_building
from tools.mesh_generator.bridges import build_bridges_mesh
from tools.mesh_generator.citizens import build_citizens
from tools.mesh_generator.city_map import render_city_map
from tools.mesh_generator.economy import build_economy
from tools.mesh_generator.props import add_street_lamps, add_stylized_trees
from tools.mesh_generator.road_elevation import (
    DEFAULT_SMOOTHING_WINDOW_M,
    RoadElevationNetwork,
    densify_polygon,
    is_bridge_road,
)
from tools.mesh_generator.road_graph import build_road_graph
from tools.mesh_generator.tasks import build_tasks
from tools.mesh_generator.terrain import (
    DEFAULT_MAX_ERROR_M,
    DEFAULT_MAX_TRIANGLES,
    DEFAULT_TILE_SIZE_M,
    build_terrain_tiles,
)
from tools.mesh_generator.traffic import build_vehicle_route


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENE = ROOT / "data/processed/doemitz-altstadt/scene.json"
STREET_LAYOUT = ROOT / "data/manifests/doemitz-altstadt-streets.json"
CITIZENS_LAYOUT = ROOT / "data/manifests/doemitz-altstadt-citizens.json"
ECONOMY_LAYOUT = ROOT / "data/manifests/doemitz-altstadt-economy.json"
TASKS_LAYOUT = ROOT / "data/manifests/doemitz-altstadt-tasks.json"
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
        if callable(elevation_m):
            polygon = densify_polygon(polygon, max_segment_m=3.0)
            triangles = orient_polygons(constrained_delaunay_triangles(polygon))
            for triangle in triangles.geoms:
                self.triangles.append(
                    tuple(
                        self.vertex(xy, round(float(elevation_m(xy[0], xy[1])), 4))
                        for xy in list(triangle.exterior.coords)[:3]
                    )
                )
            return
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

    def add_draped_walls(self, polygon, top_z_fn, bottom_z_fn):
        polygon = densify_polygon(polygon, max_segment_m=3.0)
        for ring in (polygon.exterior, *polygon.interiors):
            points = list(ring.coords)
            for start, end in zip(points, points[1:]):
                if start == end:
                    continue
                top_a = round(float(top_z_fn(start[0], start[1])), 4)
                top_b = round(float(top_z_fn(end[0], end[1])), 4)
                bot_a = round(float(bottom_z_fn(start[0], start[1])), 4)
                bot_b = round(float(bottom_z_fn(end[0], end[1])), 4)
                offset = len(self.vertices)
                self.vertices.extend(
                    [(*start, bot_a), (*end, bot_b), (*end, top_b), (*start, top_a)]
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


def add_streets(
    meshes, roads, bounds, obstacles, base_m, sidewalk_widths,
    default_sidewalk_widths=None, road_network=None, elevation=None,
    road_polygons_out=None, non_bridge_sidewalks_out=None, building_obstacles=None,
):
    surfaces = {name: [] for name in ROAD_MESHES}
    bridge_road_buffers = []
    sidewalk_envelopes = []
    bridge_sidewalk_envelopes = []
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
        bridge_flag = is_bridge_road(tags)
        if bridge_flag:
            bridge_road_buffers.append(axis.buffer(width / 2, quad_segs=3, cap_style="flat"))
        else:
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
            env = axis.buffer(width / 2 + sidewalk_width, quad_segs=3, cap_style="flat")
            if bridge_flag:
                bridge_sidewalk_envelopes.append(env)
            else:
                sidewalk_envelopes.append(env)

    if eligible_ids != sidewalk_widths.keys():
        raise ValueError(f"missing eligible roads for sidewalks: {sorted(sidewalk_widths.keys() - eligible_ids)}")

    use_draped = road_network is not None and elevation is not None and not elevation.is_flat
    road_z_arg = road_network.road_surface_z if use_draped else (base_m + ROAD_ELEVATION_M)
    sidewalk_z_arg = road_network.sidewalk_surface_z if use_draped else (base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M)

    bridge_occupied = set_precision(union_all(bridge_road_buffers, grid_size=STREET_GRID_M), STREET_GRID_M)
    occupied = bridge_occupied
    for name, parts in surfaces.items():
        area = set_precision(union_all(parts, grid_size=STREET_GRID_M), STREET_GRID_M).intersection(bounds)
        for polygon in geometry_parts(area.difference(occupied), "Polygon"):
            meshes[name].add_surface(polygon, road_z_arg)
            if road_polygons_out is not None:
                road_polygons_out.append(polygon)
        occupied = occupied.union(area)

    # Regular sidewalks exclude roads, buildings, and water
    envelopes = set_precision(union_all(sidewalk_envelopes, grid_size=STREET_GRID_M), STREET_GRID_M)
    excluded = occupied.union(set_precision(obstacles, STREET_GRID_M))
    sidewalk_area = envelopes.intersection(bounds).difference(excluded)
    sidewalks = []
    for polygon in geometry_parts(orient_polygons(sidewalk_area), "Polygon"):
        if polygon.area < 0.08:
            continue
        sidewalks.append(polygon)
        if non_bridge_sidewalks_out is not None:
            non_bridge_sidewalks_out.append(polygon)
        meshes["Sidewalks"].add_surface(polygon, sidewalk_z_arg)
        if use_draped:
            def _curb_bottom(x, y):
                return min(
                    road_network.ground_elevation_at(x, y) - 0.20,
                    elevation.sample(x, y) - 0.30,
                )
            meshes["Sidewalks"].add_draped_walls(polygon, road_network.sidewalk_surface_z, _curb_bottom)
        else:
            meshes["Sidewalks"].add_walls(polygon, ROAD_ELEVATION_M + CURB_HEIGHT_M, base_m)

    # Bridge sidewalks span OVER water with 12 cm curb resting on the bridge deck (excluded only by roadway/buildings/regular sidewalks)
    if bridge_sidewalk_envelopes:
        b_env = set_precision(union_all(bridge_sidewalk_envelopes, grid_size=STREET_GRID_M), STREET_GRID_M)
        b_obs = occupied.union(set_precision(sidewalk_area, STREET_GRID_M))
        if building_obstacles is not None and not building_obstacles.is_empty:
            b_obs = b_obs.union(set_precision(building_obstacles, STREET_GRID_M))
        bridge_sw_area = b_env.intersection(bounds).difference(b_obs)
        for polygon in geometry_parts(orient_polygons(bridge_sw_area), "Polygon"):
            if polygon.area < 0.08:
                continue
            sidewalks.append(polygon)
            meshes["Sidewalks"].add_surface(polygon, sidewalk_z_arg)
            if use_draped:
                def _bridge_curb_bottom(x, y):
                    return road_network.road_surface_z(x, y) - 0.05
                meshes["Sidewalks"].add_draped_walls(polygon, road_network.sidewalk_surface_z, _bridge_curb_bottom)
            else:
                meshes["Sidewalks"].add_walls(polygon, CURB_HEIGHT_M + 0.02, base_m + ROAD_ELEVATION_M - 0.02)

    return width_sources, sidewalks


def build(
    scene, report, sidewalk_widths=None, vehicle_config=None,
    citizens_config=None, default_sidewalk_widths=None, traffic_network_config=None,
    economy_config=None, tasks_config=None, map_output_png=None, scene_dir=None,
):
    if scene["schema_version"] != 1 or scene["coordinates"]["local_axes"] != ["east", "north"]:
        raise ValueError("expected scene schema 1 with local [east, north] coordinates")
    terrain_kind = scene["terrain"]["kind"]
    if scene["coordinates"]["unit"] != "meter" or terrain_kind not in ("flat_placeholder", "dgm1"):
        raise ValueError(f"unsupported scene unit or terrain kind: {terrain_kind!r}")

    resolved_scene_dir = scene_dir if scene_dir is not None else (ROOT / "data" / "processed" / scene["id"])
    elevation = ElevationModel.from_scene(scene, scene_dir=resolved_scene_dir)
    assumptions = scene["terrain"].get("assumptions") or {}
    tile_size_m = int(assumptions.get("terrain_tile_size_m", DEFAULT_TILE_SIZE_M))
    max_error_m = float(assumptions.get("terrain_max_error_m", DEFAULT_MAX_ERROR_M))
    max_triangles = int(assumptions.get("terrain_max_triangles", DEFAULT_MAX_TRIANGLES))
    smoothing_window_m = float(assumptions.get("road_smoothing_window_m", DEFAULT_SMOOTHING_WINDOW_M))
    water_depression_m = float(assumptions.get("water_bank_depression_m", 0.05))

    meshes = {name: Mesh() for name in PALETTE}
    bounds = shape(scene["terrain"]["boundary"])
    base_m = float(scene["terrain"].get("elevation_m", 0.0)) if elevation.is_flat else 0.0

    # 1. Water bodies: fixed water level per waterbody (documented assumption strictly below bank heights)
    water_geoms = []
    water_surfaces: list[tuple] = []
    water_levels_report: list[dict] = []
    for feature in scene["layers"]["water"]:
        geom = shape(feature["geometry"])
        water_geoms.append(geom)
        polys = list(geometry_parts(geom, "Polygon"))
        if not polys:
            continue
        if elevation.is_flat:
            w_level = base_m + 0.04
            b_min = base_m
            b_max = base_m
            w_source = "flat_placeholder_offset_4cm"
        else:
            b_min = min(elevation.boundary_min_max(p)[0] for p in polys)
            b_max = max(elevation.boundary_min_max(p)[1] for p in polys)
            w_level = round(b_min - water_depression_m, 4)
            w_source = f"assumed_bank_min_minus_{int(round(water_depression_m * 100))}cm"
        for polygon in polys:
            meshes["Water"].add_surface(polygon, w_level)
            water_surfaces.append((polygon, w_level))
        water_levels_report.append({
            "id": feature["id"],
            "name": feature["properties"].get("name", ""),
            "bank_min_m": round(b_min, 4),
            "bank_max_m": round(b_max, 4),
            "water_level_m": round(w_level, 4),
            "water_level_nhn_m": round(elevation.local_to_nhn(w_level), 4),
            "source": w_source,
        })
    water = union_all(water_geoms)

    # 2. Buildings: foundation at lowest terrain under footprint, visible stone plinth on slopes
    height_sources = Counter()
    buildings = []
    building_entries: list[tuple] = []
    sloped_buildings = 0
    max_building_slope_m = 0.0
    building_min_z_by_geom_idx: list[float] = []
    for feature in scene["layers"]["buildings"]:
        osm_id = int(feature["id"].rsplit(":", 1)[1])
        height, source = building_height(feature["properties"])
        height_sources[source] += 1
        geometry = orient_polygons(shape(feature["geometry"]))
        buildings.append(geometry)
        polys = list(geometry_parts(geometry, "Polygon"))
        if elevation.is_flat:
            b_min_z = base_m
            b_max_z = base_m
        else:
            mins_maxs = [elevation.polygon_min_max(p) for p in polys]
            b_min_z = min(mm[0] for mm in mins_maxs)
            b_max_z = max(mm[1] for mm in mins_maxs)
            slope_diff = b_max_z - b_min_z
            if slope_diff > 0.05:
                sloped_buildings += 1
            if slope_diff > max_building_slope_m:
                max_building_slope_m = slope_diff
        building_min_z_by_geom_idx.append(b_min_z)
        for polygon in polys:
            add_stylized_building(
                meshes, polygon, height, round(b_min_z, 4), osm_id, feature["properties"],
                max_ground_m=round(b_max_z, 4),
            )
            building_entries.append((polygon, b_min_z))

    # 3. Roads, bridges & sidewalks draped along smoothed longitudinal profile, linear bridge decks, 12 cm curb
    sidewalk_widths = sidewalk_widths or {}
    default_sidewalk_widths = default_sidewalk_widths or {}
    building_union = union_all(buildings, grid_size=STREET_GRID_M) if buildings else union_all([], grid_size=STREET_GRID_M)
    obstacles = (
        union_all([water, *buildings], grid_size=STREET_GRID_M)
        if sidewalk_widths or default_sidewalk_widths or vehicle_config or citizens_config else water
    )
    roads = scene["layers"]["roads"]
    road_network = RoadElevationNetwork(
        elevation, roads, road_width, ROAD_ELEVATION_M, CURB_HEIGHT_M,
        smoothing_window_m=smoothing_window_m,
    )
    road_polygons: list = []
    non_bridge_sidewalks: list = []
    width_sources, sidewalks = add_streets(
        meshes, roads, bounds, obstacles, base_m, sidewalk_widths, default_sidewalk_widths,
        road_network=road_network, elevation=elevation,
        road_polygons_out=road_polygons, non_bridge_sidewalks_out=non_bridge_sidewalks,
        building_obstacles=building_union,
    )

    bridges_mesh, bridges_report, bridge_footprints = build_bridges_mesh(
        bridges=road_network.bridges,
        elevation=elevation,
        road_offset_m=ROAD_ELEVATION_M,
        curb_height_m=CURB_HEIGHT_M,
        sidewalk_widths=sidewalk_widths,
        default_sidewalk_widths=default_sidewalk_widths,
        water_surfaces=water_surfaces,
    )
    bridge_exclusion_zone = (
        union_all([fp.buffer(0.8) for fp in bridge_footprints], grid_size=STREET_GRID_M)
        if bridge_footprints
        else union_all([], grid_size=STREET_GRID_M)
    )

    # 4. Terrain mesh: simplified 64 m tiles for DGM1, single flat plane for flat_placeholder
    # Under bridges, terrain is NOT depressed for the road and water is NOT cut out.
    terrain_tiles: dict[str, dict] = {}
    if elevation.is_flat:
        meshes["Terrain"].add_surface(bounds, base_m)
        terrain_mesh_report = {
            "kind": "flat_placeholder",
            "tile_size_m": tile_size_m,
            "tile_count": 1,
            "triangle_count": len(meshes["Terrain"].triangles),
            "max_triangles_budget": max_triangles,
            "max_vertical_error_m": 0.0,
            "max_error_budget_m": max_error_m,
            "depressed_cells": 0,
        }
    else:
        terrain_tiles, terrain_mesh_report = build_terrain_tiles(
            elevation=elevation,
            bounds=bounds,
            water_surfaces=water_surfaces,
            road_polygons=road_polygons,
            sidewalk_polygons=non_bridge_sidewalks,
            building_entries=building_entries,
            road_ground_z_fn=road_network.ground_elevation_at,
            bridge_polygons=bridge_footprints,
            tile_size_m=tile_size_m,
            max_error_m=max_error_m,
            max_triangles=max_triangles,
        )

    road_z_resolver = road_network.road_surface_z if not elevation.is_flat else (base_m + ROAD_ELEVATION_M)
    sidewalk_z_resolver = road_network.sidewalk_surface_z if not elevation.is_flat else (base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M)
    terrain_z_resolver = elevation.sample if not elevation.is_flat else base_m
    parking_z_resolver = (
        (lambda x, y: elevation.sample(x, y) + ROAD_ELEVATION_M)
        if not elevation.is_flat
        else (base_m + ROAD_ELEVATION_M)
    )

    roads_by_id = {road["id"]: (road, road_width(road["properties"])[0]) for road in roads}
    road_buffers = [
        shape(road["geometry"]).buffer(width / 2, quad_segs=2)
        for road, width in roads_by_id.values()
        if road["properties"].get("tunnel", "no") == "no"
    ]
    excluded_for_trees = union_all(
        [water, *buildings, *road_buffers, *sidewalks, *bridge_footprints],
        grid_size=STREET_GRID_M,
    )
    detailed_road_ids = {
        road["id"]
        for road in roads
        if road["properties"].get("tunnel", "no") == "no"
        and not is_bridge_road(road["properties"])
        and (
            road["id"] in sidewalk_widths
            or road["properties"]["highway"] in default_sidewalk_widths
        )
    }
    lamp_lights, street_prop_instances = add_street_lamps(
        meshes, roads, sidewalks, base_m, sidewalk_z_resolver, detailed_road_ids,
        forbidden_area=bridge_exclusion_zone,
    )
    vegetation_instances = add_stylized_trees(meshes, bounds, excluded_for_trees, terrain_z_resolver)
    prop_instances = {**street_prop_instances, **vegetation_instances}
    road_graph = build_road_graph(
        roads, road_width, road_z_resolver,
        crossings=scene.get("crossings"),
        priority_signs=scene.get("priority_signs"),
        pois=scene["layers"].get("pois"),
        parking_elevation_fn=parking_z_resolver,
    )
    traffic_network = None
    if traffic_network_config:
        edges_by_id = {edge["id"]: edge for edge in road_graph["edges"]}
        compiled_vehicles = []
        seen_vehicle_ids = set()
        for entry in traffic_network_config.get("vehicles", []):
            vid = entry["id"]
            edge_id = entry["start_edge_id"]
            if not vid or vid in seen_vehicle_ids:
                raise ValueError(f"duplicate or invalid traffic vehicle id: {vid}")
            edge = edges_by_id.get(edge_id)
            if edge is None or edge["dead_end"]:
                raise ValueError(f"traffic vehicle {vid} references invalid or dead-end edge {edge_id}")
            start_m = float(entry.get("start_distance_m", 5.0))
            if not 0.0 <= start_m < edge["length_m"]:
                raise ValueError(f"traffic vehicle {vid} start_distance_m {start_m} out of range for {edge_id}")
            seen_vehicle_ids.add(vid)
            compiled_vehicles.append({
                "id": vid,
                "start_edge_id": edge_id,
                "start_distance_m": round(start_m, 3),
                "body_color": entry.get("body_color", [0.72, 0.22, 0.16]),
            })
        traffic_network = {
            "seed": int(traffic_network_config.get("seed", 202607)),
            "vehicles": compiled_vehicles,
        }
    vehicle = None
    if vehicle_config:
        vehicle = build_vehicle_route(
            vehicle_config, roads_by_id,
            bounds, obstacles, road_z_resolver,
        )
    citizens = None
    if citizens_config:
        citizens = build_citizens(
            citizens_config, roads_by_id, scene["layers"]["buildings"], sidewalks,
            obstacles, road_z_resolver, sidewalk_z_resolver,
            pois=scene["layers"].get("pois"),
            crossings=road_graph.get("crossings"),
            entrances=scene.get("entrances"),
        )
    economy = None
    if economy_config and citizens:
        economy = build_economy(economy_config, citizens["places"])
    tasks = None
    if tasks_config and citizens:
        tasks = build_tasks(tasks_config, citizens["places"], economy)
    city_map = None
    if map_output_png is not None:
        _, city_map = render_city_map(
            scene, road_width, sidewalks=sidewalks, output_png=map_output_png, elevation=elevation,
        )
    reference = report["reference"]
    if scene["id"] != report["id"]:
        raise ValueError("scene and report belong to different areas")
    reference_points = reference["local_points_m"]
    reference_points_3d = [
        [
            round(float(pt[0]), 4),
            round(float(pt[1]), 4),
            round(float(road_network.road_surface_z(pt[0], pt[1]) if not elevation.is_flat else (base_m + ROAD_ELEVATION_M)), 4),
        ]
        for pt in reference_points
    ]
    reference_dgm_z_m = [
        round(float(elevation.sample(pt[0], pt[1])), 4)
        for pt in reference_points
    ]
    reference_line = LineString(reference_points)
    start = reference_line.interpolate(0.5, normalized=True)
    nearest_building_idx = min(range(len(buildings)), key=lambda idx: buildings[idx].distance(start))
    nearest_building = buildings[nearest_building_idx]
    if nearest_building.distance(start) < 1.0 or water.distance(start) < 1.0:
        raise ValueError("player start on the reference street is obstructed")
    roof_probe = nearest_building.representative_point()
    roof_probe_z = building_min_z_by_geom_idx[nearest_building_idx]
    start_ground_z = road_network.road_surface_z(start.x, start.y) if not elevation.is_flat else base_m
    sidewalk_interior = union_all([polygon.buffer(-0.4) for polygon in sidewalks])
    sidewalk_probe = None
    if sidewalk_widths and sidewalk_interior.is_empty:
        raise ValueError("the configured sidewalks have no walkable interior")
    if not sidewalk_interior.is_empty:
        _, point = nearest_points(start, sidewalk_interior)
        sw_z = road_network.sidewalk_surface_z(point.x, point.y) if not elevation.is_flat else (base_m + ROAD_ELEVATION_M + CURB_HEIGHT_M)
        sidewalk_probe = [round(point.x, 4), round(point.y, 4), round(sw_z, 4)]

    # Open terrain probe for Unreal collision verification (pick first tree location if available, else origin)
    if prop_instances["trees"]:
        t0 = prop_instances["trees"][0]
        terrain_probe = [t0[0], t0[1], t0[2]]
    else:
        terrain_probe = [0.0, 0.0, round(float(elevation.sample(0.0, 0.0)), 4)]

    compiled_meshes = {
        name: {
            "color": PALETTE[name],
            "collision": (
                name in {"Terrain", "Sidewalks", "Roads", "Paving", "Paths"}
                or name in WALLS
                or name in ROOFS
            ),
            "vertices": mesh.vertices,
            "triangles": mesh.triangles,
        }
        for name, mesh in meshes.items() if mesh.triangles
    }
    for tile_name, tile_data in terrain_tiles.items():
        compiled_meshes[tile_name] = {
            "color": PALETTE["Terrain"],
            "material": "Terrain",
            "collision": True,
            "vertices": tile_data["vertices"],
            "triangles": tile_data["triangles"],
        }
    if bridges_mesh is not None:
        compiled_meshes["Bridges"] = bridges_mesh

    terrain_attribution = scene["terrain"].get("attribution", "")
    terrain_license = scene["terrain"].get("license", "")
    return {
        "schema_version": 1,
        "attribution": scene["attribution"],
        "attribution_url": scene["attribution_url"],
        "terrain_attribution": terrain_attribution,
        "terrain_license": terrain_license,
        "bridges": bridges_report,
        "terrain": {
            "kind": terrain_kind,
            "reference_elevation_m": float(scene["terrain"].get("reference_elevation_m", 0.0)),
            "attribution": terrain_attribution,
            "license": terrain_license,
            "delivery_year": scene["terrain"].get("delivery_year"),
            "mesh": terrain_mesh_report,
            "bridges": bridges_report,
            "water_levels": water_levels_report,
            "roads_elevation": {
                "smoothing_window_m": road_network.smoothing_window_m,
                "max_slope_overall_percent": round(road_network.max_slope_overall(), 2),
                "road_count": len(road_network.road_reports),
                "roads": road_network.road_reports,
            },
            "buildings_elevation": {
                "count": len(buildings),
                "sloped_count": sloped_buildings,
                "max_footprint_slope_m": round(max_building_slope_m, 4),
            },
        },
        "bounds_m": bounds.bounds,
        "reference_points_m": reference_points,
        "reference_points_3d_m": reference_points_3d,
        "reference_dgm_z_m": reference_dgm_z_m,
        "reference_geodesic_m": reference["geodesic_m"],
        "maximum_relative_error": reference["maximum_relative_error"],
        "start_m": [round(start.x, 4), round(start.y, 4), round(start_ground_z + 1.0, 4)],
        "roof_probe_m": [round(roof_probe.x, 4), round(roof_probe.y, 4), round(roof_probe_z, 4)],
        "sidewalk_probe_m": sidewalk_probe,
        "terrain_probe_m": terrain_probe,
        "road-graph": road_graph,
        "traffic_network": traffic_network,
        "vehicle": vehicle,
        "citizens": citizens,
        "economy": economy,
        "tasks": tasks,
        "city_map": city_map,
        "sidewalks": {
            "width_source": "estimated_from_pilot_layout",
            "widths_m": sidewalk_widths,
            "curb_height_m": CURB_HEIGHT_M,
            "area_m2": round(sum(polygon.area for polygon in sidewalks), 2),
        },
        "height_sources": dict(height_sources),
        "width_sources": dict(width_sources),
        "props": {
            "street_lamps": len(prop_instances["street_lamps"]),
            "lamp_lights_m": lamp_lights,
            "benches": len(prop_instances["benches"]),
            "planters": len(prop_instances["planters"]),
            "bollards": len(prop_instances["bollards"]),
            "trees_and_bushes": len(prop_instances["trees"]) + len(prop_instances["bushes"]),
            "instances": prop_instances,
        },
        "meshes": compiled_meshes,
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
    economy_config = None
    if ECONOMY_LAYOUT.exists():
        economy_layout = json.loads(ECONOMY_LAYOUT.read_text(encoding="utf-8"))
        if scene["id"] == economy_layout["scene_id"]:
            economy_config = economy_layout
    tasks_config = None
    if TASKS_LAYOUT.exists():
        tasks_layout = json.loads(TASKS_LAYOUT.read_text(encoding="utf-8"))
        if scene["id"] == tasks_layout["scene_id"]:
            tasks_config = tasks_layout
    map_png_path = args.scene.with_name("city-map.png")
    package = build(
        scene, report, layout.get("sidewalk_widths_m"), layout.get("vehicle"),
        citizens_config, layout.get("default_sidewalk_widths_m"), layout.get("traffic_network"),
        economy_config, tasks_config, map_output_png=map_png_path, scene_dir=args.scene.parent,
    )
    package["source_scene_sha256"] = sha256(scene_bytes).hexdigest()
    destination = args.scene.with_name("unreal-city-meshes.json")
    write_json(destination, package)
    if package.get("terrain"):
        tr = package["terrain"]
        tm = tr["mesh"]
        re_info = tr["roads_elevation"]
        print(
            f"Terrain ({tr['kind']}): {tm['tile_count']} tile(s), {tm['triangle_count']} tris "
            f"(budget {tm['max_triangles_budget']}), max_err={tm['max_vertical_error_m']*100:.2f} cm "
            f"(budget {tm['max_error_budget_m']*100:.1f} cm), "
            f"max_road_slope={re_info['max_slope_overall_percent']:.2f}%, "
            f"sloped_buildings={tr['buildings_elevation']['sloped_count']}/{tr['buildings_elevation']['count']}, "
            f"bridges={len(tr.get('bridges', []))}"
        )
    if package.get("city_map"):
        write_json(args.scene.with_name("city-map-meta.json"), package["city_map"])
        cm = package["city_map"]
        print(
            f"CityMap: {cm['width_px']}x{cm['height_px']} px "
            f"({cm['meters_per_pixel']:.4f} m/px, sha256={cm['image_sha256'][:12]}...): {map_png_path}"
        )
    if package.get("citizens"):
        cit = package["citizens"]
        osm_oh = cit.get("osm_opening_hours_places", [])
        ent_rep = cit.get("osm_entrances_report", [])
        used_ent = sum(1 for item in ent_rep if item["status"] == "used")
        print(
            f"Citizens: {len(cit['citizens'])}, places: {len(cit['places'])}, "
            f"routes: {len(cit['routes'])} ({cit.get('routes_using_crossings', 0)} via crossings), "
            f"entrances: {cit.get('entrance_sources', {})} (OSM {used_ent}/{len(ent_rep)} used), "
            f"opening_hours_sources: {cit.get('opening_hours_sources', {})}"
        )
        if osm_oh:
            osm_summary = ", ".join(f"{p['name']} ({p['raw']})" for p in osm_oh)
            print(f"OSM opening_hours ({len(osm_oh)}): {osm_summary}")
    if package.get("road-graph"):
        rg = package["road-graph"]
        prio_junctions = sum(1 for j in rg.get("junctions", []) if j["rule"] == "priority_sign")
        print(
            f"RoadGraph: {rg['edge_count']} edges, {rg['junction_count']} junctions "
            f"({prio_junctions} priority_sign, {rg['junction_count'] - prio_junctions} right_before_left), "
            f"{rg['priority_sign_count']} signs, {rg['parking_lot_count']} parking lots"
        )
    if package.get("economy"):
        econ = package["economy"]
        print(
            f"Economy: start={econ['starting_money_cents']} ct ({econ['starting_money_source']}), "
            f"{econ['item_count']} items, {econ['job_count']} jobs (seed={econ['economy_seed']})"
        )
    if package.get("tasks"):
        tsk = package["tasks"]
        print(
            f"Tasks: {tsk['template_count']} templates "
            f"({tsk['errand_count']} errands, {tsk['fetch_count']} fetches, "
            f"{tsk['daily_min_tasks']}-{tsk['daily_max_tasks']}/day, seed={tsk['task_seed']})"
        )
    print(f"{len(package['meshes'])} meshes, "
          f"{sum(len(mesh['triangles']) for mesh in package['meshes'].values())} triangles: {destination}")


if __name__ == "__main__":
    main()
