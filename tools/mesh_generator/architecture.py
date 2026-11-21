"""Generate stylized European/North-German old-town building geometry from OSM footprints."""

from math import floor, hypot

from shapely.geometry import Polygon


WALL_STYLES = (
    "WallsCream",
    "WallsOchre",
    "WallsTerracotta",
    "WallsSage",
    "WallsSand",
    "WallsBrick",
)
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


def _add_pitched_roof(roof_mesh, gable_mesh, polygon, base_z, ridge_h, overhang=0.25):
    """Add a pitched hip/gable roof for simple footprints, or a clean flat cap for complex/courtyard ones."""
    if polygon.interiors or len(polygon.exterior.coords) > 10:
        # Courtyard or complex footprint: keep reliable triangulated roof with slight parapet rim
        roof_mesh.add_surface(polygon, base_z)
        return

    # Check if the footprint is well-approximated by its minimum rotated rectangle for a classic gable roof.
    mrr = polygon.minimum_rotated_rectangle
    if isinstance(mrr, Polygon) and mrr.area > 0 and (polygon.area / mrr.area) >= 0.86:
        coords = list(mrr.exterior.coords)[:4]
        # Ensure counter-clockwise orientation
        e0 = hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
        e1 = hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
        # Ridge runs parallel to the longer edge
        if e0 >= e1:
            p0, p1, p2, p3 = coords[0], coords[1], coords[2], coords[3]
            long_len, short_len = e0, e1
        else:
            p0, p1, p2, p3 = coords[1], coords[2], coords[3], coords[0]
            long_len, short_len = e1, e0

        if short_len < 1.5 or long_len < 1.5:
            roof_mesh.add_surface(polygon, base_z)
            return

        # Unit vectors along length (p0->p1) and width (p0->p3)
        lx, ly = (p1[0] - p0[0]) / long_len, (p1[1] - p0[1]) / long_len
        wx, wy = (p3[0] - p0[0]) / short_len, (p3[1] - p0[1]) / short_len

        # Expand eave corners slightly for overhang
        c0 = (p0[0] - lx * overhang - wx * overhang, p0[1] - ly * overhang - wy * overhang, base_z - 0.10)
        c1 = (p1[0] + lx * overhang - wx * overhang, p1[1] + ly * overhang - wy * overhang, base_z - 0.10)
        c2 = (p2[0] + lx * overhang + wx * overhang, p2[1] + ly * overhang + wy * overhang, base_z - 0.10)
        c3 = (p3[0] - lx * overhang + wx * overhang, p3[1] - ly * overhang + wy * overhang, base_z - 0.10)

        # Ridge endpoints (slightly inset for subtle hip or flush for gable)
        r0 = ((p0[0] + p3[0]) * 0.5 - lx * overhang, (p0[1] + p3[1]) * 0.5 - ly * overhang, base_z + ridge_h)
        r1 = ((p1[0] + p2[0]) * 0.5 + lx * overhang, (p1[1] + p2[1]) * 0.5 + ly * overhang, base_z + ridge_h)

        # Two roof slopes (CCW when viewed from outside -> correct Unreal winding)
        _add_quad(roof_mesh, c0, c1, r1, r0)
        _add_quad(roof_mesh, c2, c3, r0, r1)

        # Gable triangles (flush with walls, no overhang)
        g0 = (p0[0], p0[1], base_z)
        g1 = (p1[0], p1[1], base_z)
        g2 = (p2[0], p2[1], base_z)
        g3 = (p3[0], p3[1], base_z)
        gr0 = ((p0[0] + p3[0]) * 0.5, (p0[1] + p3[1]) * 0.5, base_z + ridge_h)
        gr1 = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5, base_z + ridge_h)
        _add_triangle(gable_mesh, g3, g0, gr0)
        _add_triangle(gable_mesh, g1, g2, gr1)

        # Also add flat ceiling cap inside eave so vertical roof collision rays always hit
        roof_mesh.add_surface(polygon, base_z)
        return

    # Fallback: hip/pyramid roof to representative point for irregular simple polygons
    center = polygon.representative_point()
    apex = (center.x, center.y, base_z + ridge_h * 0.85)
    ring = list(polygon.exterior.coords)
    for start, end in zip(ring, ring[1:]):
        if start != end:
            _add_triangle(roof_mesh, (start[0], start[1], base_z), (end[0], end[1], base_z), apex)
    roof_mesh.add_surface(polygon, base_z)


