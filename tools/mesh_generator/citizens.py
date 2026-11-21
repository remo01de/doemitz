"""Compile deterministic citizen places, schedules, and pedestrian routes from OSM data."""

from math import ceil, hypot

from shapely import union_all
from shapely.geometry import Point, shape
from shapely.ops import nearest_points


VALID_ACTIVITIES = {"Home", "Working", "Shopping", "Strolling"}
ROUTE_STEP_M = 4.0


def _side_sign(line, point):
    along = line.project(point)
    before = line.interpolate(max(0.0, along - 0.5))
    after = line.interpolate(min(line.length, along + 0.5))
    cross = (after.x - before.x) * (point.y - before.y) - (after.y - before.y) * (point.x - before.x)
    return 1.0 if cross >= 0.0 else -1.0


def _offset_point(line, distance_m, lateral_m):
    clamped = max(0.0, min(line.length, distance_m))
    center = line.interpolate(clamped)
    before = line.interpolate(max(0.0, clamped - 0.5))
    after = line.interpolate(min(line.length, clamped + 0.5))
    dx = after.x - before.x
    dy = after.y - before.y
    norm = hypot(dx, dy)
    if norm <= 1e-9:
        return center
    # Left normal is (-dy, dx) / norm
    return Point(center.x - (dy / norm) * lateral_m, center.y + (dx / norm) * lateral_m)


def _route_points(start_place, end_place, road_line, lateral_offset_m, sidewalk_area,
                  road_elevation_m, sidewalk_elevation_m, obstacles):
    start_xy = Point(start_place["access_m"][0], start_place["access_m"][1])
    end_xy = Point(end_place["access_m"][0], end_place["access_m"][1])
    start_along = start_place["along_m"]
    end_along = end_place["along_m"]
    start_side = start_place["side"]
    end_side = end_place["side"]

    points = [start_place["access_m"]]
    span = abs(end_along - start_along)
    steps = max(2, ceil(span / ROUTE_STEP_M))

    def append_point(pt, prefer_sidewalk=True):
        if prefer_sidewalk and not sidewalk_area.is_empty and sidewalk_area.contains(pt):
            z = sidewalk_elevation_m
        elif not obstacles.is_empty and obstacles.contains(pt):
            _, safe = nearest_points(pt, sidewalk_area if not sidewalk_area.is_empty else road_line)
            pt = safe
            z = sidewalk_elevation_m if not sidewalk_area.is_empty and sidewalk_area.covers(pt) else road_elevation_m
        else:
            z = road_elevation_m
        coord = [round(pt.x, 4), round(pt.y, 4), round(z, 4)]
        if coord != points[-1]:
            points.append(coord)

    # Walk along the starting side sidewalk, crossing at the destination's projection if sides differ.
    for step in range(1, steps):
        fraction = step / steps
        along = start_along + (end_along - start_along) * fraction
        candidate = _offset_point(road_line, along, start_side * lateral_offset_m)
        if not sidewalk_area.is_empty and not sidewalk_area.contains(candidate):
            # Snap nearby sidewalk points back onto the walkable sidewalk if close; otherwise cross at road level.
            _, nearest_sw = nearest_points(candidate, sidewalk_area)
            if candidate.distance(nearest_sw) <= 1.2:
                candidate = nearest_sw
        append_point(candidate, prefer_sidewalk=True)

    if start_side != end_side:
        # Step onto the carriageway at end_along to cross cleanly to the opposite sidewalk.
        mid = road_line.interpolate(end_along)
        append_point(mid, prefer_sidewalk=False)

    if end_place["access_m"] != points[-1]:
        points.append(end_place["access_m"])

    # Validate that no route point falls inside a building or water obstacle.
    for east, north, _ in points:
        if not obstacles.is_empty and obstacles.contains(Point(east, north)):
            raise ValueError(
                f"citizen route from {start_place['id']} to {end_place['id']} intersects an obstacle "
                f"near ({east:.1f}, {north:.1f}) m"
            )
    return points


