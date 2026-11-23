"""Hafen Dömitz (Sprint 14): floating jetties, piles, groynes, quay walls and moored boats.

OSM man_made=pier ways in the marina are floating jetties: over water their deck floats 0.35 m above the water
level of the reach below them, over land they follow the terrain 0.12 m above ground, with a ramp in between
(gangways from the promenade). Lines get a deck 2.0 m wide (main jetties >= 25 m) or 1.2 m (finger piers),
closed pier ways are platforms. Mooring nodes and the main jetties get timber piles. Groynes (man_made=groyne) are
stone ridges. Water edges near the jetties whose bank stands at least 1.2 m above the water get a quay wall
(locks.build_edge_wall). Boats are deterministic HISM instances beside finger piers and long jetties, only where
their whole hull lies in water and touches no deck and no other boat. All widths and heights are assumptions
(assumed_sprint14_harbour).
"""

from __future__ import annotations

from math import atan2, ceil, cos, degrees, hypot, isfinite, sin
import re

import numpy as np
from shapely import constrained_delaunay_triangles, orient_polygons
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import linemerge, unary_union

from tools.mesh_generator.architecture import _add_quad, _add_triangle
from tools.mesh_generator.locks import _railing, build_edge_wall
from tools.mesh_generator.solids import box_faces, frame_box, orient

HARBOUR_PALETTE = {
    "PierDeck": (0.26, 0.21, 0.16),
    "PierFloat": (0.07, 0.07, 0.075),
    "PierPile": (0.13, 0.10, 0.07),
    "GroyneStone": (0.30, 0.29, 0.27),
}
HARBOUR_COLLISION_MESHES = {"PierDeck", "PierFloat", "PierPile", "GroyneStone"}
FLOAT_ABOVE_WATER_M = 0.35
DECK_ABOVE_GROUND_M = 0.12
BOAT_LENGTH_M = 9.0  # prototype length of the boat props (doemitz_prop_meshes.stylized_boat)
BOAT_BEAM_M = 3.0


def _faces(mesh, quads):
    for q in quads:
        if len(q) == 3:
            _add_triangle(mesh, *q)
        else:
            _add_quad(mesh, *q)


def _water_level(water_surfaces, x, y):
    p = Point(x, y)
    for poly, level in water_surfaces:
        if poly.covers(p):
            return float(level)
    return None


def _ue_yaw(dx, dy):
    return round(degrees(atan2(dx, dy)), 2)  # Unreal X = north, Y = east


