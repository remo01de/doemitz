"""Locks and weirs (Sprint 14): Schleuse Dömitz on the Müritz-Elde-Wasserstraße.

The lock chamber is the OSM water area tagged water=lock; its gates are waterway=lock_gate ways drawn as a
V (two mitre-gate leaves meeting upstream). DGM1 models the chamber walls as a steep slope; this module puts
vertical concrete walls on the long chamber edges from below the water up to the bank, with a coping, ladder
recesses, bollards and a railing, and returns them as retaining-wall step lines so the terrain generator fills
the bank up to the coping and splits terrain triangles exactly at the wall (like walls.py). Each gate gets two
leaves from below the lower water to the bank with a walkway, railings and balance beams; the leaves also close
the water step between the chamber and the upper reach. Weirs (waterway=weir) become a concrete body whose
crest closes the step between the upper and the lower reach. Dimensions are assumptions (assumed_sprint14_lock).
"""

from __future__ import annotations

from math import ceil, hypot

import numpy as np
from shapely.geometry import LineString, Point, shape
from shapely.ops import linemerge, unary_union

from tools.mesh_generator.architecture import _add_quad, _add_triangle
from tools.mesh_generator.solids import beam, box_faces, frame_box, orient
from tools.mesh_generator.walls import WallStepLine

LOCK_PALETTE = {
    "LockConcrete": (0.34, 0.34, 0.32),
    "LockCoping": (0.46, 0.46, 0.44),
    "LockGate": (0.09, 0.075, 0.06),
    "LockRailing": (0.05, 0.16, 0.10),
    "LockSteel": (0.05, 0.05, 0.055),
}
LOCK_COLLISION_MESHES = {"LockConcrete", "LockCoping", "LockGate", "LockRailing"}
STATION_M = 1.0


def _faces(mesh, quads):
    for q in quads:
        if len(q) == 3:
            _add_triangle(mesh, *q)
        else:
            _add_quad(mesh, *q)


def _level_at(water_surfaces, x, y):
    p = Point(x, y)
    for poly, level in water_surfaces:
        if poly.covers(p):
            return float(level)
    return None


def _level_near(water_surfaces, x, y, dx, dy):
    """Water level of the first water surface found walking from (x, y) along (dx, dy) up to 8 m."""
    for d in np.arange(1.0, 8.01, 0.5):
        lv = _level_at(water_surfaces, x + dx * d, y + dy * d)
        if lv is not None:
            return lv
    return None


def _railing(mesh, pts, z_fn, height=1.05, post_spacing=2.0):
    """Posts, handrail and middle rail along a polyline (pts as (x, y)); z_fn(x, y) gives the walking level."""
    line = LineString(pts)
    if line.length < 0.5:
        return
    n_posts = max(1, int(ceil(line.length / post_spacing)))
    for k in range(n_posts + 1):
        p = line.interpolate(min(line.length, k * line.length / n_posts))
        q = line.interpolate(min(line.length, k * line.length / n_posts + 0.05)) if k < n_posts else line.interpolate(line.length - 0.05)
        tx, ty = q.x - p.x, q.y - p.y
        tl = hypot(tx, ty) or 1.0
        t = (tx / tl, ty / tl)
        n = (t[1], -t[0])
        z0 = z_fn(p.x, p.y)
        _faces(mesh, frame_box((p.x, p.y), t, n, -0.04, 0.04, -0.04, 0.04, z0, z0 + height))
    coords = list(line.coords)
    for (ax, ay), (bx, by) in zip(coords, coords[1:]):
        for dz, h in ((height - 0.06, 0.06), (0.5, 0.04)):
            za, zb = z_fn(ax, ay) + dz, z_fn(bx, by) + dz
            _faces(mesh, beam((ax, ay, za + h * 0.5), (bx, by, zb + h * 0.5), 0.05, h))


