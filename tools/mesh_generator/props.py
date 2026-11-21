"""Generate stylized old-town street lamps, planters, and trees deterministically."""

from math import cos, hypot, sin, tau

from shapely import union_all
from shapely.geometry import Point, shape
from shapely.ops import nearest_points


def _add_cylinder(mesh, cx, cy, z0, z1, r0, r1, sides=8):
    base = len(mesh.vertices)
    for i in range(sides):
        a = tau * i / sides
        mesh.vertices.append((cx + r0 * cos(a), cy + r0 * sin(a), z0))
    for i in range(sides):
        a = tau * i / sides
        mesh.vertices.append((cx + r1 * cos(a), cy + r1 * sin(a), z1))
    top = base + sides
    for i in range(sides):
        j = (i + 1) % sides
        mesh.triangles.extend(((base + i, base + j, top + j), (base + i, top + j, top + i)))
    for i in range(1, sides - 1):
        mesh.triangles.extend(((base, base + i + 1, base + i), (top, top + i, top + i + 1)))


def _add_canopy_blob(mesh, cx, cy, cz, rx, ry, rz):
    """Low-poly stylized rounded foliage cluster."""
    sides = 6
    rings = [
        (cz - rz, 0.15),
        (cz - rz * 0.30, 0.90),
        (cz + rz * 0.35, 0.95),
        (cz + rz, 0.15),
    ]
    base = len(mesh.vertices)
    for z, scale in rings:
        for i in range(sides):
            a = tau * i / sides
            mesh.vertices.append((cx + rx * scale * cos(a), cy + ry * scale * sin(a), z))
    for r in range(len(rings) - 1):
        b0 = base + r * sides
        b1 = b0 + sides
        for i in range(sides):
            j = (i + 1) % sides
            mesh.triangles.extend(((b0 + i, b0 + j, b1 + j), (b0 + i, b1 + j, b1 + i)))
    top = base + (len(rings) - 1) * sides
    for i in range(1, sides - 1):
        mesh.triangles.extend(((base, base + i + 1, base + i), (top, top + i, top + i + 1)))


def _add_box(mesh, cx, cy, z0, z1, hx, hy, tx, ty):
    """Add an oriented box centered at (cx, cy) with half-extents (hx, hy) along (tx, ty) and its left normal."""
    nx, ny = -ty, tx
    corners = (
        (cx - tx * hx - nx * hy, cy - ty * hx - ny * hy),
        (cx + tx * hx - nx * hy, cy + ty * hx - ny * hy),
        (cx + tx * hx + nx * hy, cy + ty * hx + ny * hy),
        (cx - tx * hx + nx * hy, cy - ty * hx + ny * hy),
    )
    b = [(x, y, z0) for x, y in corners]
    t = [(x, y, z1) for x, y in corners]
    base = len(mesh.vertices)
    mesh.vertices.extend(b + t)
    # 4 sides + top + bottom (CCW outward)
    for i in range(4):
        j = (i + 1) % 4
        mesh.triangles.extend(((base + i, base + j, base + 4 + j), (base + i, base + 4 + j, base + 4 + i)))
    mesh.triangles.extend((
        (base + 4, base + 5, base + 6), (base + 4, base + 6, base + 7),
        (base + 0, base + 2, base + 1), (base + 0, base + 3, base + 2),
    ))


def _far_enough(x, y, existing_points, min_dist):
    min_sq = min_dist * min_dist
    for px, py in existing_points:
        dx = x - px
        dy = y - py
        if dx * dx + dy * dy < min_sq:
            return False
    return True