def _parse_meters(raw) -> float | None:
    """Parse an OSM length tag in meters (supports '2', '2.5', '2 m', '2,5 m'); returns None if invalid."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if isfinite(val) and 0.0 < val <= 30.0 else None
    text = str(raw).strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:m)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    val = float(match.group(1).replace(",", "."))
    return val if isfinite(val) and 0.0 < val <= 30.0 else None


def _extend_line(line: LineString, extend_start_m: float = 0.0, extend_end_m: float = 0.0) -> LineString:
    coords = list(line.coords)
    if len(coords) < 2:
        return line
    if extend_start_m > 0.0:
        dx, dy = coords[0][0] - coords[1][0], coords[0][1] - coords[1][1]
        d = hypot(dx, dy) or 1.0
        coords.insert(0, (coords[0][0] + dx / d * extend_start_m, coords[0][1] + dy / d * extend_start_m))
    if extend_end_m > 0.0:
        dx, dy = coords[-1][0] - coords[-2][0], coords[-1][1] - coords[-2][1]
        d = hypot(dx, dy) or 1.0
        coords.append((coords[-1][0] + dx / d * extend_end_m, coords[-1][1] + dy / d * extend_end_m))
    return LineString(coords)


def _emit_deck_strip(deck, floats, stations, zs, half):
    """Emit walkable top deck strip, side float walls, and closed end caps along stations."""
    n = len(stations)
    for i in range(n - 1):
        a, b = stations[i], stations[i + 1]
        tx, ty = b.x - a.x, b.y - a.y
        tl = hypot(tx, ty) or 1.0
        nx, ny = ty / tl, -tx / tl
        za, zb = zs[i], zs[i + 1]
        la = (a.x + nx * half, a.y + ny * half)
        ra = (a.x - nx * half, a.y - ny * half)
        lb = (b.x + nx * half, b.y + ny * half)
        rb = (b.x - nx * half, b.y - ny * half)
        _faces(deck, [orient([(*ra, za), (*la, za), (*lb, zb), (*rb, zb)], (0, 0, 1))])
        for s_pt_a, s_pt_b, side in ((la, lb, 1.0), (ra, rb, -1.0)):
            _faces(floats, [orient([(*s_pt_a, za - 0.4), (*s_pt_b, zb - 0.4), (*s_pt_b, zb), (*s_pt_a, za)],
                                   (nx * side, ny * side, 0.0))])
    for i in (0, n - 1):
        p = stations[i]
        q = stations[1] if i == 0 else stations[-2]
        tx, ty = (p.x - q.x), (p.y - q.y)
        tl = hypot(tx, ty) or 1.0
        nx, ny = ty / tl, -tx / tl
        _faces(floats, [orient([(p.x + nx * half, p.y + ny * half, zs[i] - 0.4),
                                (p.x - nx * half, p.y - ny * half, zs[i] - 0.4),
                                (p.x - nx * half, p.y - ny * half, zs[i]),
                                (p.x + nx * half, p.y + ny * half, zs[i])], (tx / tl, ty / tl, 0.0))])


def _emit_side_railings(railing_mesh, stations, zs, half):
    """Emit handrails along both sides of an elevated gangway/landing."""
    s_cum = [0.0]
    for a, b in zip(stations, stations[1:]):
        s_cum.append(s_cum[-1] + hypot(b.x - a.x, b.y - a.y))
    total = s_cum[-1]
    if total < 0.6:
        return
    base_line = LineString([(p.x, p.y) for p in stations])
    for side in (-1.0, 1.0):
        pts = []
        for idx, p in enumerate(stations):
            q = stations[min(idx + 1, len(stations) - 1)]
            r = stations[max(idx - 1, 0)]
            tx, ty = q.x - r.x, q.y - r.y
            tl = hypot(tx, ty) or 1.0
            nx, ny = ty / tl, -tx / tl
            pts.append((p.x + nx * (half - 0.08) * side, p.y + ny * (half - 0.08) * side))

        def z_fn(x, y, _line=base_line, _sc=s_cum, _zs=zs):
            return float(np.interp(_line.project(Point(x, y)), _sc, _zs))

        _railing(railing_mesh, pts, z_fn, height=1.0, post_spacing=2.0)


def build_harbour(meshes, scene_layers, water_surfaces, elevation, cfg: dict | None = None, skip_water=(),
                  existing_walls=()):
    """
    Return (report, boat instances, terrain step lines, walkable deck polygons, exclusion polygons). skip_water:
    water polygons that already have walls (lock chambers); existing_walls: OSM wall lines (no quay beside them).
    """
    cfg = cfg or {}
    deck, floats, piles, groyne_m = meshes["PierDeck"], meshes["PierFloat"], meshes["PierPile"], meshes["GroyneStone"]
    railing_m = meshes.get("LockRailing", piles)
    piers_report, decks, exclusion = [], [], []
    finger_piers, long_piers = [], []
    gangways_report = []

    def deck_z(x, y):
        lv = _water_level(water_surfaces, x, y)
        if lv is not None:
            return lv + FLOAT_ABOVE_WATER_M, True
        return float(elevation.sample(x, y)) + DECK_ABOVE_GROUND_M, False

    # Pre-scan pier geometries so quay walls can be computed first and shore gangways can align cleanly to quay tops.
    sorted_piers = sorted(scene_layers.get("piers", []), key=lambda f: f["id"])
    raw_deck_geoms = []
    raw_pier_lines: list[tuple[str, LineString]] = []
    for feature in sorted_piers:
        kind = feature["properties"].get("man_made", "pier")
        if kind in ("groyne", "breakwater"):
            continue
        geom = shape(feature["geometry"])
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            for poly in getattr(geom, "geoms", [geom]):
                raw_deck_geoms.append(poly)
        else:
            for line in getattr(geom, "geoms", [geom]):
                if line.geom_type == "LineString" and line.length >= 1.0:
                    w = _parse_meters(feature["properties"].get("width")) or (2.0 if line.length >= 25.0 else 1.2)
                    raw_deck_geoms.append(line.buffer(w * 0.5, cap_style="flat"))
                    raw_pier_lines.append((feature["id"], line))

    # quay walls: water edges within 30 m of the jetties where the bank stands >= 1.2 m above the water
    steps, quays = [], []
    quay_profiles: list[tuple[LineString, np.ndarray, np.ndarray]] = []
    jetty_zone = unary_union([g.buffer(30.0) for g in raw_deck_geoms]) if raw_deck_geoms else None
    if jetty_zone is not None:
        walls_zone = unary_union([w.buffer(2.0) for w in existing_walls]) if existing_walls else None
        for poly, level in water_surfaces:
            if not poly.intersects(jetty_zone):
                continue
            if any(poly.intersection(sw).area > 0.5 * poly.area for sw in skip_water):
                continue
            edge = LineString(poly.exterior.coords).intersection(jetty_zone)
            if walls_zone is not None:
                edge = edge.difference(walls_zone)
            pieces = linemerge(edge) if edge.geom_type == "MultiLineString" else edge
            for piece in getattr(pieces, "geoms", [pieces]):
                if piece.geom_type != "LineString" or piece.length < 6.0:
                    continue
                for stretch in _high_bank_stretches(piece, poly, level, elevation, 1.2):
                    step, top = build_edge_wall(meshes, stretch, poly, level - 1.0, level, elevation,
                                                f"quay:{len(quays)}", cfg=cfg, railing=False, bank_search=(1.0, 2.5))
                    steps.append(step)
                    quay_profiles.append((stretch, step.s_vals, top))
                    quays.append({"length_m": round(stretch.length, 2), "top_z_m": [round(float(top.min()), 3),
                                                                                    round(float(top.max()), 3)]})

    def quay_top_near(x, y, max_dist=3.5):
        pt = Point(x, y)
        best_d = max_dist
        best_z = None
        for stretch, s_vals, top in quay_profiles:
            d = stretch.distance(pt)
            if d < best_d:
                best_d = d
                best_z = float(np.interp(stretch.project(pt), s_vals, top))
        return best_z

    # Detect OSM highway=steps ways over water linking a quay landing pier to a floating jetty (e.g. marina gangways).
    landing_pier_info: dict[str, tuple[float, int]] = {}  # pier_id -> (z_landing, land_end_idx: 0 or -1)
    gangway_step_specs: list[tuple[str, LineString, float, float]] = []
    for road in sorted(scene_layers.get("roads", []), key=lambda r: r["id"]):
        if road["properties"].get("highway") != "steps":
            continue
        rgeom = shape(road["geometry"])
        for rline in getattr(rgeom, "geoms", [rgeom]):
            if rline.geom_type != "LineString" or rline.length < 2.0:
                continue
            mid = rline.interpolate(0.5, normalized=True)
            mid_lv = _water_level(water_surfaces, mid.x, mid.y)
            if mid_lv is None:
                continue
            p0, p1 = Point(rline.coords[0]), Point(rline.coords[-1])
            # Match one endpoint to a short quay-connected landing pier, and the opposite endpoint to a floating jetty.
            landing_match = None
            for end_idx, ep in ((0, p0), (1, p1)):
                for pid, pline in raw_pier_lines:
                    if pline.length >= 10.0 or pline.distance(ep) > 1.5:
                        continue
                    pa, pb = pline.coords[0], pline.coords[-1]
                    wa, wb = _water_level(water_surfaces, *pa), _water_level(water_surfaces, *pb)
                    if (wa is None) != (wb is None):
                        land_end = 0 if wa is None else -1
                        lp = pa if land_end == 0 else pb
                        zq = quay_top_near(*lp, 3.0)
                        if zq is not None or float(elevation.sample(*lp)) - mid_lv >= 1.2:
                            z_land = max(zq if zq is not None else -99.0, float(elevation.sample(*lp))) + 0.04
                            landing_match = (end_idx, pid, z_land, land_end)
                            break
                if landing_match is not None:
                    break
            jetty_match = None
            if landing_match is not None:
                other_ep = p1 if landing_match[0] == 0 else p0
                for pid, pline in raw_pier_lines:
                    if pline.length >= 15.0 and pline.distance(other_ep) <= 3.0:
                        jetty_match = (1 - landing_match[0], pid, mid_lv + FLOAT_ABOVE_WATER_M)
                        break
            if landing_match is not None and jetty_match is not None:
                l_end, l_pid, z_land, land_end = landing_match
                _, _, z_float = jetty_match
                landing_pier_info[l_pid] = (z_land, land_end)
                ordered = LineString(list(rline.coords)) if l_end == 0 else LineString(list(reversed(rline.coords)))
                gangway_step_specs.append((road["id"], ordered, z_land, z_float))

    for feature in sorted_piers:
        props = feature["properties"]
        geom = shape(feature["geometry"])
        kind = props.get("man_made", "pier")
        if kind == "groyne" or kind == "breakwater":
            for line in getattr(geom, "geoms", [geom]):
                if line.geom_type != "LineString":
                    continue
                _add_groyne(groyne_m, line, water_surfaces, elevation)
                exclusion.append(line.buffer(2.5))
            piers_report.append({"id": feature["id"], "kind": kind, "length_m": round(geom.length, 2)})
            continue
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            for poly in getattr(geom, "geoms", [geom]):
                c = poly.representative_point()
                z, floating = deck_z(c.x, c.y)
                for tri in orient_polygons(constrained_delaunay_triangles(poly)).geoms:
                    a, b, cc = list(tri.exterior.coords)[:3]
                    _add_triangle(deck, (a[0], a[1], z), (b[0], b[1], z), (cc[0], cc[1], z))
                ring = list(poly.exterior.coords)
                for (ax, ay), (bx, by) in zip(ring, ring[1:]):
                    out = (by - ay, -(bx - ax), 0.0)  # exterior is CCW: right normal points outward
                    _faces(floats, [orient([(ax, ay, z - 0.4), (bx, by, z - 0.4), (bx, by, z), (ax, ay, z)], out)])
                decks.append((poly, z))
                exclusion.append(poly.buffer(1.0))
            piers_report.append({"id": feature["id"], "kind": "platform", "area_m2": round(geom.area, 1)})
            continue
        for line in getattr(geom, "geoms", [geom]):
            if line.geom_type != "LineString" or line.length < 1.0:
                continue
            width = _parse_meters(props.get("width")) or (2.0 if line.length >= 25.0 else 1.2)
            half = width * 0.5

            # Special case: quay landing platform serving OSM over-water gangway stairs.
            if feature["id"] in landing_pier_info:
                z_land, land_end = landing_pier_info[feature["id"]]
                half = max(half, 1.0)
                build_line = _extend_line(
                    line,
                    extend_start_m=1.2 if land_end == 0 else 0.3,
                    extend_end_m=1.2 if land_end == -1 else 0.3,
                )
                n = max(2, int(ceil(build_line.length / 1.0)) + 1)
                stations = [build_line.interpolate(i / (n - 1), normalized=True) for i in range(n)]
                zs = [z_land] * n
                _emit_deck_strip(deck, floats, stations, zs, half)
                _emit_side_railings(railing_m, stations, zs, half)
                # Timber support piles under the waterward landing edge
                water_pt = stations[-1] if land_end == 0 else stations[0]
                adj_pt = stations[-2] if land_end == 0 else stations[1]
                tx, ty = water_pt.x - adj_pt.x, water_pt.y - adj_pt.y
                tl = hypot(tx, ty) or 1.0
                nx, ny = ty / tl, -tx / tl
                lv = _water_level(water_surfaces, water_pt.x, water_pt.y)
                z_pile_bot = (lv if lv is not None else z_land - 3.0) - 1.2
                for side in (-1.0, 1.0):
                    _add_pile(piles, water_pt.x + nx * (half - 0.15) * side, water_pt.y + ny * (half - 0.15) * side,
                              z_pile_bot, z_land - 0.05)
                decks.append((build_line.buffer(half, cap_style="flat"), z_land))
                exclusion.append(build_line.buffer(half + 1.0))
                piers_report.append({
                    "id": feature["id"], "kind": "quay_landing", "length_m": round(build_line.length, 2),
                    "width_m": round(half * 2.0, 2), "floating_share": 0.0,
                })
                continue

            # Check whether either end connects to land or a quay wall for smooth gangway ramping.
            p_start, p_end = line.coords[0], line.coords[-1]
            dx_l, dy_l = p_end[0] - p_start[0], p_end[1] - p_start[1]
            dl_l = hypot(dx_l, dy_l) or 1.0
            tx_l, ty_l = dx_l / dl_l, dy_l / dl_l
            start_wet = _water_level(water_surfaces, *p_start) is not None
            end_wet = _water_level(water_surfaces, *p_end) is not None
            start_near_land = (not start_wet) or (_water_level(water_surfaces, p_start[0] - tx_l * 1.5, p_start[1] - ty_l * 1.5) is None)
            end_near_land = (not end_wet) or (_water_level(water_surfaces, p_end[0] + tx_l * 1.5, p_end[1] + ty_l * 1.5) is None)

            build_line = line
            ramp_end = None  # 0 = start is landward, -1 = end is landward
            if start_near_land and not end_near_land:
                ramp_end = 0
                build_line = _extend_line(line, extend_start_m=1.2 if start_wet else 0.6)
            elif end_near_land and not start_near_land:
                ramp_end = -1
                build_line = _extend_line(line, extend_end_m=1.2 if end_wet else 0.6)

            n = max(2, int(ceil(build_line.length / 1.0)) + 1)
            stations = [build_line.interpolate(i / (n - 1), normalized=True) for i in range(n)]
            zs, wet = [], []
            for p in stations:
                z, fl = deck_z(p.x, p.y)
                zs.append(z)
                wet.append(fl)

            # Smoothly interpolate ramp from floating deck up to land/quay anchor height (max ~13° slope where room permits).
            if ramp_end is not None and any(wet):
                land_idx = 0 if ramp_end == 0 else n - 1
                lp = stations[land_idx]
                zq = quay_top_near(lp.x, lp.y, max_dist=2.5)
                z_float = next(z for z, fl in zip(zs, wet) if fl)
                z_land = max(
                    zq + 0.04 if zq is not None else -99.0,
                    float(elevation.sample(lp.x, lp.y)) + DECK_ABOVE_GROUND_M,
                )
                rise = abs(z_land - z_float)
                if rise >= 0.25:
                    ramp_len = min(build_line.length, max(4.5, rise * 4.5))
                    for i, p in enumerate(stations):
                        dist_from_land = build_line.project(p) if ramp_end == 0 else (build_line.length - build_line.project(p))
                        if dist_from_land <= ramp_len:
                            t = dist_from_land / max(ramp_len, 0.1)
                            zs[i] = z_land * (1.0 - t) + z_float * t
                    slope_deg = round(degrees(atan2(rise, max(ramp_len, 0.1))), 1)
                    gangways_report.append({
                        "id": feature["id"], "kind": "pier_ramp",
                        "length_m": round(ramp_len, 2),
                        "z_low_m": round(min(z_float, z_land), 3),
                        "z_high_m": round(max(z_float, z_land), 3),
                        "slope_deg": slope_deg,
                    })

            _emit_deck_strip(deck, floats, stations, zs, half)
            decks.append((build_line.buffer(half, cap_style="flat"), float(np.median(zs))))
            exclusion.append(build_line.buffer(half + 1.0))
            entry = {"id": feature["id"], "kind": "jetty", "length_m": round(line.length, 2), "width_m": width,
                     "floating_share": round(sum(wet) / len(wet), 2)}
            piers_report.append(entry)
            if sum(wet) / len(wet) > 0.8:
                (finger_piers if line.length < 15.0 else long_piers).append((feature["id"], line, half))
            # guide piles along long floating jetties
            if line.length >= 25.0:
                for k, s_p in enumerate(np.arange(4.0, line.length - 2.0, 8.0)):
                    p = line.interpolate(s_p)
                    lv = _water_level(water_surfaces, p.x, p.y)
                    if lv is None:
                        continue
                    q = line.interpolate(min(line.length, s_p + 0.1))
                    tx, ty = q.x - p.x, q.y - p.y
                    tl = hypot(tx, ty) or 1.0
                    side = 1.0 if k % 2 == 0 else -1.0
                    cx, cy = p.x + ty / tl * (half + 0.25) * side, p.y - tx / tl * (half + 0.25) * side
                    _add_pile(piles, cx, cy, lv - 1.2, lv + 1.9)

    # Build walkable sloped harbour gangways (OSM highway=steps linking quay landing to main floating jetty)
    for gw_id, gw_line, z_high, z_low in gangway_step_specs:
        gw_width = 1.5
        gw_half = gw_width * 0.5
        build_gw = _extend_line(gw_line, extend_start_m=0.35, extend_end_m=0.35)
        n = max(3, int(ceil(build_gw.length / 1.0)) + 1)
        stations = [build_gw.interpolate(i / (n - 1), normalized=True) for i in range(n)]
        zs = [z_high * (1.0 - i / (n - 1)) + z_low * (i / (n - 1)) for i in range(n)]
        _emit_deck_strip(deck, floats, stations, zs, gw_half)
        _emit_side_railings(railing_m, stations, zs, gw_half)
        decks.append((build_gw.buffer(gw_half, cap_style="flat"), (z_high + z_low) * 0.5))
        exclusion.append(build_gw.buffer(gw_half + 0.8))
        slope_deg = round(degrees(atan2(abs(z_high - z_low), max(gw_line.length, 0.1))), 1)
        gangways_report.append({
            "id": gw_id, "kind": "quay_steps_gangway",
            "length_m": round(gw_line.length, 2),
            "z_low_m": round(z_low, 3),
            "z_high_m": round(z_high, 3),
            "slope_deg": slope_deg,
        })

    moorings = 0
    for feature in scene_layers.get("moorings", []):
        p = shape(feature["geometry"])
        lv = _water_level(water_surfaces, p.x, p.y)
        z0 = (lv if lv is not None else float(elevation.sample(p.x, p.y))) - 1.2
        _add_pile(piles, p.x, p.y, z0, z0 + 3.1)
        moorings += 1

    boats = _place_boats(finger_piers, long_piers, decks, water_surfaces, cfg)
    report = {
        "piers": piers_report,
        "jetties": sum(1 for p in piers_report if p["kind"] == "jetty"),
        "platforms": sum(1 for p in piers_report if p["kind"] == "platform"),
        "groynes": sum(1 for p in piers_report if p["kind"] in ("groyne", "breakwater")),
        "mooring_piles": moorings,
        "quay_walls": quays,
        "gangways": gangways_report,
        "boats": len(boats),
        "dimensions_source": cfg.get("dimensions_source", "assumed_sprint14_harbour"),
    }
    return report, boats, steps, decks, exclusion


def _high_bank_stretches(line, water_poly, level, elevation, min_rise):
    n = max(2, int(ceil(line.length)) + 1)
    flags = []
    for i in range(n):
        p = line.interpolate(i / (n - 1), normalized=True)
        q = line.interpolate(min(1.0, (i + 0.5) / (n - 1)), normalized=True)
        tx, ty = q.x - p.x, q.y - p.y
        tl = hypot(tx, ty) or 1.0
        nx, ny = ty / tl, -tx / tl
        if water_poly.contains(Point(p.x + nx * 0.5, p.y + ny * 0.5)):
            nx, ny = -nx, -ny
        bank = max(float(elevation.sample(p.x + nx * d, p.y + ny * d)) for d in (1.0, 1.5, 2.0, 2.5))
        flags.append(bank - level >= min_rise)
    out, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - 1 - start >= 6:
                coords = [line.interpolate(k / (n - 1), normalized=True) for k in range(start, i)]
                out.append(LineString([(c.x, c.y) for c in coords]))
            start = None
    return out


def _add_pile(mesh, x, y, z0, z1, r=0.16, sides=8):
    pts0 = [(x + r * cos(6.283185307 * k / sides), y + r * sin(6.283185307 * k / sides)) for k in range(sides)]
    for k in range(sides):
        a, b = pts0[k], pts0[(k + 1) % sides]
        _add_quad(mesh, (a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1))
    for k in range(1, sides - 1):
        _add_triangle(mesh, (pts0[0][0], pts0[0][1], z1), (pts0[k][0], pts0[k][1], z1), (pts0[k + 1][0], pts0[k + 1][1], z1))


def _add_groyne(mesh, line, water_surfaces, elevation):
    """Stone groyne: trapezoid ridge 3 m wide at the base, 1 m at the crown, crown 0.6 m above ground/water."""
    n = max(2, int(ceil(line.length / 2.0)) + 1)
    stations = [line.interpolate(i / (n - 1), normalized=True) for i in range(n)]
    for i in range(n - 1):
        a, b = stations[i], stations[i + 1]
        tx, ty = b.x - a.x, b.y - a.y
        tl = hypot(tx, ty) or 1.0
        nx, ny = ty / tl, -tx / tl
        ga = max(float(elevation.sample(a.x, a.y)), _water_level(water_surfaces, a.x, a.y) or -99.0)
        gb = max(float(elevation.sample(b.x, b.y)), _water_level(water_surfaces, b.x, b.y) or -99.0)
        for side in (1.0, -1.0):
            _faces(mesh, [orient([(a.x + nx * 1.5 * side, a.y + ny * 1.5 * side, ga - 0.3),
                                  (b.x + nx * 1.5 * side, b.y + ny * 1.5 * side, gb - 0.3),
                                  (b.x + nx * 0.5 * side, b.y + ny * 0.5 * side, gb + 0.6),
                                  (a.x + nx * 0.5 * side, a.y + ny * 0.5 * side, ga + 0.6)], (nx * side, ny * side, 0.6))])
        _faces(mesh, [orient([(a.x + nx * 0.5, a.y + ny * 0.5, ga + 0.6), (b.x + nx * 0.5, b.y + ny * 0.5, gb + 0.6),
                              (b.x - nx * 0.5, b.y - ny * 0.5, gb + 0.6), (a.x - nx * 0.5, a.y - ny * 0.5, ga + 0.6)],
                             (0, 0, 1))])


def _boat_footprint(cx, cy, dx, dy, length, beam):
    nx, ny = dy, -dx
    hl, hb = length * 0.5, beam * 0.5
    return Polygon([(cx + dx * hl + nx * hb, cy + dy * hl + ny * hb), (cx - dx * hl + nx * hb, cy - dy * hl + ny * hb),
                    (cx - dx * hl - nx * hb, cy - dy * hl - ny * hb), (cx + dx * hl - nx * hb, cy + dy * hl - ny * hb)])


def _place_boats(finger_piers, long_piers, decks, water_surfaces, cfg):
    """Deterministic moored boats beside finger piers and along long jetties."""
    deck_union = unary_union([d.buffer(0.25) for d, _ in decks]) if decks else None
    taken = []
    boats = []
    occupancy = float(cfg.get("berth_occupancy", 0.7))

    def try_place(cx, cy, dx, dy, length, seed):
        h = (seed * 2654435761) & 0xFFFFFFFF
        if (h % 1000) / 1000.0 >= occupancy:
            return
        fp = _boat_footprint(cx, cy, dx, dy, length, BOAT_BEAM_M * length / BOAT_LENGTH_M)
        if deck_union is not None and fp.intersects(deck_union):
            return
        if any(fp.intersects(t) for t in taken):
            return
        lv = None
        for poly, level in water_surfaces:
            if poly.buffer(-0.3).covers(fp):
                lv = level
                break
        if lv is None:
            return
        taken.append(fp.buffer(0.4))
        boats.append([round(cx, 4), round(cy, 4), round(lv, 4), _ue_yaw(dx, dy),
                      round(length / BOAT_LENGTH_M, 3), int(h % 3)])

    seed = 1
    for _, line, half in finger_piers:
        a, b = line.coords[0], line.coords[-1]
        tl = hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        dx, dy = (b[0] - a[0]) / tl, (b[1] - a[1]) / tl
        length = max(6.5, min(11.0, line.length * 0.95))
        mid = line.interpolate(0.5, normalized=True)
        for side in (1.0, -1.0):
            beam = BOAT_BEAM_M * length / BOAT_LENGTH_M
            off = half + beam * 0.5 + 0.35
            try_place(mid.x + dy * off * side, mid.y - dx * off * side, dx, dy, length, seed)
            seed += 1
    for _, line, half in long_piers:
        for s_b in np.arange(6.0, line.length - 5.0, 11.0):
            p = line.interpolate(s_b)
            q = line.interpolate(min(line.length, s_b + 0.5))
            tl = hypot(q.x - p.x, q.y - p.y) or 1.0
            dx, dy = (q.x - p.x) / tl, (q.y - p.y) / tl
            for side in (1.0, -1.0):
                length = 9.0 + ((seed * 7) % 5) * 0.5
                beam = BOAT_BEAM_M * length / BOAT_LENGTH_M
                off = half + beam * 0.5 + 0.35
                try_place(p.x + dy * off * side, p.y - dx * off * side, dx, dy, length, seed)
                seed += 1
    return boats
