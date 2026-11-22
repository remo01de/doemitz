"""Generate stylized European/North-German old-town building geometry from OSM footprints."""

from math import atan2, cos, degrees, floor, hypot, radians, sin

from shapely import orient_polygons
from shapely.geometry import Polygon


WALL_STYLES = (
    "WallsCream",
    "WallsOchre",
    "WallsTerracotta",
    "WallsSage",
    "WallsSand",
    "WallsBrick",
)
GABLE_STYLES = tuple(style.replace("Walls", "Gable", 1) for style in WALL_STYLES)
ROOF_STYLES = ("RoofsTerracotta", "RoofsClay", "RoofsSlate")
SHUTTER_STYLES = ("ShuttersGreen", "ShuttersRed", "ShuttersBlue", "TimberTrim")


def _add_quad(mesh, p0, p1, p2, p3):
    offset = len(mesh.vertices)
    mesh.vertices.extend((p0, p1, p2, p3))
    mesh.triangles.extend(((offset, offset + 1, offset + 2), (offset, offset + 2, offset + 3)))


def _add_triangle(mesh, p0, p1, p2):
    offset = len(mesh.vertices)
    mesh.vertices.extend((p0, p1, p2))
    mesh.triangles.append((offset, offset + 1, offset + 2))


def _add_box_on_wall(mesh, ox, oy, tx, ty, nx, ny, u0, u1, z0, z1, d0, d1):
    """Add a 3D protruding box relative to a wall origin (ox, oy), tangent (tx, ty), outward normal (nx, ny)."""
    def pt(u, d, z):
        return (ox + tx * u + nx * d, oy + ty * u + ny * d, z)

    # Front face (facing outward along +n)
    f0 = pt(u0, d1, z0)
    f1 = pt(u1, d1, z0)
    f2 = pt(u1, d1, z1)
    f3 = pt(u0, d1, z1)
    _add_quad(mesh, f0, f1, f2, f3)

    # Full 3D sides only for deep protruding elements (e.g. flower boxes), keeping triangle count lean for Intel Iris Xe.
    if d1 - d0 > 0.12:
        b0 = pt(u0, d0, z0)
        b1 = pt(u1, d0, z0)
        b2 = pt(u1, d0, z1)
        b3 = pt(u0, d0, z1)
        _add_quad(mesh, b0, f0, f3, b3)  # left
        _add_quad(mesh, f1, b1, b2, f2)  # right
        _add_quad(mesh, f3, f2, b2, b3)  # top
        _add_quad(mesh, b0, b1, f1, f0)  # bottom


def _angle_diff_180(a_deg: float, b_deg: float) -> float:
    diff = abs((a_deg - b_deg) % 180.0)
    return min(diff, 180.0 - diff)


