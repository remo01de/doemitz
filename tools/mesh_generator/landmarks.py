"""Stylized architectural landmark generators selected by OSM ID from doemitz-altstadt-landmarks.json."""

from __future__ import annotations

from math import cos, floor, hypot, pi, sin

from shapely.geometry import Polygon

from tools.mesh_generator.architecture import _add_box_on_wall, _add_quad, _add_roof_with_shape, _add_triangle


def _add_prism(mesh, center_xy: tuple[float, float], ax: tuple[float, float], ay: tuple[float, float],
               hx: float, hy: float, z0: float, z1: float, add_top: bool = True) -> None:
    """Add an oriented rectangular prism (CCW outward faces in (east, north, z))."""
    cx, cy = center_xy
    fx, fy = ax
    rx, ry = ay

    def pt(u: float, v: float, z: float) -> tuple[float, float, float]:
        return (round(cx + fx * u + rx * v, 4), round(cy + fy * u + ry * v, 4), round(z, 4))

    # CCW order in (east, north): (-hx,-hy) -> (-hx,+hy)? Check cross((+f), (+r))!
    # We pass rx, ry = right normal = (fy, -fx), so f x r = (fx)(-fx) - (fy)(fy) = -1 (CW).
    # Therefore CCW around prism is: p0=(-hx,+hy), p1=(+hx,+hy), p2=(+hx,-hy), p3=(-hx,-hy) -> wait:
    # e1 = p1-p0 = +2*hx*f, e2 = p2-p1 = -2*hy*r; cross(+f, -r) = +1 (CCW)!
    b0 = pt(-hx, hy, z0)
    b1 = pt(hx, hy, z0)
    b2 = pt(hx, -hy, z0)
    b3 = pt(-hx, -hy, z0)
    t0 = pt(-hx, hy, z1)
    t1 = pt(hx, hy, z1)
    t2 = pt(hx, -hy, z1)
    t3 = pt(-hx, -hy, z1)

    _add_quad(mesh, b0, b1, t1, t0)
    _add_quad(mesh, b1, b2, t2, t1)
    _add_quad(mesh, b2, b3, t3, t2)
    _add_quad(mesh, b3, b0, t0, t3)
    if add_top:
        _add_quad(mesh, t0, t1, t2, t3)


def _add_octagonal_spire(mesh, center_xy: tuple[float, float], radius_m: float, z0: float, z_tip: float, sides: int = 8) -> None:
    """Add an n-sided steep spire/pyramid with CCW outward winding."""
    cx, cy = center_xy
    apex = (round(cx, 4), round(cy, 4), round(z_tip, 4))
    ring = [
        (
            round(cx + radius_m * cos(2.0 * pi * i / sides + pi / sides), 4),
            round(cy + radius_m * sin(2.0 * pi * i / sides + pi / sides), 4),
            round(z0, 4),
        )
        for i in range(sides)
    ]
    for i in range(sides):
        _add_triangle(mesh, ring[i], ring[(i + 1) % sides], apex)