def build_edge_wall(meshes, side, water_area, z_bot, water_level, elevation, wall_id, min_top=None, cfg=None,
                    ladders=True, bollards=True, railing=True, bank_search=(1.5, 3.5), step_extend_m=0.0):
    """
    Vertical concrete wall on a water edge (lock chamber or harbour quay): face toward the water from z_bot to the
    bank, coping, ladder recesses, bollards and a railing set back from the edge. Returns (WallStepLine, top array)
    so the terrain generator fills the bank to the coping and splits terrain triangles at the wall line.
    """
    cfg = cfg or {}
    concrete, coping = meshes["LockConcrete"], meshes["LockCoping"]
    railing_m, steel = meshes["LockRailing"], meshes["LockSteel"]
    n = max(2, int(ceil(side.length / STATION_M)) + 1)
    s_vals = np.linspace(0.0, side.length, n)
    pts = [side.interpolate(s) for s in s_vals]
    normals = []
    for i, p in enumerate(pts):
        q = pts[min(i + 1, n - 1)]
        r = pts[max(i - 1, 0)]
        tx, ty = q.x - r.x, q.y - r.y
        tl = hypot(tx, ty) or 1.0
        nx, ny = ty / tl, -tx / tl
        if water_area.contains(Point(p.x + nx * 0.4, p.y + ny * 0.4)):
            nx, ny = -nx, -ny
        normals.append((nx, ny))
    ds = np.arange(float(bank_search[0]), float(bank_search[1]) + 0.01, 0.5)
    bank = np.array([float(np.max(elevation.sample_array(p.x + nx * ds, p.y + ny * ds)))
                     for p, (nx, ny) in zip(pts, normals)])
    top = np.convolve(np.pad(bank, 3, mode="edge"), np.ones(7) / 7.0, mode="valid")
    if min_top is not None:
        top = np.maximum(top, min_top)
    base = np.full_like(top, z_bot)
    p0, p1 = pts[0], pts[1]
    dx, dy = p1.x - p0.x, p1.y - p0.y
    nx0, ny0 = normals[0]
    high_sign = 1.0 if (dy * nx0 - dx * ny0) > 0 else -1.0  # right of the direction is (dy, -dx)
    step_line = side
    step_s = s_vals
    step_top = top + 0.0
    step_base = base
    if step_extend_m > 0.0 and len(pts) >= 2:
        # Sprint 16: extend the terrain step line across the full lock-head concrete block so terrain
        # triangles at the lower/upper gate heels are cleanly clipped down to z_bot on the water side.
        sc = list(side.coords)
        d0 = hypot(sc[1][0] - sc[0][0], sc[1][1] - sc[0][1]) or 1.0
        d1 = hypot(sc[-1][0] - sc[-2][0], sc[-1][1] - sc[-2][1]) or 1.0
        p_pre = (sc[0][0] - (sc[1][0] - sc[0][0]) / d0 * step_extend_m,
                 sc[0][1] - (sc[1][1] - sc[0][1]) / d0 * step_extend_m)
        p_post = (sc[-1][0] + (sc[-1][0] - sc[-2][0]) / d1 * step_extend_m,
                  sc[-1][1] + (sc[-1][1] - sc[-2][1]) / d1 * step_extend_m)
        step_line = LineString([p_pre, *sc, p_post])
        step_s = np.concatenate(([0.0], s_vals + step_extend_m, [side.length + 2.0 * step_extend_m]))
        step_top = np.concatenate(([top[0]], top, [top[-1]]))
        step_base = np.full_like(step_top, z_bot)
    step = WallStepLine(wall_id=wall_id, line=step_line, s_vals=step_s, top_z=step_top, base_z=step_base,
                        high_sign=high_sign, gaps=[], fill_band_m=3.0, low_band_m=2.2)
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        (na_x, na_y), (nb_x, nb_y) = normals[i], normals[i + 1]
        za, zb = float(top[i]), float(top[i + 1])
        inward = (-(na_x + nb_x) * 0.5, -(na_y + nb_y) * 0.5, 0.0)
        outward = ((na_x + nb_x) * 0.5, (na_y + nb_y) * 0.5, 0.0)
        _faces(concrete, [orient([(a.x, a.y, z_bot), (b.x, b.y, z_bot), (b.x, b.y, zb - 0.18), (a.x, a.y, za - 0.18)], inward)])
        ia = (a.x - na_x * 0.05, a.y - na_y * 0.05)
        ib = (b.x - nb_x * 0.05, b.y - nb_y * 0.05)
        oa = (a.x + na_x * 0.6, a.y + na_y * 0.6)
        ob = (b.x + nb_x * 0.6, b.y + nb_y * 0.6)
        _faces(coping, [
            orient([(*ia, za - 0.2), (*ib, zb - 0.2), (*ib, zb + 0.02), (*ia, za + 0.02)], inward),
            orient([(*oa, za - 0.2), (*ob, zb - 0.2), (*ob, zb + 0.02), (*oa, za + 0.02)], outward),
            orient([(*ia, za + 0.02), (*ib, zb + 0.02), (*ob, zb + 0.02), (*oa, za + 0.02)], (0, 0, 1)),
            orient([(*ia, za - 0.2), (*ib, zb - 0.2), (*ob, zb - 0.2), (*oa, za - 0.2)], (0, 0, -1)),
        ])
    # Solid end-caps at both ends of the edge wall (Sprint 15: closes hollow black ends on quay & lock walls)
    for end_idx, adj_idx in ((0, 1), (n - 1, n - 2)):
        pe, pa = pts[end_idx], pts[adj_idx]
        nx, ny = normals[end_idx]
        ze = float(top[end_idx])
        tx, ty = pe.x - pa.x, pe.y - pa.y
        tl = hypot(tx, ty) or 1.0
        cap_out = (tx / tl, ty / tl, 0.0)
        ie = (pe.x - nx * 0.05, pe.y - ny * 0.05)
        oe = (pe.x + nx * 0.6, pe.y + ny * 0.6)
        _faces(concrete, [orient([(pe.x, pe.y, z_bot), (*oe, z_bot), (*oe, ze - 0.18), (pe.x, pe.y, ze - 0.18)], cap_out)])
        _faces(coping, [orient([(*ie, ze - 0.2), (*oe, ze - 0.2), (*oe, ze + 0.02), (*ie, ze + 0.02)], cap_out)])
    if ladders:
        spacing = float(cfg.get("ladder_spacing_m", 15.0))
        for s_l in np.arange(spacing * 0.5, side.length - 2.0, spacing):
            p = side.interpolate(s_l)
            i = min(n - 1, int(round(s_l / STATION_M)))
            nx, ny = normals[i]
            t = (-ny, nx)
            z_t = float(top[i])
            _faces(steel, frame_box((p.x, p.y), t, (-nx, -ny), -0.3, 0.3, -0.02, 0.015, water_level - 0.5, z_t - 0.2,
                                    faces={"side2"}))
            for zr in np.arange(water_level - 0.3, z_t - 0.25, 0.3):
                _faces(railing_m, frame_box((p.x, p.y), t, (-nx, -ny), -0.22, 0.22, 0.02, 0.06, zr, zr + 0.03))
    if bollards:
        spacing = float(cfg.get("bollard_spacing_m", 12.0))
        for s_b in np.arange(spacing * 0.5 + 3.0, side.length - 1.0, spacing):
            p = side.interpolate(s_b)
            i = min(n - 1, int(round(s_b / STATION_M)))
            nx, ny = normals[i]
            z_t = float(top[i]) + 0.02
            _faces(steel, frame_box((p.x + nx * 0.35, p.y + ny * 0.35), (-ny, nx), (nx, ny), -0.12, 0.12, -0.12, 0.12,
                                    z_t, z_t + 0.45))
            _faces(steel, frame_box((p.x + nx * 0.35, p.y + ny * 0.35), (-ny, nx), (nx, ny), -0.17, 0.17, -0.17, 0.17,
                                    z_t + 0.45, z_t + 0.55))
    if railing:
        rail_pts = [(p.x + nx * 0.85, p.y + ny * 0.85) for p, (nx, ny) in zip(pts, normals)]

        def rail_z(x, y, _side=side, _top=top, _s=s_vals):
            return float(np.interp(_side.project(Point(x, y)), _s, _top)) + 0.02

        _railing(railing_m, rail_pts[2:-2] if len(rail_pts) > 5 else (rail_pts[1:-1] if len(rail_pts) > 3 else rail_pts), rail_z)
    return step, top