def build_citizens(config, roads, buildings, sidewalks, obstacles, road_elevation_m, sidewalk_elevation_m):
    """Validate citizen manifest and compile places, schedules, and pedestrian routes."""
    clock = config.get("clock", {})
    start_minute = float(clock.get("start_minute", 470))
    time_scale = float(clock.get("time_scale", 60.0))
    if not 0.0 <= start_minute < 1440.0 or not 0.0 < time_scale <= 3600.0:
        raise ValueError("invalid citizen simulation clock configuration")

    pilot_road_id = config["pilot_road_id"]
    if pilot_road_id not in roads:
        raise ValueError(f"pilot road {pilot_road_id} not found in scene")
    pilot_road, pilot_width_m = roads[pilot_road_id]
    road_line = shape(pilot_road["geometry"])

    sidewalk_union = union_all(sidewalks) if sidewalks else union_all([])
    sidewalk_interior = union_all([polygon.buffer(-0.35) for polygon in sidewalks]) if sidewalks else union_all([])
    walkable_access = sidewalk_interior if not sidewalk_interior.is_empty else sidewalk_union

    buildings_by_id = {feature["id"]: shape(feature["geometry"]) for feature in buildings}
    places_out = []
    places_by_id = {}
    for entry in config["places"]:
        place_id = entry["id"]
        building_id = entry["building_id"]
        if not place_id or place_id in places_by_id:
            raise ValueError(f"duplicate or empty place id: {place_id!r}")
        if building_id not in buildings_by_id:
            raise ValueError(f"place {place_id} references unknown building {building_id}")
        building_geom = buildings_by_id[building_id]
        if walkable_access.is_empty:
            _, access_pt = nearest_points(building_geom, road_line)
            elevation = road_elevation_m
        else:
            _, access_pt = nearest_points(building_geom, walkable_access)
            elevation = sidewalk_elevation_m
        along_m = road_line.project(access_pt)
        side = _side_sign(road_line, access_pt)
        compiled = {
            "id": place_id,
            "name": entry["name"],
            "building_id": building_id,
            "kind": entry["kind"],
            "along_m": round(along_m, 4),
            "side": side,
            "access_m": [round(access_pt.x, 4), round(access_pt.y, 4), round(elevation, 4)],
        }
        places_out.append(compiled)
        places_by_id[place_id] = compiled

    citizens_out = []
    seen_citizens = set()
    needed_pairs = set()
    for entry in config["citizens"]:
        citizen_id = entry["id"]
        if not citizen_id or citizen_id in seen_citizens:
            raise ValueError(f"duplicate or empty citizen id: {citizen_id!r}")
        seen_citizens.add(citizen_id)
        home_id = entry["home_place_id"]
        work_id = entry["work_place_id"]
        if home_id not in places_by_id or work_id not in places_by_id:
            raise ValueError(f"citizen {citizen_id} references unknown home or work place")
        speed_mps = float(entry["walk_speed_mps"])
        if not 0.5 <= speed_mps <= 3.0:
            raise ValueError(f"citizen {citizen_id} has invalid walk_speed_mps: {speed_mps}")
        coat = entry["coat_color"]
        if len(coat) != 3 or not all(0.0 <= float(c) <= 1.0 for c in coat):
            raise ValueError(f"citizen {citizen_id} has invalid coat_color")

        schedule = entry["schedule"]
        if not schedule or schedule[0]["start_minute"] != 0:
            raise ValueError(f"citizen {citizen_id} schedule must start at minute 0")
        last_minute = -1
        schedule_out = []
        for step in schedule:
            minute = int(step["start_minute"])
            activity = step["activity"]
            place_id = step["place_id"]
            if not (0 <= minute < 1440) or minute <= last_minute:
                raise ValueError(f"citizen {citizen_id} schedule minutes must strictly increase in [0, 1440)")
            if activity not in VALID_ACTIVITIES:
                raise ValueError(f"citizen {citizen_id} has unsupported activity {activity!r}")
            if place_id not in places_by_id:
                raise ValueError(f"citizen {citizen_id} schedule references unknown place {place_id}")
            last_minute = minute
            schedule_out.append({
                "start_minute": minute,
                "activity": activity,
                "place_id": place_id,
            })

        for index, current in enumerate(schedule_out):
            nxt = schedule_out[(index + 1) % len(schedule_out)]
            if current["place_id"] != nxt["place_id"]:
                needed_pairs.add((current["place_id"], nxt["place_id"]))

        citizens_out.append({
            "id": citizen_id,
            "name": entry["name"],
            "home_place_id": home_id,
            "work_place_id": work_id,
            "walk_speed_mps": speed_mps,
            "coat_color": [float(c) for c in coat],
            "schedule": schedule_out,
        })

    lateral_offset_m = pilot_width_m / 2.0 + 0.8
    routes_out = []
    for start_id, end_id in sorted(needed_pairs):
        pts = _route_points(
            places_by_id[start_id], places_by_id[end_id],
            road_line, lateral_offset_m, walkable_access,
            road_elevation_m, sidewalk_elevation_m, obstacles,
        )
        routes_out.append({
            "from_place_id": start_id,
            "to_place_id": end_id,
            "points_m": pts,
        })

    return {
        "pilot_road_id": pilot_road_id,
        "clock": {
            "start_minute": start_minute,
            "time_scale": time_scale,
        },
        "places": [
            {k: v for k, v in place.items() if k not in {"along_m", "side"}}
            for place in places_out
        ],
        "citizens": citizens_out,
        "routes": routes_out,
    }