def _add_plinth_and_cornice(stone_mesh, polygon: Polygon, base_m: float, plinth_top_m: float, eave_z: float,
                            cornice_h: float = 0.22, cornice_d: float = 0.14) -> None:
    ring = list(polygon.exterior.coords)
    for start, end in zip(ring, ring[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if length < 0.6:
            continue
        tx, ty = dx / length, dy / length
        nx, ny = ty, -tx
        _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, base_m, plinth_top_m, 0.0, 0.06)
        _add_box_on_wall(
            stone_mesh, start[0], start[1], tx, ty, nx, ny,
            0.0, length, eave_z - cornice_h, eave_z + 0.04, 0.0, cornice_d,
        )


def _build_johanneskirche(meshes, polygon: Polygon, base_m: float, max_ground_m: float,
                          ridge_height_m: float, cfg: dict) -> float:
    """Neo-Gothic red-brick Johanneskirche (1869–1872): tall NW tower with 4 corner pinnacles & spire, brick nave & choir."""
    wall_style = cfg.get("wall_style", "WallsBrick")
    wall_mesh = meshes[wall_style]
    gable_mesh = meshes.get(wall_style.replace("Walls", "Gable", 1), wall_mesh)
    roof_mesh = meshes[cfg.get("roof_style", "RoofsSlate")]
    stone_mesh = meshes["StoneTrim"]
    glass_mesh = meshes["WindowGlass"]
    door_mesh = meshes["Doors"]
    timber_mesh = meshes["TimberTrim"]

    nave_eave_h = float(cfg.get("nave_eave_height_m", 11.25))
    nave_ridge_h = float(cfg.get("nave_ridge_height_m", 18.08))
    choir_ridge_h = float(cfg.get("choir_ridge_height_m", 15.27))
    tower_shaft_h = float(cfg.get("tower_shaft_height_m", 25.82))
    tower_pinnacle_h = float(cfg.get("tower_pinnacle_height_m", 29.4))
    spire_top_h = max(float(ridge_height_m), tower_shaft_h + 10.0)
    tower_w = float(cfg.get("tower_width_m", 7.0))

    # Orientation axis from NW tower toward SE nave/choir centroid
    tc = cfg.get("tower_center_local_m")
    centroid = polygon.centroid
    tx0, ty0 = (float(tc[0]), float(tc[1])) if tc else (centroid.x - 12.0, centroid.y + 6.0)
    dx, dy = centroid.x - tx0, centroid.y - ty0
    dist_c = max(hypot(dx, dy), 1.0)
    fx, fy = dx / dist_c, dy / dist_c
    rx, ry = fy, -fx  # right-hand normal

    # 1. Main church footprint walls up to nave eave (collidable) + ceiling collision cap
    wall_mesh.add_walls(polygon, nave_eave_h, base_m)
    roof_mesh.add_surface(polygon, base_m + nave_eave_h)

    ground_top = max(base_m, max_ground_m)
    plinth_top = max(base_m + 1.1, ground_top + 0.45)
    _add_plinth_and_cornice(stone_mesh, polygon, base_m, plinth_top, base_m + nave_eave_h, cornice_h=0.28, cornice_d=0.18)

    # 2. Steep Neo-Gothic nave & choir roofs aligned with the church axis
    nave_eave_z = base_m + nave_eave_h
    nave_ridge_z = base_m + nave_ridge_h
    choir_ridge_z = base_m + choir_ridge_h

    def ax_pt(s: float, lat: float, z: float) -> tuple[float, float, float]:
        return (round(tx0 + fx * s + rx * lat, 4), round(ty0 + fy * s + ry * lat, 4), round(z, 4))

    # Main nave pitched roof (s = 3.2 m behind tower to s = 26.8 m)
    s_n0, s_n1 = 3.2, 26.8
    nw_half = 7.4
    c0 = ax_pt(s_n0, nw_half, nave_eave_z - 0.15)
    c1 = ax_pt(s_n1, nw_half, nave_eave_z - 0.15)
    c2 = ax_pt(s_n1, -nw_half, nave_eave_z - 0.15)
    c3 = ax_pt(s_n0, -nw_half, nave_eave_z - 0.15)
    r0 = ax_pt(s_n0 + 0.4, 0.0, nave_ridge_z)
    r1 = ax_pt(s_n1 - 0.8, 0.0, nave_ridge_z)
    _add_quad(roof_mesh, c0, c1, r1, r0)
    _add_quad(roof_mesh, c2, c3, r0, r1)
    # East nave gable wall + west gable meeting tower
    _add_triangle(gable_mesh, ax_pt(s_n1, nw_half - 0.2, nave_eave_z), ax_pt(s_n1, -nw_half + 0.2, nave_eave_z), r1)
    _add_triangle(gable_mesh, ax_pt(s_n0, -nw_half + 0.2, nave_eave_z), ax_pt(s_n0, nw_half - 0.2, nave_eave_z), r0)

    # Cross-transept roof accent (signature cross-hipped silhouette of Johanneskirche)
    s_tr = 15.0
    tr_half_len = 5.4
    tr_half_w = 8.4
    tr_ridge_z = nave_ridge_z - 0.35
    tc_l = ax_pt(s_tr, -tr_half_w, nave_eave_z - 0.15)
    tc_r = ax_pt(s_tr, tr_half_w, nave_eave_z - 0.15)
    tr_a = ax_pt(s_tr - tr_half_len, 0.0, nave_ridge_z)
    tr_b = ax_pt(s_tr + tr_half_len, 0.0, nave_ridge_z)
    tr_l0 = ax_pt(s_tr - tr_half_len, -tr_half_w, nave_eave_z - 0.15)
    tr_l1 = ax_pt(s_tr + tr_half_len, -tr_half_w, nave_eave_z - 0.15)
    tr_r0 = ax_pt(s_tr - tr_half_len, tr_half_w, nave_eave_z - 0.15)
    tr_r1 = ax_pt(s_tr + tr_half_len, tr_half_w, nave_eave_z - 0.15)
    tr_rl = ax_pt(s_tr, -tr_half_w + 0.5, tr_ridge_z)
    tr_rr = ax_pt(s_tr, tr_half_w - 0.5, tr_ridge_z)
    _add_triangle(roof_mesh, tr_l0, tr_l1, tr_rl)
    _add_triangle(roof_mesh, tr_r1, tr_r0, tr_rr)
    _add_quad(roof_mesh, tr_l1, ax_pt(s_tr + tr_half_len, 0.0, nave_eave_z), tr_b, tr_rl)
    _add_quad(roof_mesh, ax_pt(s_tr - tr_half_len, 0.0, nave_eave_z), tr_l0, tr_rl, tr_a)
    _add_quad(roof_mesh, ax_pt(s_tr + tr_half_len, 0.0, nave_eave_z), tr_r1, tr_rr, tr_b)
    _add_quad(roof_mesh, tr_r0, ax_pt(s_tr - tr_half_len, 0.0, nave_eave_z), tr_a, tr_rr)

    # Polygonal East Choir / Apse roof (s = 26.8..34.2 m)
    s_ch0, s_ch1 = 26.5, 34.4
    ch_w = 5.0
    ch_apex = ax_pt(s_ch0 + 1.5, 0.0, choir_ridge_z)
    ch_ring = [
        ax_pt(s_ch0, ch_w, nave_eave_z - 0.1),
        ax_pt(s_ch1 - 2.0, ch_w * 0.72, nave_eave_z - 0.1),
        ax_pt(s_ch1, 0.0, nave_eave_z - 0.1),
        ax_pt(s_ch1 - 2.0, -ch_w * 0.72, nave_eave_z - 0.1),
        ax_pt(s_ch0, -ch_w, nave_eave_z - 0.1),
    ]
    for a, b in zip(ch_ring, ch_ring[1:]):
        _add_triangle(roof_mesh, a, b, ch_apex)

    # 3. Tall Neo-Gothic lancet windows & buttresses along both long nave flanks
    for side in (-1.0, 1.0):
        n_ox, n_oy = side * rx, side * ry
        # Wall tangent pointing CCW around nave
        wt_x, wt_y = (fx, fy) if side > 0 else (-fx, -fy)
        base_s = s_n0 if side > 0 else s_n1
        origin_x = tx0 + fx * base_s + rx * (side * 6.85)
        origin_y = ty0 + fy * base_s + ry * (side * 6.85)
        flank_len = s_n1 - s_n0
        bays = 5
        step = flank_len / bays
        for i in range(bays + 1):
            u_butt = i * step
            # Brick buttress (Strebepfeiler) with stone cap
            _add_box_on_wall(wall_mesh, origin_x, origin_y, wt_x, wt_y, n_ox, n_oy, u_butt - 0.35, u_butt + 0.35, base_m, nave_eave_z - 0.8, 0.0, 0.55)
            _add_box_on_wall(stone_mesh, origin_x, origin_y, wt_x, wt_y, n_ox, n_oy, u_butt - 0.38, u_butt + 0.38, nave_eave_z - 0.8, nave_eave_z - 0.45, 0.0, 0.60)
        for i in range(bays):
            u_c = (i + 0.5) * step
            # Tall pointed-arch lancet window (StoneTrim surround + WindowGlass + vertical mullion)
            wz0, wz1 = base_m + 3.0, nave_eave_z - 1.6
            _add_box_on_wall(stone_mesh, origin_x, origin_y, wt_x, wt_y, n_ox, n_oy, u_c - 0.95, u_c + 0.95, wz0 - 0.15, wz1 + 0.35, 0.0, 0.14)
            _add_box_on_wall(glass_mesh, origin_x, origin_y, wt_x, wt_y, n_ox, n_oy, u_c - 0.72, u_c + 0.72, wz0, wz1, 0.0, 0.18)
            _add_box_on_wall(stone_mesh, origin_x, origin_y, wt_x, wt_y, n_ox, n_oy, u_c - 0.08, u_c + 0.08, wz0, wz1 + 0.2, 0.0, 0.20)

    # 4. Iconic Neo-Gothic West/NW Bell Tower (Kirchturm) up to exact LoD2 height (39.22 m!)
    tw_half = tower_w * 0.5
    shaft_top_z = base_m + tower_shaft_h
    _add_prism(wall_mesh, (tx0, ty0), (fx, fy), (rx, ry), tw_half, tw_half, base_m, shaft_top_z, add_top=True)

    # Horizontal stone belt courses around tower
    for belt_h in (1.4, 11.5, 18.2, tower_shaft_h - 0.5):
        _add_prism(
            stone_mesh, (tx0, ty0), (fx, fy), (rx, ry),
            tw_half + 0.18, tw_half + 0.18, base_m + belt_h - 0.16, base_m + belt_h + 0.18, add_top=True,
        )

    # Belfry louvers, tower clock faces, and NW portal on the 4 tower faces
    # For outward front face normal fn = (fnx, fny), wall tangent must satisfy ft = (-fny, fnx) so ft x Z = +fn.
    face_specs = [
        ((-fx, -fy), (fy, -fx), True),     # NW main entrance face
        ((fx, fy), (-fy, fx), False),      # SE face (above nave)
        ((rx, ry), (-ry, rx), False),      # SW face
        ((-rx, -ry), (ry, -rx), False),    # NE face
    ]
    for (fnx, fny), (ftx, fty), is_front in face_specs:
        fcx = tx0 + fnx * tw_half
        fcy = ty0 + fny * tw_half
        # Paired belfry louver openings (z = 19.2 .. 24.0 m)
        for offset_u in (-1.25, 1.25):
            _add_box_on_wall(stone_mesh, fcx, fcy, ftx, fty, fnx, fny, offset_u - 0.72, offset_u + 0.72, base_m + 19.0, base_m + 24.2, 0.0, 0.14)
            _add_box_on_wall(door_mesh, fcx, fcy, ftx, fty, fnx, fny, offset_u - 0.52, offset_u + 0.52, base_m + 19.2, base_m + 23.9, 0.0, 0.18)
        # Tower clock face (1873) at z = 15.6 .. 17.6 m
        _add_box_on_wall(stone_mesh, fcx, fcy, ftx, fty, fnx, fny, -1.05, 1.05, base_m + 15.4, base_m + 17.5, 0.0, 0.14)
        _add_box_on_wall(timber_mesh, fcx, fcy, ftx, fty, fnx, fny, -0.82, 0.82, base_m + 15.6, base_m + 17.3, 0.0, 0.18)
        if is_front:
            # Grand NW church entrance portal + tall rose/lancet window above
            _add_box_on_wall(stone_mesh, fcx, fcy, ftx, fty, fnx, fny, -1.65, 1.65, base_m, base_m + 4.4, 0.0, 0.30)
            _add_box_on_wall(door_mesh, fcx, fcy, ftx, fty, fnx, fny, -1.15, 1.15, base_m, base_m + 3.6, 0.0, 0.36)
            _add_box_on_wall(stone_mesh, fcx, fcy, ftx, fty, fnx, fny, -1.15, 1.15, base_m + 6.2, base_m + 10.6, 0.0, 0.16)
            _add_box_on_wall(glass_mesh, fcx, fcy, ftx, fty, fnx, fny, -0.88, 0.88, base_m + 6.4, base_m + 10.3, 0.0, 0.20)

    # 4 corner pinnacles (Fialtürmchen) flanking the spire
    pin_offset = tw_half - 0.55
    for su in (-1.0, 1.0):
        for sv in (-1.0, 1.0):
            pcx = tx0 + fx * (su * pin_offset) + rx * (sv * pin_offset)
            pcy = ty0 + fy * (su * pin_offset) + ry * (sv * pin_offset)
            _add_prism(gable_mesh, (pcx, pcy), (fx, fy), (rx, ry), 0.72, 0.72, shaft_top_z - 0.5, base_m + tower_pinnacle_h - 1.6, add_top=True)
            _add_octagonal_spire(roof_mesh, (pcx, pcy), 0.86, base_m + tower_pinnacle_h - 1.65, base_m + tower_pinnacle_h + 1.1, sides=4)

    # Steep octagonal main spire reaching exact LoD2 peak (39.22 m above base -> 57.38 m NHN!)
    _add_octagonal_spire(roof_mesh, (tx0, ty0), tw_half * 0.96, shaft_top_z - 0.15, base_m + spire_top_h, sides=8)
    return spire_top_h


def _build_rathaus(meshes, polygon: Polygon, base_m: float, max_ground_m: float,
                   eave_height_m: float, ridge_height_m: float, ridge_direction_deg: float | None, cfg: dict) -> float:
    """Baroque two-story half-timbered Rathaus (1819/1820) with red mansard hipped roof, Rathausturm & real front portal."""
    wall_style = cfg.get("wall_style", "WallsCream")
    wall_mesh = meshes[wall_style]
    gable_mesh = meshes.get(wall_style.replace("Walls", "Gable", 1), wall_mesh)
    roof_mesh = meshes[cfg.get("roof_style", "RoofsTerracotta")]
    stone_mesh = meshes["StoneTrim"]
    timber_mesh = meshes["TimberTrim"]
    glass_mesh = meshes["WindowGlass"]
    door_mesh = meshes["Doors"]

    # Fit mansard roof cleanly to the main rectangular block of Rathaus (excluding the small SW Rathausturm bump)
    ring = list(polygon.exterior.coords)
    ent_xy = cfg.get("real_entrance_local_m", [-66.82, -216.75])
    best_edge_idx = 0
    best_edge_dist = 1e9
    for idx, (start, end) in enumerate(zip(ring, ring[1:])):
        mx, my = 0.5 * (start[0] + end[0]), 0.5 * (start[1] + end[1])
        d = hypot(mx - ent_xy[0], my - ent_xy[1])
        if hypot(end[0] - start[0], end[1] - start[1]) >= 6.0 and d < best_edge_dist:
            best_edge_dist = d
            best_edge_idx = idx

    f_start, f_end = ring[best_edge_idx], ring[best_edge_idx + 1]
    f_len = max(hypot(f_end[0] - f_start[0], f_end[1] - f_start[1]), 1.0)
    ftx, fty = (f_end[0] - f_start[0]) / f_len, (f_end[1] - f_start[1]) / f_len
    # Inward direction into Rathaus main block (perpendicular left of CCW front edge)
    inx, iny = -fty, ftx
    main_depth = 10.6
    main_rect = Polygon([
        f_start,
        f_end,
        (f_end[0] + inx * main_depth, f_end[1] + iny * main_depth),
        (f_start[0] + inx * main_depth, f_start[1] + iny * main_depth),
    ])

    wall_mesh.add_walls(polygon, eave_height_m, base_m)
    ridge_rise = max(2.6, ridge_height_m - eave_height_m)
    _add_roof_with_shape(
        roof_mesh, gable_mesh, main_rect, base_m + eave_height_m, ridge_rise,
        roof_shape=cfg.get("roof_shape_override", "mansard"),
        ridge_direction_deg=ridge_direction_deg,
        overhang=0.25,
    )
    roof_mesh.add_surface(polygon, base_m + eave_height_m)

    ground_top = max(base_m, max_ground_m)
    plinth_top = max(base_m + 0.95, ground_top + 0.35)
    _add_plinth_and_cornice(stone_mesh, polygon, base_m, plinth_top, base_m + eave_height_m, cornice_h=0.22, cornice_d=0.14)

    floors = 2
    usable_h = eave_height_m - (plinth_top - base_m)
    floor_h = usable_h / floors

    for idx, (start, end) in enumerate(zip(ring, ring[1:])):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if length < 1.2:
            continue
        tx, ty = dx / length, dy / length
        nx, ny = ty, -tx
        is_front = idx == best_edge_idx

        # Timber sill, floor beam, and eave beam (baroque Fachwerk)
        for z_beam in (plinth_top + 0.08, plinth_top + floor_h, base_m + eave_height_m - 0.28):
            _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, z_beam - 0.11, z_beam + 0.11, 0.0, 0.07)

        # Corner posts
        _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, 0.18, plinth_top, base_m + eave_height_m, 0.0, 0.07)
        _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, length - 0.18, length, plinth_top, base_m + eave_height_m, 0.0, 0.07)

        if length < 3.2:
            continue

        bays = 7 if (is_front and length >= 15.0) else max(1, min(7, floor((length - 0.8) / 2.5)))
        spacing = length / bays
        for fl in range(floors):
            z0_fl = plinth_top + fl * floor_h
            for bay in range(bays):
                u_c = (bay + 0.5) * spacing
                if is_front and fl == 0 and bay == bays // 2:
                    # Historic main Rathaus entrance portal facing Rathausplatz (stone surround, steps, double door, pediment)
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.35, u_c + 1.35, base_m, base_m + 0.45, 0.0, 0.55)
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.10, u_c + 1.10, base_m, z0_fl + 2.85, 0.0, 0.14)
                    _add_box_on_wall(door_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 0.82, u_c + 0.82, base_m + 0.35, z0_fl + 2.55, 0.0, 0.18)
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.25, u_c + 1.25, z0_fl + 2.85, z0_fl + 3.15, 0.0, 0.24)
                    continue

                # Kreuzstockfenster (baroque cross-mullion windows)
                win_w = 1.15
                wz0 = z0_fl + 0.72
                wz1 = min(z0_fl + floor_h - 0.45, wz0 + 1.75)
                if wz1 - wz0 < 0.7:
                    continue
                _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_c - win_w * 0.58, u_c + win_w * 0.58, wz0 - 0.08, wz1 + 0.08, 0.0, 0.07)
                _add_box_on_wall(glass_mesh, start[0], start[1], tx, ty, nx, ny, u_c - win_w * 0.48, u_c + win_w * 0.48, wz0, wz1, 0.0, 0.085)
                # Cross mullions (Kreuzstock)
                _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 0.04, u_c + 0.04, wz0, wz1, 0.0, 0.10)
                wmid = wz0 + (wz1 - wz0) * 0.62
                _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_c - win_w * 0.48, u_c + win_w * 0.48, wmid - 0.04, wmid + 0.04, 0.0, 0.10)

            # Vertical timber framing posts between bays
            for bay in range(1, bays):
                u_p = bay * spacing
                _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_p - 0.08, u_p + 0.08, z0_fl, z0_fl + floor_h, 0.0, 0.065)

        # Front mansard dormer accents (Gauben) facing Rathausplatz
        if is_front and length >= 14.0:
            for frac in (0.28, 0.50, 0.72):
                u_d = frac * length
                dz0 = base_m + eave_height_m + 0.35
                dz1 = dz0 + 1.45
                _add_box_on_wall(gable_mesh, start[0], start[1], tx, ty, nx, ny, u_d - 0.75, u_d + 0.75, dz0, dz1, -0.55, 0.05)
                _add_box_on_wall(glass_mesh, start[0], start[1], tx, ty, nx, ny, u_d - 0.48, u_d + 0.48, dz0 + 0.18, dz1 - 0.18, 0.0, 0.08)
                _add_box_on_wall(roof_mesh, start[0], start[1], tx, ty, nx, ny, u_d - 0.88, u_d + 0.88, dz1, dz1 + 0.45, -0.75, 0.15)

    # Adjacent Rathausturm accent on the SW corner projection
    tc = cfg.get("tower_corner_local_m")
    tower_h = float(cfg.get("tower_height_m", 14.8))
    if tc:
        tcx, tcy = float(tc[0]), float(tc[1])
        # Orient with Rathaus front facade
        f0, f1 = ring[best_edge_idx], ring[best_edge_idx + 1]
        fl_len = max(hypot(f1[0] - f0[0], f1[1] - f0[1]), 1.0)
        ux, uy = (f1[0] - f0[0]) / fl_len, (f1[1] - f0[1]) / fl_len
        vx, vy = uy, -ux
        shaft_top = base_m + eave_height_m + 2.4
        _add_prism(meshes["WallsBrick"], (tcx, tcy), (ux, uy), (vx, vy), 1.65, 1.65, base_m, shaft_top, add_top=True)
        _add_prism(stone_mesh, (tcx, tcy), (ux, uy), (vx, vy), 1.78, 1.78, shaft_top - 0.25, shaft_top + 0.10, add_top=True)
        _add_octagonal_spire(roof_mesh, (tcx, tcy), 2.15, shaft_top + 0.05, base_m + tower_h, sides=4)
        return max(ridge_height_m, tower_h)
    return ridge_height_m


