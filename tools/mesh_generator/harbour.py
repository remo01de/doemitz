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

from math import atan2, ceil, cos, degrees, hypot, sin

import numpy as np
from shapely import constrained_delaunay_triangles, orient_polygons
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import linemerge, unary_union

from tools.mesh_generator.architecture import _add_quad, _add_triangle
from tools.mesh_generator.locks import build_edge_wall
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


def build_harbour(meshes, scene_layers, water_surfaces, elevation, cfg: dict | None = None, skip_water=(),
                  existing_walls=()):
    """
    Return (report, boat instances, terrain step lines, walkable deck polygons, exclusion polygons). skip_water:
    water polygons that already have walls (lock chambers); existing_walls: OSM wall lines (no quay beside them).
    """
    cfg = cfg or {}
    deck, floats, piles, groyne_m = meshes["PierDeck"], meshes["PierFloat"], meshes["PierPile"], meshes["GroyneStone"]
    piers_report, decks, exclusion = [], [], []
    finger_piers, long_piers = [], []

    def deck_z(x, y):
        lv = _water_level(water_surfaces, x, y)
        if lv is not None:
            return lv + FLOAT_ABOVE_WATER_M, True
        return float(elevation.sample(x, y)) + DECK_ABOVE_GROUND_M, False

    for feature in sorted(scene_layers.get("piers", []), key=lambda f: f["id"]):
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
            width = float(props.get("width", 0) or 0) or (2.0 if line.length >= 25.0 else 1.2)
            half = width * 0.5
            n = max(2, int(ceil(line.length / 1.0)) + 1)
            stations = [line.interpolate(i / (n - 1), normalized=True) for i in range(n)]
            zs, wet = [], []
            for p in stations:
                z, fl = deck_z(p.x, p.y)
                zs.append(z)
                wet.append(fl)
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
            # end caps
            for i, sgn in ((0, -1.0), (n - 1, 1.0)):
                p = stations[i]
                q = stations[1] if i == 0 else stations[-2]
                tx, ty = (p.x - q.x), (p.y - q.y)
                tl = hypot(tx, ty) or 1.0
                nx, ny = ty / tl, -tx / tl
                _faces(floats, [orient([(p.x + nx * half, p.y + ny * half, zs[i] - 0.4),
                                        (p.x - nx * half, p.y - ny * half, zs[i] - 0.4),
                                        (p.x - nx * half, p.y - ny * half, zs[i]),
                                        (p.x + nx * half, p.y + ny * half, zs[i])], (tx / tl, ty / tl, 0.0))])
            decks.append((line.buffer(half, cap_style="flat"), float(np.median(zs))))
            exclusion.append(line.buffer(half + 1.0))
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

    moorings = 0
    for feature in scene_layers.get("moorings", []):
        p = shape(feature["geometry"])
        lv = _water_level(water_surfaces, p.x, p.y)
        z0 = (lv if lv is not None else float(elevation.sample(p.x, p.y))) - 1.2
        _add_pile(piles, p.x, p.y, z0, z0 + 3.1)
        moorings += 1

    # quay walls: water edges within 30 m of the jetties where the bank stands >= 1.2 m above the water
    steps, quays = [], []
    jetty_zone = unary_union([d.buffer(30.0) for d, _ in decks]) if decks else None
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
            for k, piece in enumerate(getattr(pieces, "geoms", [pieces])):
                if piece.geom_type != "LineString" or piece.length < 6.0:
                    continue
                # keep stretches where the bank is high; split at low stretches (slipways, beaches)
                for j, stretch in enumerate(_high_bank_stretches(piece, poly, level, elevation, 1.2)):
                    step, top = build_edge_wall(meshes, stretch, poly, level - 1.0, level, elevation,
                                                f"quay:{len(quays)}", cfg=cfg, railing=False, bank_search=(1.0, 2.5))
                    steps.append(step)
                    quays.append({"length_m": round(stretch.length, 2), "top_z_m": [round(float(top.min()), 3),
                                                                                    round(float(top.max()), 3)]})

    boats = _place_boats(finger_piers, long_piers, decks, water_surfaces, cfg)
    report = {
        "piers": piers_report,
        "jetties": sum(1 for p in piers_report if p["kind"] == "jetty"),
        "platforms": sum(1 for p in piers_report if p["kind"] == "platform"),
        "groynes": sum(1 for p in piers_report if p["kind"] in ("groyne", "breakwater")),
        "mooring_piles": moorings,
        "quay_walls": quays,
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
