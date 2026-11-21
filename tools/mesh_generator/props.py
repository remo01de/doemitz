"""Generate deterministic instance transforms for stylized old-town props and vegetation."""

from math import atan2, degrees, hypot

from shapely import union_all
from shapely.geometry import Point, shape
from shapely.ops import nearest_points


def _far_enough(x, y, existing_points, min_dist):
    min_sq = min_dist * min_dist
    for px, py in existing_points:
        dx = x - px
        dy = y - py
        if dx * dx + dy * dy < min_sq:
            return False
    return True


def _ue_yaw_deg(dx_east, dy_north):
    # In Unreal: X = North, Y = East, so heading vector is (dy_north, dx_east)
    return round(degrees(atan2(dx_east, dy_north)), 2)


def _eval_z(elevation_or_fn, x, y):
    return float(elevation_or_fn(x, y)) if callable(elevation_or_fn) else float(elevation_or_fn)


def add_street_lamps(meshes, roads, sidewalks, base_m, sidewalk_elevation_m, detailed_road_ids):
    """Collect deterministic HISM instance transforms for lamps, benches, planters, and bollards."""
    del meshes, base_m
    empty = {"street_lamps": [], "benches": [], "planters": [], "bollards": []}
    if not sidewalks or not detailed_road_ids:
        return [], empty
    sidewalk_safe = union_all([poly.buffer(-0.22) for poly in sidewalks])
    if sidewalk_safe.is_empty:
        return [], empty

    lamp_lights = []
    lamp_xy = []
    light_xy = []
    bench_xy = []
    bollard_xy = []

    instances = {
        "street_lamps": [],
        "benches": [],
        "planters": [],
        "bollards": [],
    }

    for road in roads:
        if road["id"] not in detailed_road_ids:
            continue
        line = shape(road["geometry"])
        length = line.length
        if length < 14.0:
            continue
        distance = 10.0
        index = 0
        while distance < length - 6.0:
            center = line.interpolate(distance)
            before = line.interpolate(max(0.0, distance - 0.5))
            after = line.interpolate(min(length, distance + 0.5))
            dx, dy = after.x - before.x, after.y - before.y
            norm = hypot(dx, dy)
            if norm > 1e-6:
                tx, ty = dx / norm, dy / norm
                yaw_deg = _ue_yaw_deg(tx, ty)
                side = 1.0 if index % 2 == 0 else -1.0
                cand = Point(center.x - ty * side * 3.55, center.y + tx * side * 3.55)
                if not sidewalk_safe.contains(cand):
                    _, nearest = nearest_points(cand, sidewalk_safe)
                    if cand.distance(nearest) <= 1.4:
                        cand = nearest
                    else:
                        distance += 20.0
                        index += 1
                        continue

                x, y = cand.x, cand.y
                z = round(_eval_z(sidewalk_elevation_m, x, y), 4)
                if _far_enough(x, y, lamp_xy, 16.0):
                    lamp_xy.append((x, y))
                    instances["street_lamps"].append([round(x, 4), round(y, 4), z, yaw_deg])
                    # Keep dynamic point light spacing balanced across the old town
                    if _far_enough(x, y, light_xy, 28.0):
                        light_xy.append((x, y))
                        lamp_lights.append([round(x, 4), round(y, 4), round(z + 3.78, 4)])

                if index % 2 == 0 and distance + 4.5 < length - 6.0:
                    b_center = line.interpolate(distance + 4.5)
                    b_pt = Point(b_center.x - ty * side * 4.15, b_center.y + tx * side * 4.15)
                    if (
                        sidewalk_safe.contains(b_pt)
                        and _far_enough(b_pt.x, b_pt.y, bench_xy, 22.0)
                        and _far_enough(b_pt.x, b_pt.y, lamp_xy, 3.0)
                    ):
                        bx, by = b_pt.x, b_pt.y
                        bz = round(_eval_z(sidewalk_elevation_m, bx, by), 4)
                        bench_xy.append((bx, by))
                        bench_yaw = yaw_deg if side > 0 else round((yaw_deg + 180.0) % 360.0, 2)
                        instances["benches"].append([round(bx, 4), round(by, 4), bz, bench_yaw])

                        p_pt = Point(bx + tx * 1.25, by + ty * 1.25)
                        if sidewalk_safe.contains(p_pt):
                            pz = round(_eval_z(sidewalk_elevation_m, p_pt.x, p_pt.y), 4)
                            instances["planters"].append([round(p_pt.x, 4), round(p_pt.y, 4), pz, bench_yaw])

                if distance + 10.0 < length - 6.0:
                    pol_center = line.interpolate(distance + 10.0)
                    pol_pt = Point(pol_center.x - ty * side * 3.35, pol_center.y + tx * side * 3.35)
                    if (
                        sidewalk_safe.contains(pol_pt)
                        and _far_enough(pol_pt.x, pol_pt.y, bollard_xy, 12.0)
                        and _far_enough(pol_pt.x, pol_pt.y, lamp_xy, 3.0)
                    ):
                        bollard_xy.append((pol_pt.x, pol_pt.y))
                        pol_z = round(_eval_z(sidewalk_elevation_m, pol_pt.x, pol_pt.y), 4)
                        instances["bollards"].append([round(pol_pt.x, 4), round(pol_pt.y, 4), pol_z, yaw_deg])
            distance += 20.0
            index += 1
    return lamp_lights, instances


def add_stylized_trees(meshes, bounds, excluded_area, base_m):
    """Deterministically collect HISM instance transforms for stylized broad-leaf trees & bushes."""
    del meshes
    forbidden = excluded_area.buffer(3.2)
    minx, miny, maxx, maxy = bounds.bounds
    step = 26.0
    trees = []
    bushes = []

    gx = minx + 12.0
    ix = 0
    while gx < maxx - 12.0:
        gy = miny + 12.0
        iy = 0
        while gy < maxy - 12.0:
            h = (ix * 73856093 ^ iy * 19349663) & 0xFFFFFFFF
            jx = ((h % 100) / 100.0 - 0.5) * 9.0
            jy = (((h // 100) % 100) / 100.0 - 0.5) * 9.0
            pt = Point(gx + jx, gy + jy)
            if bounds.contains(pt) and not forbidden.contains(pt):
                variant = h % 3
                yaw_deg = float(h % 360)
                tz = round(_eval_z(base_m, pt.x, pt.y), 4)
                if h % 4 == 0:
                    scale = round(0.85 + (h % 5) * 0.12, 3)
                    bushes.append([round(pt.x, 4), round(pt.y, 4), tz, yaw_deg, scale, variant])
                else:
                    scale = round(0.82 + (h % 7) * 0.08, 3)
                    trees.append([round(pt.x, 4), round(pt.y, 4), tz, yaw_deg, scale, variant])
            gy += step
            iy += 1
        gx += step
        ix += 1
    return {"trees": trees, "bushes": bushes}