def add_street_lamps(meshes, roads, sidewalks, base_m, sidewalk_elevation_m, detailed_road_ids):
    """Place classic old-town street lamps, benches, bollards, and planters along all detailed sidewalks."""
    if not sidewalks or not detailed_road_ids:
        return [], 0, 0, 0
    sidewalk_safe = union_all([poly.buffer(-0.22) for poly in sidewalks])
    if sidewalk_safe.is_empty:
        return [], 0, 0, 0

    metal = meshes["LampMetal"]
    glow = meshes["LanternGlow"]
    timber = meshes["TimberTrim"]
    terracotta = meshes["WallsTerracotta"]
    foliage = meshes["FoliageLight"]

    lamp_lights = []
    lamp_xy = []
    light_xy = []
    bench_xy = []
    bollard_xy = []

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
                z = sidewalk_elevation_m
                if _far_enough(x, y, lamp_xy, 16.0):
                    lamp_xy.append((x, y))
                    _add_cylinder(metal, x, y, z, z + 0.45, 0.16, 0.11, 8)
                    _add_cylinder(metal, x, y, z + 0.45, z + 3.45, 0.08, 0.055, 8)
                    _add_cylinder(metal, x, y, z + 3.45, z + 3.55, 0.14, 0.18, 6)
                    _add_cylinder(glow, x, y, z + 3.55, z + 3.98, 0.15, 0.19, 6)
                    _add_cylinder(metal, x, y, z + 3.98, z + 4.22, 0.24, 0.04, 6)
                    # Keep dynamic point light spacing balanced across the whole old town for Iris Xe performance
                    if _far_enough(x, y, light_xy, 28.0):
                        light_xy.append((x, y))
                        lamp_lights.append([round(x, 4), round(y, 4), round(z + 3.78, 4)])

                # Stylized wooden bench + terracotta planter along sidewalks
                if index % 2 == 0 and distance + 4.5 < length - 6.0:
                    b_center = line.interpolate(distance + 4.5)
                    b_pt = Point(b_center.x - ty * side * 4.15, b_center.y + tx * side * 4.15)
                    if sidewalk_safe.contains(b_pt) and _far_enough(b_pt.x, b_pt.y, bench_xy, 22.0) and _far_enough(b_pt.x, b_pt.y, lamp_xy, 3.0):
                        bx, by = b_pt.x, b_pt.y
                        bench_xy.append((bx, by))
                        _add_box(metal, bx - tx * 0.65, by - ty * 0.65, z, z + 0.44, 0.06, 0.24, tx, ty)
                        _add_box(metal, bx + tx * 0.65, by + ty * 0.65, z, z + 0.44, 0.06, 0.24, tx, ty)
                        _add_box(timber, bx, by, z + 0.42, z + 0.49, 0.80, 0.26, tx, ty)
                        _add_box(timber, bx - ty * side * 0.22, by + tx * side * 0.22, z + 0.56, z + 0.86, 0.80, 0.05, tx, ty)

                        p_pt = Point(bx + tx * 1.25, by + ty * 1.25)
                        if sidewalk_safe.contains(p_pt):
                            _add_cylinder(terracotta, p_pt.x, p_pt.y, z, z + 0.46, 0.22, 0.28, 8)
                            _add_canopy_blob(foliage, p_pt.x, p_pt.y, z + 0.66, 0.34, 0.34, 0.30)

                # Cast-iron curb bollards halfway between lamps
                if distance + 10.0 < length - 6.0:
                    pol_center = line.interpolate(distance + 10.0)
                    pol_pt = Point(pol_center.x - ty * side * 3.35, pol_center.y + tx * side * 3.35)
                    if sidewalk_safe.contains(pol_pt) and _far_enough(pol_pt.x, pol_pt.y, bollard_xy, 12.0) and _far_enough(pol_pt.x, pol_pt.y, lamp_xy, 3.0):
                        bollard_xy.append((pol_pt.x, pol_pt.y))
                        _add_cylinder(metal, pol_pt.x, pol_pt.y, z, z + 0.82, 0.075, 0.06, 7)
                        _add_cylinder(metal, pol_pt.x, pol_pt.y, z + 0.82, z + 0.90, 0.08, 0.02, 7)
            distance += 20.0
            index += 1
    return lamp_lights, len(lamp_xy), len(bench_xy), len(bollard_xy)


def add_stylized_trees(meshes, bounds, excluded_area, base_m):
    """Deterministically scatter stylized broad-leaf trees & bushes on open green ground."""
    foliage_buckets = ("FoliageLight", "FoliageMid", "FoliageDark")
    trunks = meshes["TreeTrunks"]
    # Keep clear margin from roads, sidewalks, buildings, and water
    forbidden = excluded_area.buffer(3.2)
    minx, miny, maxx, maxy = bounds.bounds
    step = 26.0
    placed = 0

    gx = minx + 12.0
    ix = 0
    while gx < maxx - 12.0:
        gy = miny + 12.0
        iy = 0
        while gy < maxy - 12.0:
            # Deterministic hash jitter per grid cell
            h = (ix * 73856093 ^ iy * 19349663) & 0xFFFFFFFF
            jx = ((h % 100) / 100.0 - 0.5) * 9.0
            jy = (((h // 100) % 100) / 100.0 - 0.5) * 9.0
            pt = Point(gx + jx, gy + jy)
            if bounds.contains(pt) and not forbidden.contains(pt):
                foliage = meshes[foliage_buckets[h % len(foliage_buckets)]]
                if h % 4 == 0:
                    # Lush stylized bush
                    r = 1.15 + (h % 5) * 0.16
                    _add_canopy_blob(foliage, pt.x, pt.y, base_m + r * 0.65, r, r * 0.92, r * 0.72)
                else:
                    # Stylized broad-leaf tree
                    trunk_h = 2.6 + (h % 7) * 0.28
                    canopy_r = 2.2 + (h % 5) * 0.35
                    _add_cylinder(trunks, pt.x, pt.y, base_m, base_m + trunk_h, 0.28, 0.18, 7)
                    _add_canopy_blob(foliage, pt.x, pt.y, base_m + trunk_h + canopy_r * 0.62, canopy_r, canopy_r * 0.95, canopy_r * 0.85)
                    # Secondary offset crown puff for organic silhouette
                    ang = (h % 360) * tau / 360.0
                    _add_canopy_blob(
                        foliage,
                        pt.x + cos(ang) * canopy_r * 0.45,
                        pt.y + sin(ang) * canopy_r * 0.45,
                        base_m + trunk_h + canopy_r * 0.42,
                        canopy_r * 0.72, canopy_r * 0.72, canopy_r * 0.62,
                    )
                placed += 1
            gy += step
            iy += 1
        gx += step
        ix += 1
    return placed