def _add_roof_with_shape(
    roof_mesh,
    gable_mesh,
    polygon,
    base_z: float,
    ridge_rise: float,
    roof_shape: str = "gabled",
    ridge_direction_deg: float | None = None,
    slope_direction_deg: float | None = None,
    overhang: float = 0.25,
    is_minor: bool = False,
):
    """Build roof geometry matching LoD2 roof shape (flat, gabled, hipped, half-hipped, mansard, skillion, pyramidal)."""
    shape_norm = (roof_shape or "gabled").strip().lower()

    # 1. Flat roof (LoD2 roofType 1000) or negligible ridge rise
    if shape_norm == "flat" or ridge_rise < 0.25:
        roof_mesh.add_surface(polygon, base_z)
        if not is_minor and not polygon.interiors:
            # Subtle 0.25 m parapet rim around flat roofs
            ring = list(polygon.exterior.coords)
            for start, end in zip(ring, ring[1:]):
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = hypot(dx, dy)
                if length < 0.5:
                    continue
                tx, ty = dx / length, dy / length
                nx, ny = ty, -tx
                _add_box_on_wall(
                    gable_mesh, start[0], start[1], tx, ty, nx, ny,
                    0.0, length, base_z, base_z + 0.28, 0.0, 0.06,
                )
        return

    # 2. Complex / courtyard footprints: reliable flat cap or simple hip
    if polygon.interiors or len(polygon.exterior.coords) > 12:
        roof_mesh.add_surface(polygon, base_z)
        return

    # 3. Pyramidal / conical / dome roofs
    if shape_norm in ("pyramidal", "conical", "dome"):
        center = polygon.representative_point()
        apex = (center.x, center.y, base_z + ridge_rise)
        ring = list(polygon.exterior.coords)
        for start, end in zip(ring, ring[1:]):
            if start != end:
                _add_triangle(roof_mesh, (start[0], start[1], base_z), (end[0], end[1], base_z), apex)
        roof_mesh.add_surface(polygon, base_z)
        return

    # 4. Rectangular-approximated footprints: gabled, hipped, half-hipped, mansard, skillion
    mrr = orient_polygons(polygon.minimum_rotated_rectangle)
    if isinstance(mrr, Polygon) and mrr.area > 0 and (polygon.area / mrr.area) >= 0.84:
        coords = list(mrr.exterior.coords)[:4]
        e0 = hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
        e1 = hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
        if min(e0, e1) < 1.5:
            roof_mesh.add_surface(polygon, base_z)
            return

        ang0 = degrees(atan2(coords[1][1] - coords[0][1], coords[1][0] - coords[0][0])) % 180.0
        ang1 = degrees(atan2(coords[2][1] - coords[1][1], coords[2][0] - coords[1][0])) % 180.0

        # Align ridge with LoD2 ridge_direction_deg when available, else parallel to longer edge
        if ridge_direction_deg is not None:
            use_edge0 = _angle_diff_180(ang0, ridge_direction_deg) <= _angle_diff_180(ang1, ridge_direction_deg)
        else:
            use_edge0 = e0 >= e1

        if use_edge0:
            p0, p1, p2, p3 = coords[0], coords[1], coords[2], coords[3]
            ridge_len, span_len = e0, e1
        else:
            p0, p1, p2, p3 = coords[1], coords[2], coords[3], coords[0]
            ridge_len, span_len = e1, e0

        lx, ly = (p1[0] - p0[0]) / ridge_len, (p1[1] - p0[1]) / ridge_len
        wx, wy = (p3[0] - p0[0]) / span_len, (p3[1] - p0[1]) / span_len
        # Guarantee right-handed CCW basis (l x w = +Z) regardless of input polygon orientation
        if lx * wy - ly * wx < 0.0:
            p0, p1, p2, p3 = p1, p0, p3, p2
            lx, ly = -lx, -ly
            wx, wy = (p3[0] - p0[0]) / span_len, (p3[1] - p0[1]) / span_len

        c0 = (p0[0] - lx * overhang - wx * overhang, p0[1] - ly * overhang - wy * overhang, base_z - 0.10)
        c1 = (p1[0] + lx * overhang - wx * overhang, p1[1] + ly * overhang - wy * overhang, base_z - 0.10)
        c2 = (p2[0] + lx * overhang + wx * overhang, p2[1] + ly * overhang + wy * overhang, base_z - 0.10)
        c3 = (p3[0] - lx * overhang + wx * overhang, p3[1] - ly * overhang + wy * overhang, base_z - 0.10)

        g0 = (p0[0], p0[1], base_z)
        g1 = (p1[0], p1[1], base_z)
        g2 = (p2[0], p2[1], base_z)
        g3 = (p3[0], p3[1], base_z)

        if shape_norm == "skillion":
            # Determine which side is low vs high using LoD2 slope_direction_deg
            flip = False
            if slope_direction_deg is not None:
                sx, sy = cos(radians(slope_direction_deg)), sin(radians(slope_direction_deg))
                # (wx, wy) points from (p0,p1) to (p3,p2); if downhill aligns with +w, (p0,p1) is high
                flip = (wx * sx + wy * sy) > 0.0
            if not flip:
                # Low at (p0, p1), high at (p3, p2)
                h2 = (c2[0], c2[1], base_z + ridge_rise)
                h3 = (c3[0], c3[1], base_z + ridge_rise)
                _add_quad(roof_mesh, c0, c1, h2, h3)
                gh2 = (p2[0], p2[1], base_z + ridge_rise)
                gh3 = (p3[0], p3[1], base_z + ridge_rise)
                _add_quad(gable_mesh, g2, g3, gh3, gh2)
                _add_triangle(gable_mesh, g1, g2, gh2)
                _add_triangle(gable_mesh, g3, g0, gh3)
            else:
                # High at (p0, p1), low at (p3, p2)
                h0 = (c0[0], c0[1], base_z + ridge_rise)
                h1 = (c1[0], c1[1], base_z + ridge_rise)
                _add_quad(roof_mesh, h0, h1, c2, c3)
                gh0 = (p0[0], p0[1], base_z + ridge_rise)
                gh1 = (p1[0], p1[1], base_z + ridge_rise)
                _add_quad(gable_mesh, g0, g1, gh1, gh0)
                _add_triangle(gable_mesh, g1, g2, gh1)
                _add_triangle(gable_mesh, g3, g0, gh0)
            roof_mesh.add_surface(polygon, base_z)
            return

        if shape_norm == "hipped":
            hip_inset = min(ridge_len * 0.35, span_len * 0.42)
            r0 = ((p0[0] + p3[0]) * 0.5 + lx * hip_inset, (p0[1] + p3[1]) * 0.5 + ly * hip_inset, base_z + ridge_rise)
            r1 = ((p1[0] + p2[0]) * 0.5 - lx * hip_inset, (p1[1] + p2[1]) * 0.5 - ly * hip_inset, base_z + ridge_rise)
            _add_quad(roof_mesh, c0, c1, r1, r0)
            _add_quad(roof_mesh, c2, c3, r0, r1)
            _add_triangle(roof_mesh, c3, c0, r0)
            _add_triangle(roof_mesh, c1, c2, r1)
            roof_mesh.add_surface(polygon, base_z)
            return

        if shape_norm == "half-hipped":
            # Gable up to 52% of ridge rise, then hipped bevel
            hip_inset = min(ridge_len * 0.20, span_len * 0.25)
            break_z = base_z + ridge_rise * 0.52
            r0 = ((p0[0] + p3[0]) * 0.5 + lx * hip_inset, (p0[1] + p3[1]) * 0.5 + ly * hip_inset, base_z + ridge_rise)
            r1 = ((p1[0] + p2[0]) * 0.5 - lx * hip_inset, (p1[1] + p2[1]) * 0.5 - ly * hip_inset, base_z + ridge_rise)
            # Mid-gable corners at break_z
            m_a0 = (p0[0] + wx * span_len * 0.26, p0[1] + wy * span_len * 0.26, break_z)
            m_a1 = (p3[0] - wx * span_len * 0.26, p3[1] - wy * span_len * 0.26, break_z)
            m_b0 = (p1[0] + wx * span_len * 0.26, p1[1] + wy * span_len * 0.26, break_z)
            m_b1 = (p2[0] - wx * span_len * 0.26, p2[1] - wy * span_len * 0.26, break_z)
            _add_quad(roof_mesh, c0, c1, r1, r0)
            _add_quad(roof_mesh, c2, c3, r0, r1)
            _add_triangle(roof_mesh, m_a1, m_a0, r0)
            _add_triangle(roof_mesh, m_b0, m_b1, r1)
            _add_quad(gable_mesh, g3, g0, m_a0, m_a1)
            _add_quad(gable_mesh, g1, g2, m_b1, m_b0)
            roof_mesh.add_surface(polygon, base_z)
            return

        if shape_norm == "mansard":
            # Two-pitch mansard hipped roof (steep lower curb + gentler upper hip)
            mid_z = base_z + ridge_rise * 0.62
            in_l = min(ridge_len * 0.14, span_len * 0.16)
            in_w = span_len * 0.18
            m0 = (p0[0] + lx * in_l + wx * in_w, p0[1] + ly * in_l + wy * in_w, mid_z)
            m1 = (p1[0] - lx * in_l + wx * in_w, p1[1] - ly * in_l + wy * in_w, mid_z)
            m2 = (p2[0] - lx * in_l - wx * in_w, p2[1] - ly * in_l - wy * in_w, mid_z)
            m3 = (p3[0] + lx * in_l - wx * in_w, p3[1] + ly * in_l - wy * in_w, mid_z)
            r_in = min(ridge_len * 0.30, span_len * 0.36)
            r0 = ((p0[0] + p3[0]) * 0.5 + lx * r_in, (p0[1] + p3[1]) * 0.5 + ly * r_in, base_z + ridge_rise)
            r1 = ((p1[0] + p2[0]) * 0.5 - lx * r_in, (p1[1] + p2[1]) * 0.5 - ly * r_in, base_z + ridge_rise)
            # Lower steep skirt (4 quads)
            _add_quad(roof_mesh, c0, c1, m1, m0)
            _add_quad(roof_mesh, c1, c2, m2, m1)
            _add_quad(roof_mesh, c2, c3, m3, m2)
            _add_quad(roof_mesh, c3, c0, m0, m3)
            # Upper hipped crown
            _add_quad(roof_mesh, m0, m1, r1, r0)
            _add_quad(roof_mesh, m2, m3, r0, r1)
            _add_triangle(roof_mesh, m3, m0, r0)
            _add_triangle(roof_mesh, m1, m2, r1)
            roof_mesh.add_surface(polygon, base_z)
            return

        # Default: classic gabled roof (LoD2 roofType 3100)
        r0 = ((p0[0] + p3[0]) * 0.5 - lx * overhang, (p0[1] + p3[1]) * 0.5 - ly * overhang, base_z + ridge_rise)
        r1 = ((p1[0] + p2[0]) * 0.5 + lx * overhang, (p1[1] + p2[1]) * 0.5 + ly * overhang, base_z + ridge_rise)
        _add_quad(roof_mesh, c0, c1, r1, r0)
        _add_quad(roof_mesh, c2, c3, r0, r1)
        gr0 = ((p0[0] + p3[0]) * 0.5, (p0[1] + p3[1]) * 0.5, base_z + ridge_rise)
        gr1 = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5, base_z + ridge_rise)
        _add_triangle(gable_mesh, g3, g0, gr0)
        _add_triangle(gable_mesh, g1, g2, gr1)
        roof_mesh.add_surface(polygon, base_z)
        return

    # Fallback: hip/pyramid roof to representative point for irregular simple polygons
    center = polygon.representative_point()
    apex = (center.x, center.y, base_z + ridge_rise * 0.85)
    ring = list(polygon.exterior.coords)
    for start, end in zip(ring, ring[1:]):
        if start != end:
            _add_triangle(roof_mesh, (start[0], start[1], base_z), (end[0], end[1], base_z), apex)
    roof_mesh.add_surface(polygon, base_z)