def build_locks(meshes, scene_layers, water_surfaces, elevation, cfg: dict | None = None):
    """Return (lock reports, weir reports, terrain step lines, exclusion polygons)."""
    cfg = cfg or {}
    concrete, coping, gate_m = meshes["LockConcrete"], meshes["LockCoping"], meshes["LockGate"]
    railing_m, steel = meshes["LockRailing"], meshes["LockSteel"]
    works = scene_layers.get("waterworks", [])
    gates_all = [(w["id"], shape(w["geometry"])) for w in works if w["properties"].get("waterway") == "lock_gate"]
    lock_lines = {w["id"]: w for w in works if w["properties"].get("lock") == "yes"}
    reports, weirs, steps, exclusion = [], [], [], []

    for wf in scene_layers.get("water", []):
        if wf["properties"].get("water") != "lock":
            continue
        chamber = shape(wf["geometry"])
        if chamber.geom_type != "Polygon":
            chamber = max(chamber.geoms, key=lambda g: g.area)
        ring = LineString(chamber.exterior.coords)
        gates = [(gid, g) for gid, g in gates_all if g.distance(ring) < 1.0]
        if len(gates) < 2:
            continue
        gate_union = unary_union([g.buffer(0.05) for _, g in gates])
        sides = linemerge(ring.difference(gate_union))
        raw_sides = [g for g in getattr(sides, "geoms", [sides]) if g.geom_type == "LineString" and g.length > 5.0]
        # Extend each chamber wall 0.55 m into the concrete lock-head blocks at both gate heels so the
        # WallStepLine keeps terrain cleanly depressed right up to and behind the mitre gate corners.
        sides = []
        for s_line in raw_sides:
            sc = list(s_line.coords)
            if len(sc) >= 2:
                d0 = hypot(sc[1][0] - sc[0][0], sc[1][1] - sc[0][1]) or 1.0
                d1 = hypot(sc[-1][0] - sc[-2][0], sc[-1][1] - sc[-2][1]) or 1.0
                ext = 0.55
                sc[0] = (sc[0][0] - (sc[1][0] - sc[0][0]) / d0 * ext, sc[0][1] - (sc[1][1] - sc[0][1]) / d0 * ext)
                sc[-1] = (sc[-1][0] + (sc[-1][0] - sc[-2][0]) / d1 * ext, sc[-1][1] + (sc[-1][1] - sc[-2][1]) / d1 * ext)
            sides.append(LineString(sc))
        lvl_chamber = _level_at(water_surfaces, chamber.representative_point().x, chamber.representative_point().y)
        c = chamber.centroid
        gate_info = []
        for gid, g in gates:
            gm = g.interpolate(0.5, normalized=True)
            dx, dy = gm.x - c.x, gm.y - c.y
            dl = hypot(dx, dy) or 1.0
            outside = _level_near(water_surfaces, gm.x, gm.y, dx / dl, dy / dl)
            gate_info.append((gid, g, outside))
        outs = [o for _, _, o in gate_info if o is not None]
        upper = max(outs + [lvl_chamber or -99.0])
        lower = min(outs + [lvl_chamber if lvl_chamber is not None else upper])
        z_bot = lower - float(cfg.get("chamber_depth_below_lower_m", 1.6))
        # chamber walls on the long sides (concrete face toward the water, coping, bank filled behind)
        wall_tops = []
        for k, side in enumerate(sides):
            step, top = build_edge_wall(meshes, side, chamber, z_bot, lower, elevation, f"{wf['id']}:wall{k}",
                                        min_top=upper + float(cfg.get("min_freeboard_m", 0.8)), cfg=cfg)
            if step is not None:
                steps.append(step)
                wall_tops.extend(top.tolist())
        z_walk = float(np.median(wall_tops)) + 0.02 if wall_tops else upper + 1.0
        # mitre gates: two leaves per gate, walkway with railings on top, balance beams over the bank
        gates_report = []
        for gid, g, outside in gate_info:
            coords = list(g.coords)
            if len(coords) < 3:
                coords = [coords[0], ((coords[0][0] + coords[-1][0]) / 2, (coords[0][1] + coords[-1][1]) / 2), coords[-1]]
            mitre = coords[len(coords) // 2]
            heels = [coords[0], coords[-1]]
            for heel in heels:
                tx, ty = mitre[0] - heel[0], mitre[1] - heel[1]
                tl = hypot(tx, ty) or 1.0
                t = (tx / tl, ty / tl)
                nrm = (t[1], -t[0])
                _faces(gate_m, frame_box(heel, t, nrm, -0.35, tl, -0.25, 0.25, z_bot, z_walk - 0.12))
                _faces(coping, frame_box(heel, t, nrm, -0.1, tl + 0.05, -0.55, 0.55, z_walk - 0.12, z_walk))
                for side_off in (-0.5, 0.5):
                    a = (heel[0] + nrm[0] * side_off, heel[1] + nrm[1] * side_off)
                    b = (heel[0] + t[0] * tl + nrm[0] * side_off, heel[1] + t[1] * tl + nrm[1] * side_off)
                    _railing(railing_m, [a, b], lambda x, y: z_walk, post_spacing=1.6)
                # balance beam from the heel back over the bank
                bx, by = heel[0] - t[0] * 0.3, heel[1] - t[1] * 0.3
                ex, ey = heel[0] - t[0] * 5.5, heel[1] - t[1] * 5.5
                _faces(steel, beam((bx, by, z_walk + 0.75), (ex, ey, z_walk + 0.85), 0.28, 0.32))
            # lock heads: walkable concrete blocks around both heels at walkway height, so the gate walkway always
            # ends on solid ground (the DGM bank beside a heel can drop straight into the upper reach)
            gm = g.interpolate(0.5, normalized=True)
            ax, ay = gm.x - c.x, gm.y - c.y
            al = hypot(ax, ay) or 1.0
            axis = (ax / al, ay / al)
            for heel in heels:
                nx, ny = -axis[1], axis[0]
                if (heel[0] - gm.x) * nx + (heel[1] - gm.y) * ny < 0:
                    nx, ny = -nx, -ny
                _faces(concrete, frame_box(heel, axis, (nx, ny), 0.0, 3.0, -0.05, 3.0, z_bot, z_walk - 0.02))
                _faces(coping, frame_box(heel, axis, (nx, ny), -0.05, 3.05, -0.1, 3.05, z_walk - 0.02, z_walk,
                                         faces={"top", "side0", "side1", "side2", "side3"}))
            gates_report.append({
                "id": gid, "leaves": len(heels), "outside_level_m": round(outside, 3) if outside is not None else None,
                "length_m": round(g.length, 2),
            })
        exclusion.append(chamber.buffer(4.0))
        line = next((w for w in lock_lines.values() if shape(w["geometry"]).distance(chamber) < 1.0), None)
        reports.append({
            "id": wf["id"],
            "name": (line or {}).get("properties", {}).get("lock_name") or (line or {}).get("properties", {}).get("name", ""),
            "lock_line_id": (line or {}).get("id"),
            "chamber_length_m": round(max(s.length for s in sides), 2) if sides else None,
            "chamber_area_m2": round(chamber.area, 1),
            "chamber_level_m": round(lvl_chamber, 3) if lvl_chamber is not None else None,
            "upper_level_m": round(upper, 3),
            "lower_level_m": round(lower, 3),
            "lift_m": round(upper - lower, 2),
            "wall_top_z_m": [round(min(wall_tops), 3), round(max(wall_tops), 3)] if wall_tops else None,
            "walkway_z_m": round(z_walk, 3),
            "gates": gates_report,
            "dimensions_source": cfg.get("dimensions_source", "assumed_sprint14_lock"),
        })

    # weirs: concrete body across the channel, crest at the upper water level
    for w in works:
        if w["properties"].get("waterway") not in ("weir", "dam"):
            continue
        g = shape(w["geometry"])
        if g.geom_type != "LineString":
            continue
        mid = g.interpolate(0.5, normalized=True)
        a, b = g.coords[0], g.coords[-1]
        tl = hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        nx, ny = (b[1] - a[1]) / tl, -(b[0] - a[0]) / tl
        l1 = _level_near(water_surfaces, mid.x, mid.y, nx, ny)
        l2 = _level_near(water_surfaces, mid.x, mid.y, -nx, -ny)
        lv = [v for v in (l1, l2) if v is not None]
        if not lv:
            continue
        up, low = max(lv), min(lv)
        coords = list(g.coords)
        # extend into the banks so the body meets the shore
        (x0, y0), (x1, y1) = coords[0], coords[1]
        (xa, ya), (xb, yb) = coords[-2], coords[-1]
        d0 = hypot(x1 - x0, y1 - y0) or 1.0
        d1 = hypot(xb - xa, yb - ya) or 1.0
        coords = [(x0 - (x1 - x0) / d0 * 1.5, y0 - (y1 - y0) / d0 * 1.5)] + coords + \
                 [(xb + (xb - xa) / d1 * 1.5, yb + (yb - ya) / d1 * 1.5)]
        for (ax, ay), (bx, by) in zip(coords, coords[1:]):
            sl = hypot(bx - ax, by - ay) or 1.0
            t = ((bx - ax) / sl, (by - ay) / sl)
            nrm = (t[1], -t[0])
            _faces(concrete, frame_box((ax, ay), t, nrm, 0.0, sl, -1.0, 1.0, low - 1.2, up + 0.05))
        # piers with a service walkway on top
        bank_z = max(float(elevation.sample(*coords[0])), float(elevation.sample(*coords[-1])))
        for frac in (0.0, 0.33, 0.66, 1.0):
            p = g.interpolate(frac, normalized=True)
            _faces(concrete, frame_box((p.x, p.y), (nx, ny), (-ny, nx), -1.2, 1.2, -0.3, 0.3, up, bank_z + 0.3))
        weirs.append({
            "id": w["id"], "length_m": round(g.length, 2), "upper_level_m": round(up, 3), "lower_level_m": round(low, 3),
            "drop_m": round(up - low, 2), "dimensions_source": cfg.get("dimensions_source", "assumed_sprint14_lock"),
        })
        exclusion.append(g.buffer(3.0))
    return reports, weirs, steps, exclusion