def _build_fortress_building(meshes, polygon: Polygon, base_m: float, max_ground_m: float,
                             eave_height_m: float, ridge_height_m: float, roof_shape: str,
                             ridge_direction_deg: float | None, variant: str, cfg: dict) -> float:
    """Festung Dömitz military garrison buildings: Zeughaus, Hauptwache, Kommandantenremise, Arrestantenhaus."""
    wall_style = cfg.get("wall_style", "WallsBrick")
    wall_mesh = meshes[wall_style]
    gable_mesh = meshes.get(wall_style.replace("Walls", "Gable", 1), wall_mesh)
    roof_mesh = meshes[cfg.get("roof_style", "RoofsClay")]
    stone_mesh = meshes["StoneTrim"]
    timber_mesh = meshes["TimberTrim"]
    glass_mesh = meshes["WindowGlass"]
    door_mesh = meshes["Doors"]

    wall_mesh.add_walls(polygon, eave_height_m, base_m)
    resolved_shape = cfg.get("roof_shape", roof_shape or "hipped")
    ridge_rise = max(1.8, ridge_height_m - eave_height_m)
    _add_roof_with_shape(
        roof_mesh, gable_mesh, polygon, base_m + eave_height_m, ridge_rise,
        roof_shape=resolved_shape,
        ridge_direction_deg=ridge_direction_deg,
        overhang=0.22,
    )

    ground_top = max(base_m, max_ground_m)
    plinth_top = min(base_m + eave_height_m - 0.4, max(base_m + 0.90, ground_top + 0.40))
    _add_plinth_and_cornice(stone_mesh, polygon, base_m, plinth_top, base_m + eave_height_m, cornice_h=0.24, cornice_d=0.14)

    court = cfg.get("courtyard_center_local_m", [-195.0, -25.0])
    ring = list(polygon.exterior.coords)

    # Identify longest facade facing the fortress courtyard
    best_court_idx = -1
    best_court_score = -1e9
    for idx, (start, end) in enumerate(zip(ring, ring[1:])):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if length < 5.0:
            continue
        nx, ny = dy / length, -dx / length
        mx, my = 0.5 * (start[0] + end[0]), 0.5 * (start[1] + end[1])
        to_cx, to_cy = court[0] - mx, court[1] - my
        to_len = max(hypot(to_cx, to_cy), 1.0)
        dot = (nx * to_cx + ny * to_cy) / to_len
        if dot > 0.35 and length * dot > best_court_score:
            best_court_score = length * dot
            best_court_idx = idx

    usable_h = max(2.2, (base_m + eave_height_m) - plinth_top)
    if variant == "festung_kommandantenremise":
        floors = 1
    else:
        floors = max(1, min(2, int(round(usable_h / 3.4))))
    floor_h = usable_h / floors

    for idx, (start, end) in enumerate(zip(ring, ring[1:])):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if length < 2.2:
            continue
        tx, ty = dx / length, dy / length
        nx, ny = ty, -tx
        is_courtyard = idx == best_court_idx

        # Stone stringcourse between floors on 2-story garrison buildings
        if floors >= 2:
            z_belt = plinth_top + floor_h
            _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, length, z_belt - 0.14, z_belt + 0.08, 0.0, 0.10)

        # Classicist stone corner pilasters on Hauptwache
        if variant == "festung_hauptwache":
            _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, 0.0, 0.42, plinth_top, base_m + eave_height_m, 0.0, 0.09)
            _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, length - 0.42, length, plinth_top, base_m + eave_height_m, 0.0, 0.09)

        if length < 3.6:
            continue

        if variant == "festung_kommandantenremise":
            # Wide carriage bays along courtyard side, simple brick windows on rear
            if is_courtyard:
                bays = max(2, min(4, floor(length / 4.2)))
                step = length / bays
                for bay in range(bays):
                    u_c = (bay + 0.5) * step
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.35, u_c + 1.35, base_m, base_m + 2.95, 0.0, 0.12)
                    _add_box_on_wall(door_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.12, u_c + 1.12, base_m, base_m + 2.70, 0.0, 0.15)
            else:
                bays = max(2, min(5, floor(length / 3.2)))
                step = length / bays
                for bay in range(bays):
                    u_c = (bay + 0.5) * step
                    wz0 = plinth_top + 0.55
                    wz1 = min(base_m + eave_height_m - 0.45, wz0 + 1.25)
                    if wz1 - wz0 >= 0.5:
                        _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 0.55, u_c + 0.55, wz0 - 0.08, wz1 + 0.08, 0.0, 0.07)
                        _add_box_on_wall(glass_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 0.42, u_c + 0.42, wz0, wz1, 0.0, 0.09)
            continue

        # Regular military window rhythm (Zeughaus, Hauptwache, Arrestantenhaus)
        bay_pitch = 2.4 if variant == "festung_arrestantenhaus" else 2.75
        bays = max(2, min(7, floor((length - 0.8) / bay_pitch)))
        step = length / bays
        for fl in range(floors):
            z0_fl = plinth_top + fl * floor_h
            for bay in range(bays):
                u_c = (bay + 0.5) * step
                # Central portal on Hauptwache (Mittelbau), Zeughaus, or Arrestantenhaus courtyard facade
                if is_courtyard and fl == 0 and bay == bays // 2 and (variant != "festung_hauptwache" or cfg.get("has_central_portal")):
                    _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.15, u_c + 1.15, base_m, z0_fl + 2.75, 0.0, 0.14)
                    _add_box_on_wall(door_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 0.85, u_c + 0.85, base_m, z0_fl + 2.45, 0.0, 0.17)
                    if variant == "festung_hauptwache":
                        # Classicist crest/pediment cornice above Hauptwache entrance
                        _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 1.45, u_c + 1.45, z0_fl + 2.75, z0_fl + 3.10, 0.0, 0.24)
                    continue

                if variant == "festung_arrestantenhaus":
                    # Smaller strict detention windows with stone sills & vertical bar mullion
                    win_w = 0.82
                    wz0 = z0_fl + 0.95
                    wz1 = min(z0_fl + floor_h - 0.55, wz0 + 1.05)
                else:
                    win_w = 1.08
                    wz0 = z0_fl + 0.72
                    wz1 = min(z0_fl + floor_h - 0.45, wz0 + 1.65)
                if wz1 - wz0 < 0.55:
                    continue
                _add_box_on_wall(stone_mesh, start[0], start[1], tx, ty, nx, ny, u_c - win_w * 0.60, u_c + win_w * 0.60, wz0 - 0.10, wz1 + 0.12, 0.0, 0.08)
                _add_box_on_wall(glass_mesh, start[0], start[1], tx, ty, nx, ny, u_c - win_w * 0.48, u_c + win_w * 0.48, wz0, wz1, 0.0, 0.10)
                if variant == "festung_arrestantenhaus":
                    _add_box_on_wall(timber_mesh, start[0], start[1], tx, ty, nx, ny, u_c - 0.04, u_c + 0.04, wz0, wz1, 0.0, 0.12)
    return ridge_height_m


def add_landmark_building(
    meshes,
    polygon: Polygon,
    eave_height_m: float,
    ridge_height_m: float,
    roof_shape: str,
    ridge_direction_deg: float | None,
    base_m: float,
    max_ground_m: float,
    landmark_cfg: dict,
) -> float:
    """Dispatch configured landmark variant and return final peak height above base_m."""
    variant = landmark_cfg["variant"]
    if variant == "johanneskirche":
        return _build_johanneskirche(meshes, polygon, base_m, max_ground_m, ridge_height_m, landmark_cfg)
    if variant == "rathaus":
        return _build_rathaus(meshes, polygon, base_m, max_ground_m, eave_height_m, ridge_height_m, ridge_direction_deg, landmark_cfg)
    if variant.startswith("festung_"):
        return _build_fortress_building(
            meshes, polygon, base_m, max_ground_m, eave_height_m, ridge_height_m,
            roof_shape, ridge_direction_deg, variant, landmark_cfg,
        )
    raise ValueError(f"Unknown landmark variant: {variant}")