def add_stylized_building(
    meshes,
    polygon,
    height_m,
    base_m,
    osm_id,
    tags,
    max_ground_m=None,
    ridge_height_m=None,
    roof_shape=None,
    ridge_direction_deg=None,
    slope_direction_deg=None,
    style_override=None,
):
    """Build a stylized old-town building with stone plinth, windows, shutters, timber trim, and LoD2-informed roof."""
    is_minor = tags.get("building") in {"garage", "garages", "shed", "roof", "hut"} or height_m <= 3.3
    is_civic = tags.get("building") in {"church", "civic", "commercial"} or "name" in tags

    override = style_override or {}
    wall_name = override.get("wall_style") or WALL_STYLES[osm_id % len(WALL_STYLES)]
    roof_name = override.get("roof_style") or (
        "RoofsSlate" if (is_civic and osm_id % 2 == 0) else ROOF_STYLES[osm_id % len(ROOF_STYLES)]
    )
    shutter_name = override.get("shutter_style") or SHUTTER_STYLES[(osm_id // 3) % len(SHUTTER_STYLES)]
    has_timber_framing = override.get("timber_framing", (not is_minor) and (osm_id % 3 != 0))

    wall_mesh = meshes[wall_name]
    gable_name = wall_name.replace("Walls", "Gable", 1)
    gable_mesh = meshes.get(gable_name, wall_mesh)
    roof_mesh = meshes[roof_name]
    stone_mesh = meshes["StoneTrim"]
    timber_mesh = meshes["TimberTrim"]
    glass_mesh = meshes["WindowGlass"]
    shutter_mesh = meshes[shutter_name]
    door_mesh = meshes["Doors"]
    flower_mesh = meshes["FlowerBoxes"]

    ground_top_m = base_m if max_ground_m is None else max(base_m, float(max_ground_m))
    slope_span_m = ground_top_m - base_m
    # Sprint 13: buildings with a walk-in interior get real door/window openings (see interiors.py).
    interior = override.get("interior")
    if interior is not None:
        from tools.mesh_generator.interiors import add_walls_with_openings, add_window_frame_and_glass

    # Main wall volume (collidable); foundation starts at lowest terrain under footprint, eave counts from base_m.
    if interior is None:
        wall_mesh.add_walls(polygon, height_m, base_m)

    # Roof geometry (collidable): use LoD2 ridge_height & roof_shape when provided
    resolved_shape = roof_shape or ("flat" if is_minor and height_m <= 2.9 else "gabled")
    if ridge_height_m is not None:
        ridge_rise = max(0.0, float(ridge_height_m) - float(height_m))
    else:
        ridge_rise = 0.0 if resolved_shape == "flat" else (0.75 if is_minor else min(3.4, max(1.8, height_m * 0.36)))
    _add_roof_with_shape(
        roof_mesh,
        gable_mesh,
        polygon,
        base_m + height_m,
        ridge_rise,
        roof_shape=resolved_shape,
        ridge_direction_deg=ridge_direction_deg,
        slope_direction_deg=slope_direction_deg,
        is_minor=is_minor,
    )

    if is_minor:
        if slope_span_m > 0.10:
            minor_plinth_top = min(base_m + height_m - 0.15, ground_top_m + 0.25)
            ring = list(polygon.exterior.coords)
            for start, end in zip(ring, ring[1:]):
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = hypot(dx, dy)
                if length < 0.5:
                    continue
                tx, ty = dx / length, dy / length
                nx, ny = ty, -tx
                _add_box_on_wall(
                    stone_mesh, start[0], start[1], tx, ty, nx, ny,
                    0.0, length, base_m, minor_plinth_top, 0.0, 0.05,
                )
        return

    base_plinth_h = min(0.85, height_m * 0.16)
    # On sloped terrain, extend the natural stone plinth visibly past the highest terrain point under the footprint.
    plinth_top_m = (
        min(base_m + height_m - 0.35, max(base_m + base_plinth_h, ground_top_m + 0.35))
        if slope_span_m > 0.05
        else base_m + base_plinth_h
    )
    plinth_h = max(base_plinth_h, plinth_top_m - base_m)
    floors = max(1, min(4, int(round(height_m / 3.1))))
    floor_h = height_m / floors
    door_z0 = min(ground_top_m, base_m + max(0.0, height_m - 2.45)) if slope_span_m > 0.25 else base_m

    door_placed = interior is not None
    if interior is not None:
        interior.ceiling_z = base_m + floor_h - 0.16
        interior.add_door_frame(stone_mesh)
    ring = list(polygon.exterior.coords)
    for edge_idx, (start, end) in enumerate(zip(ring, ring[1:])):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = hypot(dx, dy)
        if length < 1.2:
            continue
        tx, ty = dx / length, dy / length
        # For CCW exterior ring in (east, north), outward normal is (ty, -tx)
        nx, ny = ty, -tx

        # Stone plinth along wall base (extends up past highest slope terrain), interrupted by an interior door
        door_rng = interior.door_range(edge_idx, 0.14) if interior is not None else None
        if door_rng is None:
            _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, base_m, plinth_top_m, 0.0, 0.05)
        else:
            _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, max(0.0, door_rng[0]), base_m, plinth_top_m, 0.0, 0.05)
            _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, min(length, door_rng[1]), length, base_m, plinth_top_m, 0.0, 0.05)

        # Horizontal cornice / timber belt between floors and under eaves
        belt_mesh = timber_mesh if has_timber_framing else stone_mesh
        for level in range(1, floors + 1):
            z = base_m + level * floor_h
            _add_box_on_wall(belt_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, z - 0.14, z + 0.04, 0.0, 0.08)

        # Corner timber posts / quoins
        if has_timber_framing and plinth_top_m < base_m + height_m - 0.2:
            _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, 0.16, plinth_top_m, base_m + height_m, 0.0, 0.06)
            _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, length - 0.16, length, plinth_top_m, base_m + height_m, 0.0, 0.06)

        if length < 3.0:
            continue

        # Windows & ground-floor door
        bays = max(1, min(8, floor((length - 0.8) / 2.6)))
        spacing = length / bays
        for fl in range(floors):
            z_floor = base_m + fl * floor_h
            for bay in range(bays):
                u_center = (bay + 0.5) * spacing
                if fl == 0 and not door_placed and bay == bays // 2 and length >= 4.0:
                    door_placed = True
                    # Wooden entrance door with stone/timber frame
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_center - 0.65, u_center + 0.65, base_m, door_z0 + 2.30, 0.0, 0.07)
                    _add_box_on_wall(door_mesh, start[0], start[1], tx, ty, nx, ny, u_center - 0.52, u_center + 0.52, door_z0, door_z0 + 2.18, 0.0, 0.09)
                    continue

                win_w = 1.05
                win_z0 = z_floor + max(plinth_h + 0.25, 0.95) if fl == 0 else max(plinth_top_m + 0.20, z_floor + 0.85)
                win_z1 = min(z_floor + floor_h - 0.35, win_z0 + 1.35)
                if win_z1 - win_z0 < 0.6:
                    continue

                if interior is not None and fl == 0:
                    if interior.overlaps_door(edge_idx, u_center - win_w * 0.6, u_center + win_w * 0.6):
                        continue
                    if interior.add_window(edge_idx, u_center - win_w * 0.48, u_center + win_w * 0.48, win_z0, win_z1):
                        op = interior.openings[-1]
                        add_window_frame_and_glass(
                            timber_mesh, meshes["WindowGlassClear"], start[0], start[1], tx, ty, nx, ny,
                            op.u0, op.u1, op.z0, op.z1, wall_thickness_m=interior.wall_thickness_m,
                        )
                        if spacing >= 2.2:
                            shutter_w = 0.38
                            _add_box_on_wall(shutter_mesh, start[0], start[1], tx, ty, nx, ny, op.u0 - 0.1 - shutter_w, op.u0 - 0.1, op.z0, op.z1, 0.0, 0.08)
                            _add_box_on_wall(shutter_mesh, start[0], start[1], tx, ty, nx, ny, op.u1 + 0.1, op.u1 + 0.1 + shutter_w, op.z0, op.z1, 0.0, 0.08)
                        continue

                # Window frame + glass
                _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_center - win_w * 0.58, u_center + win_w * 0.58, win_z0 - 0.08, win_z1 + 0.08, 0.0, 0.06)
                _add_box_on_wall(glass_mesh, start[0], start[1], tx, ty, nx, ny, u_center - win_w * 0.48, u_center + win_w * 0.48, win_z0, win_z1, 0.0, 0.075)

                # Stylized shutters on both sides
                if spacing >= 2.2:
                    shutter_w = 0.38
                    _add_box_on_wall(shutter_mesh, start[0], start[1], tx, ty, nx, ny, u_center - win_w * 0.58 - shutter_w, u_center - win_w * 0.58, win_z0, win_z1, 0.0, 0.08)
                    _add_box_on_wall(shutter_mesh, start[0], start[1], tx, ty, nx, ny, u_center + win_w * 0.58, u_center + win_w * 0.58 + shutter_w, win_z0, win_z1, 0.0, 0.08)

                # Occasional flower box under upper-floor windows
                if fl >= 1 and (osm_id + bay) % 2 == 0:
                    _add_box_on_wall(flower_mesh, start[0], start[1], tx, ty, nx, ny, u_center - 0.48, u_center + 0.48, win_z0 - 0.22, win_z0 - 0.02, 0.0, 0.22)

            # Vertical half-timbering mullions between bays on upper floors
            if has_timber_framing and fl >= 1:
                for bay in range(1, bays):
                    u_post = bay * spacing
                    _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_post - 0.07, u_post + 0.07, z_floor, z_floor + floor_h, 0.0, 0.05)

    if interior is not None:
        add_walls_with_openings(wall_mesh, polygon, height_m, base_m, interior.openings_by_edge())