def add_stylized_building(meshes, polygon, height_m, base_m, osm_id, tags):
    """Build a stylized old-town building with stone plinth, windows, shutters, timber trim, and pitched roof."""
    is_minor = tags.get("building") in {"garage", "garages", "shed", "roof", "hut"} or height_m <= 3.2
    is_civic = tags.get("building") in {"church", "civic", "commercial"} or "name" in tags

    wall_name = WALL_STYLES[osm_id % len(WALL_STYLES)]
    roof_name = "RoofsSlate" if (is_civic and osm_id % 2 == 0) else ROOF_STYLES[osm_id % len(ROOF_STYLES)]
    shutter_name = SHUTTER_STYLES[(osm_id // 3) % len(SHUTTER_STYLES)]
    has_timber_framing = (not is_minor) and (osm_id % 3 != 0)

    wall_mesh = meshes[wall_name]
    roof_mesh = meshes[roof_name]
    stone_mesh = meshes["StoneTrim"]
    timber_mesh = meshes["TimberTrim"]
    glass_mesh = meshes["WindowGlass"]
    shutter_mesh = meshes[shutter_name]
    door_mesh = meshes["Doors"]
    flower_mesh = meshes["FlowerBoxes"]

    # Main wall volume (collidable)
    wall_mesh.add_walls(polygon, height_m, base_m)

    # Pitched roof (collidable)
    ridge_h = 0.75 if is_minor else min(3.4, max(1.8, height_m * 0.36))
    _add_pitched_roof(roof_mesh, wall_mesh, polygon, base_m + height_m, ridge_h)

    if is_minor:
        return

    plinth_h = min(0.85, height_m * 0.16)
    floors = max(1, min(4, int(round(height_m / 3.1))))
    floor_h = height_m / floors

    door_placed = False
    ring = list(polygon.exterior.coords)
    for start, end in zip(ring, ring[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = hypot(dx, dy)
        if length < 1.2:
            continue
        tx, ty = dx / length, dy / length
        # For CCW exterior ring in (east, north), outward normal is (ty, -tx)
        nx, ny = ty, -tx

        # Stone plinth along wall base
        _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, base_m, base_m + plinth_h, 0.0, 0.05)

        # Horizontal cornice / timber belt between floors and under eaves
        belt_mesh = timber_mesh if has_timber_framing else stone_mesh
        for level in range(1, floors + 1):
            z = base_m + level * floor_h
            _add_box_on_wall(belt_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, z - 0.14, z + 0.04, 0.0, 0.08)

        # Corner timber posts / quoins
        if has_timber_framing:
            _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, 0.16, base_m + plinth_h, base_m + height_m, 0.0, 0.06)
            _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, length - 0.16, length, base_m + plinth_h, base_m + height_m, 0.0, 0.06)

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
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_center - 0.65, u_center + 0.65, base_m, base_m + 2.30, 0.0, 0.07)
                    _add_box_on_wall(door_mesh, start[0], start[1], tx, ty, nx, ny, u_center - 0.52, u_center + 0.52, base_m, base_m + 2.18, 0.0, 0.09)
                    continue

                win_w = 1.05
                win_z0 = z_floor + max(plinth_h + 0.25, 0.95) if fl == 0 else z_floor + 0.85
                win_z1 = min(z_floor + floor_h - 0.35, win_z0 + 1.35)
                if win_z1 - win_z0 < 0.6:
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
