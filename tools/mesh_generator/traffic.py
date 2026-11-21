"""Compile a closed test route from connected OpenStreetMap ways."""

from math import ceil, dist

from shapely import union_all
from shapely.geometry import LineString, Polygon, shape


DRIVABLE = {"primary", "secondary", "tertiary", "residential", "living_street", "unclassified", "service"}


def junction(first, second):
    shared = set(first) & set(second)
    if len(shared) != 1:
        raise ValueError("consecutive pilot roads must share exactly one mapped junction")
    return next(iter(shared))


def route_vertices(roads):
    axes = []
    for road in roads:
        tags = road["properties"]
        axis = shape(road["geometry"])
        if (axis.geom_type != "LineString" or tags["highway"] not in DRIVABLE
                or tags.get("tunnel", "no") != "no" or tags.get("bridge", "no") != "no"):
            raise ValueError(f"{road['id']} is unsuitable for the flat vehicle route")
        axes.append(list(axis.coords))

    vertices = []
    for index, (road, points) in enumerate(zip(roads, axes)):
        entry = points.index(junction(points, axes[index - 1]))
        exit = points.index(junction(points, axes[(index + 1) % len(axes)]))
        oneway = road["properties"].get("oneway", "no")
        if entry == exit or (entry > exit and oneway == "yes") or (entry < exit and oneway == "-1"):
            raise ValueError(f"{road['id']} enters and leaves in an invalid direction")
        step = 1 if entry < exit else -1
        vertices.extend(points[node] for node in range(entry, exit, step))
    return vertices


def toward(origin, target, distance):
    fraction = distance / dist(origin, target)
    return tuple(a + (b - a) * fraction for a, b in zip(origin, target))


def rounded_route(vertices, trim_m):
    points = []
    for i, corner in enumerate(vertices):
        previous = vertices[i - 1]
        following = vertices[(i + 1) % len(vertices)]
        trim = min(trim_m, dist(previous, corner) / 3, dist(corner, following) / 3)
        entry = toward(corner, previous, trim)
        exit = toward(corner, following, trim)
        for step in range(13):
            t = step / 12
            points.append(tuple(
                (1 - t) ** 2 * a + 2 * (1 - t) * t * b + t ** 2 * c
                for a, b, c in zip(entry, corner, exit)
            ))
    return points


def verify_vehicle_clearance(points, corridor, obstacles):
    for start, end in zip(points, [*points[1:], points[0]]):
        length = dist(start, end)
        forward_east = (end[0] - start[0]) / length
        forward_north = (end[1] - start[1]) / length
        samples = ceil(length / 0.5)
        for step in range(samples + 1):
            east, north = toward(start, end, step * length / samples)
            footprint = Polygon([
                (east + x * forward_east + y * forward_north, north + x * forward_north - y * forward_east)
                for x, y in ((-1.95, -0.93), (1.95, -0.93), (1.95, 0.93), (-1.95, 0.93))
            ])
            if not corridor.covers(footprint) or obstacles.intersects(footprint):
                raise ValueError(f"vehicle route leaves the carriageway near ({east:.1f}, {north:.1f}) m")


def build_vehicle_route(config, roads, bounds, obstacles, elevation):
    """Roads maps each available stable ID to its source feature and configured width."""
    road_ids = config["road_ids"]
    if len(road_ids) < 3 or len(set(road_ids)) != len(road_ids):
        raise ValueError("the pilot vehicle route requires at least three distinct roads")
    if not config["id"] or not config["route_id"] or not 0 < config["speed_kmh"] <= 50:
        raise ValueError("expected stable vehicle and route IDs and a valid pilot speed")
    trim = config["corner_trim_m"]
    if not 0 < trim <= 10:
        raise ValueError("invalid pilot corner trim")
    features_and_widths = [roads[road_id] for road_id in road_ids]
    vertices = route_vertices([feature for feature, _ in features_and_widths])
    points = rounded_route(vertices, trim)
    centerline = LineString([*points, points[0]])
    if not centerline.is_simple or not 0 <= config["start_distance_m"] < centerline.length:
        raise ValueError("pilot route must be a simple loop with a start distance on the route")
    corridor = union_all([
        shape(feature["geometry"]).buffer(width / 2, quad_segs=3)
        for feature, width in features_and_widths
    ]).intersection(bounds)
    verify_vehicle_clearance(points, corridor, obstacles)
    start_m = config["start_distance_m"]
    def _eval_z(e, n):
        return round(float(elevation(e, n)), 4) if callable(elevation) else float(elevation)

    return {
        "id": config["id"],
        "route_id": config["route_id"],
        "road_ids": road_ids,
        "speed_kmh": config["speed_kmh"],
        "start_distance_m": start_m,
        "length_m": centerline.length,
        "preview_pose_m": [
            (pt[0], pt[1], _eval_z(pt[0], pt[1]))
            for pt in (centerline.interpolate(distance % centerline.length).coords[0] for distance in (start_m, start_m + 0.1))
        ],
        "points_m": [(east, north, _eval_z(east, north)) for east, north in points],
    }
