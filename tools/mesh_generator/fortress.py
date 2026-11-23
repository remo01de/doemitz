"""Brick escarp (Festungsmauer) along the fortress outline, configured in doemitz-altstadt-landmarks.json.

The OSM outline osm:way:42318561 (historic=castle) is the outer face of the rampart, exactly on the inner edge
of the moat. DGM1 is bare earth and models the revetment as a steep grass slope; this module puts a vertical
brick wall on the outline from below the moat water level up to the rampart crest, with a brick coping, a
cordon below the crest and small embrasures in the short flanks (after the reference photos). Openings are
left where configured roads or tunnels cross the outline (drawbridge/gate, NW-Steg tunnel portal).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot

import numpy as np
from shapely import orient_polygons
from shapely.geometry import LineString, Point, Polygon

from tools.mesh_generator.architecture import _add_box_on_wall, _add_quad, _add_triangle
from tools.mesh_generator.solids import Profile, arch_curve, arched_face, beam, disc, frame_box, frame_point, orient, ring_quads


FORTRESS_PALETTE = {
    "FortressWalls": (0.56, 0.23, 0.15),
    "FortressCoping": (0.60, 0.44, 0.36),
    "FortressDark": (0.05, 0.04, 0.04),
    "FortressSandstone": (0.52, 0.33, 0.15),
    "FortressSteel": (0.20, 0.21, 0.23),
}
FORTRESS_MATERIALS = {"FortressWalls": "WallsBrick", "FortressCoping": "StoneTrim"}
FORTRESS_COLLISION_MESHES = {"FortressWalls", "FortressCoping", "FortressSandstone"}
STATION_STEP_M = 2.0


@dataclass
class FortressWallProfile:
    """Wall crest along the outline, used by the terrain generator to fill the rampart behind the wall."""
    outline: Polygon
    ring: LineString
    s_vals: np.ndarray
    top_z: np.ndarray
    fill_band_m: float
    foot_z: np.ndarray = None
    gaps: list = None  # (s0, s1) ranges along the ring without wall
    corridors: list = None  # (polygon, floor z) walled approach cuts
    flat_zones: list = None  # (polygon, z) courts inside the outline kept level (gate forecourt)

    def flat_z(self, x: float, y: float):
        for poly, z in self.flat_zones or []:
            if poly.covers(Point(x, y)):
                return z
        return None

    def top_at(self, x: float, y: float) -> float:
        s = self.ring.project(Point(x, y))
        return float(np.interp(s, self.s_vals, self.top_z))

    def in_gap(self, x: float, y: float) -> bool:
        s = self.ring.project(Point(x, y))
        length = self.ring.length
        for g0, g1 in self.gaps or []:
            for off in (0.0, length, -length):
                if g0 + off - 0.3 <= s <= g1 + off + 0.3:
                    return True
        return False


def _cyclic_moving_average(values: np.ndarray, s_vals: np.ndarray, length: float, window: float) -> np.ndarray:
    out = np.empty_like(values)
    half = 0.5 * window
    for i, s in enumerate(s_vals):
        d = np.abs(s_vals - s)
        d = np.minimum(d, length - d)
        out[i] = float(np.mean(values[d <= half]))
    return out


def _quad_facing(mesh, quad, want_up=None, want_dir=None):
    """Add a quad, flipping its winding so the normal points up/down (want_up) or along want_dir (x, y)."""
    (x0, y0, z0), (x1, y1, z1), _, (x3, y3, z3) = quad
    ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
    vx, vy, vz = x3 - x0, y3 - y0, z3 - z0
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    flip = False
    if want_up is not None:
        flip = (nz < 0) == want_up
    elif want_dir is not None:
        flip = (nx * want_dir[0] + ny * want_dir[1]) < 0
    _add_quad(mesh, *(quad if not flip else [quad[1], quad[0], quad[3], quad[2]]))


def _add_mesh_quads(mesh, quads):
    for q in quads:
        if len(q) == 3:
            _add_triangle(mesh, *q)
        else:
            _add_quad(mesh, *q)


def _add_gatehouse(meshes, ring, length, pt, s_closed, foot_closed, cfg, road_z_fn, elevation):
    """
    Brick gate front at the drawbridge (reference photos Torbau/Zugbruecke): a round arch between two piers with
    oculi and light stone panels, a cambered brick attic with stone cornice and coping, a sandstone base down to
    the moat floor and the two drawbridge beams with their chains. No roof: the gate front is an open portal.
    """
    walls, coping = meshes["FortressWalls"], meshes["FortressCoping"]
    sand, steel = meshes["FortressSandstone"], meshes["FortressSteel"]
    s_c = ring.project(pt)
    pa, pb = ring.interpolate((s_c - 0.5) % length), ring.interpolate((s_c + 0.5) % length)
    tx, ty = pb.x - pa.x, pb.y - pa.y
    tl = hypot(tx, ty) or 1.0
    t = (tx / tl, ty / tl)
    n = (t[1], -t[0])  # outward (into the moat)
    oc = ring.interpolate(s_c)
    o = (oc.x, oc.y)
    road_z = road_z_fn(pt.x, pt.y) if road_z_fn else float(elevation.sample(pt.x, pt.y))
    a = float(cfg.get("opening_width_m", 3.3)) * 0.5
    crown = road_z + float(cfg.get("opening_height_m", 4.1))
    spring = crown - a
    pw = float(cfg.get("pier_width_m", 1.45))
    front = float(cfg.get("front_m", 0.35))
    back = -float(cfg.get("depth_m", 1.3)) + front
    w2 = a + pw
    z_e = road_z + float(cfg.get("attic_height_m", 5.0))
    z_m = road_z + float(cfg.get("attic_crown_m", 5.7))
    foot = min(float(np.interp((s_c + d) % length, s_closed, foot_closed)) for d in (-w2, 0.0, w2))
    z_base = road_z - 0.35
    prof = Profile([(-w2, z_e), (-w2 + 0.55, z_e), (-a * 0.7, z_e + 0.28), (-0.5, z_m),
                    (0.5, z_m), (a * 0.7, z_e + 0.28), (w2 - 0.55, z_e), (w2, z_e)])
    arch = arch_curve(a, spring, a, 12)
    out3, in3 = (n[0], n[1], 0.0), (-n[0], -n[1], 0.0)

    def P(u, off, z):
        return frame_point(o, t, n, u, off, z)

    # brick front and back faces with the arched opening; the sandstone base carries the piers
    _add_mesh_quads(walls, arched_face(o, t, n, front, -w2, w2, z_base, prof, arch, out3))
    _add_mesh_quads(walls, arched_face(o, t, n, back, -w2, w2, z_base, prof, arch, in3))
    for u_side, d in ((-w2, (-t[0], -t[1], 0.0)), (w2, (t[0], t[1], 0.0))):
        _add_mesh_quads(walls, [orient([P(u_side, back, z_base), P(u_side, front, z_base),
                                        P(u_side, front, z_e), P(u_side, back, z_e)], d)])
    for u_jamb, d in ((-a, (t[0], t[1], 0.0)), (a, (-t[0], -t[1], 0.0))):
        _add_mesh_quads(walls, [orient([P(u_jamb, back, road_z - 0.55), P(u_jamb, front, road_z - 0.55),
                                        P(u_jamb, front, spring), P(u_jamb, back, spring)], d)])
    for (ua, za), (ub, zb) in zip(arch, arch[1:]):
        um, zm = 0.5 * (ua + ub), 0.5 * (za + zb)
        toward = (-(t[0] * um), -(t[1] * um), spring - zm)
        _add_mesh_quads(walls, [orient([P(ua, front, za), P(ub, front, zb), P(ub, back, zb), P(ua, back, za)], toward)])
    pts = prof.points
    cf, cb = front + 0.1, back - 0.1
    for (ua, za), (ub, zb) in zip(pts, pts[1:]):
        _add_mesh_quads(walls, [orient([P(ua, front, za), P(ub, front, zb), P(ub, back, zb), P(ua, back, za)], (0, 0, 1))])
        # stone cornice band below the attic edge and a coping slab on top (both follow the cambered line)
        z0, z1, zb0, zb1 = za - 0.42, za - 0.22, zb - 0.42, zb - 0.22
        n0, n1 = front, front + 0.12
        _add_mesh_quads(coping, [
            orient([P(ua, n1, z0), P(ub, n1, zb0), P(ub, n1, zb1), P(ua, n1, z1)], out3),
            orient([P(ua, n0, z1), P(ub, n0, zb1), P(ub, n1, zb1), P(ua, n1, z1)], (0, 0, 1)),
            orient([P(ua, n0, z0), P(ub, n0, zb0), P(ub, n1, zb0), P(ua, n1, z0)], (0, 0, -1)),
            orient([P(ua, cf, za + 0.14), P(ub, cf, zb + 0.14), P(ub, cb, zb + 0.14), P(ua, cb, za + 0.14)], (0, 0, 1)),
            orient([P(ua, cf, za - 0.02), P(ub, cf, zb - 0.02), P(ub, cf, zb + 0.14), P(ua, cf, za + 0.14)], out3),
            orient([P(ua, cb, za - 0.02), P(ub, cb, zb - 0.02), P(ub, cb, zb + 0.14), P(ua, cb, za + 0.14)], in3),
        ])
    for u_end, d in ((-w2 - 0.1, (-t[0], -t[1], 0.0)), (w2 + 0.1, (t[0], t[1], 0.0))):
        _add_mesh_quads(coping, [orient([P(u_end, cb, z_e - 0.02), P(u_end, cf, z_e - 0.02),
                                         P(u_end, cf, z_e + 0.14), P(u_end, cb, z_e + 0.14)], d)])
    # brick archivolt ring proud of the front, stone keystone and impost blocks
    ring_out = [(u * (a + 0.32) / a, spring + (z - spring) * (a + 0.32) / a) for u, z in arch]
    nf = front + 0.06
    for (ua, za), (ub, zb), (uc, zc), (ud, zd) in zip(arch, arch[1:], ring_out[1:], ring_out):
        _add_mesh_quads(walls, [
            orient([P(ua, nf, za), P(ub, nf, zb), P(uc, nf, zc), P(ud, nf, zd)], out3),
            orient([P(ud, front, zd), P(uc, front, zc), P(uc, nf, zc), P(ud, nf, zd)],
                   (t[0] * (ud + uc) * 0.5, t[1] * (ud + uc) * 0.5, 0.5 * (zd + zc) - spring)),
        ])
    _add_mesh_quads(coping, frame_box(o, t, n, -0.2, 0.2, front, front + 0.12, crown - 0.08, crown + 0.42))
    for u0 in (-a - 0.3, a):
        _add_mesh_quads(coping, frame_box(o, t, n, u0, u0 + 0.3, front, front + 0.09, spring - 0.22, spring))
    # oculi and recessed light stone panels on the piers
    for u_p in (-(a + pw * 0.5), a + pw * 0.5):
        _add_mesh_quads(sand, disc(P(u_p, front + 0.02, road_z + 4.35), n, 0.30, 12))
        _add_mesh_quads(walls, ring_quads(P(u_p, front + 0.05, road_z + 4.35), n, 0.30, 0.44, 12))
        _add_mesh_quads(sand, frame_box(o, t, n, u_p - 0.26, u_p + 0.26, front, front + 0.03, road_z + 0.7, road_z + 2.35))
    # sandstone base: piers down to the moat floor and a sill block under the bridge deck end
    for u0, u1 in ((-w2 - 0.06, -a), (a, w2 + 0.06)):
        _add_mesh_quads(sand, frame_box(o, t, n, u0, u1, back - 0.06, front + 0.06, foot, z_base))
    _add_mesh_quads(sand, frame_box(o, t, n, -a, a, back - 0.06, front + 0.06, foot, road_z - 0.55))
    # drawbridge beams and chains (steel), leaning from the piers over the bridge deck
    for side in (-1.0, 1.0):
        top_p = P(side * (a + 0.25), front + 0.08, road_z + 3.3)
        low_p = P(side * (a - 0.12), front + 2.6, road_z + 1.05)
        _add_mesh_quads(steel, beam(top_p, low_p, 0.14, 0.16))
        _add_mesh_quads(steel, beam(low_p, P(side * (a + 0.36), front + 0.05, road_z + 4.05), 0.05, 0.05))
    return {
        "style": "brick_round_arch_oculi",
        "opening_width_m": round(2 * a, 2),
        "opening_height_m": round(crown - road_z, 2),
        "width_m": round(2 * w2, 2),
        "top_z_m": round(z_m + 0.14, 3),
        "road_z_m": round(road_z, 3),
    }


def _forecourt_ranges(ring, length, forecourts, crossings, road_z_fn, elevation, parapet_h):
    """Ring s-ranges bordering a gate forecourt: (s0, s1, court level, parapet top)."""
    ranges = []
    for poly in forecourts or []:
        shared = ring.intersection(poly.buffer(0.05))
        parts = [g for g in getattr(shared, "geoms", [shared]) if g.geom_type == "LineString" and g.length > 1.0]
        if not parts:
            continue
        ss = sorted(ring.project(Point(c)) for g in parts for c in (g.coords[0], g.coords[-1]))
        s0, s1 = ss[0], ss[-1]
        if s1 - s0 > 0.5 * length:
            continue
        level = None
        for pt, _, _, _ in crossings:
            if s0 <= ring.project(pt) <= s1:
                level = road_z_fn(pt.x, pt.y) if road_z_fn else float(elevation.sample(pt.x, pt.y))
        if level is None:
            c = poly.representative_point()
            level = float(elevation.sample(c.x, c.y))
        ranges.append((s0, s1, level, level + parapet_h, poly))
    return ranges


def build_fortress_wall(meshes, outline: Polygon, cfg: dict, elevation, water_polygons, crossings, road_z_fn=None,
                        forecourts=None):
    """
    Add the escarp to meshes and return (report, profile). crossings: list of (Point, gap_width_m, label, approach)
    where approach is an optional (LineString, half_width_m) road segment inside the fortress that gets brick
    cheek walls up to the next tunnel portal. forecourts: small courts cut off inside the outline by a gate wall;
    along them the escarp is a low, level loophole parapet on a sandstone base (reference photos Torvorhof).
    """
    outline = orient_polygons(outline)
    coords = list(outline.exterior.coords)
    ring = LineString(coords)
    length = ring.length
    foot_below_water = float(cfg.get("foot_below_water_m", 0.6))
    search = cfg.get("crest_search_inside_m", [1.5, 7.0])
    smoothing = float(cfg.get("crest_smoothing_m", 10.0))
    min_h = float(cfg.get("min_height_m", 2.5))
    coping_d = float(cfg.get("coping_depth_m", 0.9))
    coping_h = float(cfg.get("coping_height_m", 0.25))
    cordon_below = float(cfg.get("cordon_below_top_m", 0.9))
    cordon_h = float(cfg.get("cordon_height_m", 0.22))
    cordon_p = float(cfg.get("cordon_protrusion_m", 0.12))
    emb_spacing = float(cfg.get("embrasure_spacing_m", 7.0))
    emb_max_edge = float(cfg.get("embrasure_max_edge_m", 25.0))
    emb_above_foot = float(cfg.get("embrasure_height_above_foot_m", 2.4))
    plinth_h = float(cfg.get("stone_plinth_height_m", 0.0))
    plinth_scope = str(cfg.get("stone_plinth_scope", "all"))
    cheek_walls = bool(cfg.get("approach_cheek_walls", True))
    gatehouse = cfg.get("gatehouse") or {}
    fc_cfg = cfg.get("forecourt_parapet") or {}
    parapet_h = float(fc_cfg.get("height_m", 2.3))
    parapet_t = float(fc_cfg.get("thickness_m", 0.6))
    lh_spacing = float(fc_cfg.get("loophole_spacing_m", 1.5))
    lh_z = float(fc_cfg.get("loophole_height_m", 1.2))
    lh_w, lh_h = (float(v) for v in fc_cfg.get("loophole_size_m", [0.16, 0.32]))
    fc_full = _forecourt_ranges(ring, length, forecourts, crossings, road_z_fn, elevation, parapet_h)
    fc_ranges = [r[:4] for r in fc_full]
    fc_breaks = sorted({b for s0, s1, _, _ in fc_ranges for b in (s0 - 0.02, s0 + 0.02, s1 - 0.02, s1 + 0.02)})

    def fc_at(s):
        for s0, s1, lvl, ptop in fc_ranges:
            if s0 + 0.01 <= s <= s1 - 0.01:
                return lvl, ptop
        return None

    # Stations along the ring (every edge densified, corners kept)
    st_xy, st_s, st_edge = [], [], []
    cursor = 0.0
    for idx, (a, b) in enumerate(zip(coords, coords[1:])):
        seg = hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-6:
            continue
        n = max(1, int(ceil(seg / STATION_STEP_M)))
        ts = sorted({k / n for k in range(n)} | {(bs - cursor) / seg for bs in fc_breaks if cursor < bs < cursor + seg})
        for t in ts:
            st_xy.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            st_s.append(cursor + seg * t)
            st_edge.append(idx)
        cursor += seg
    s_arr = np.asarray(st_s, dtype=np.float64)

    def inward_normal(idx):
        a, b = coords[idx], coords[idx + 1]
        seg = hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        tx, ty = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        return (-ty, tx)

    crest_raw = np.empty(len(st_xy))
    foot = np.empty(len(st_xy))
    for i, ((x, y), idx) in enumerate(zip(st_xy, st_edge)):
        nx, ny = inward_normal(idx)
        ds = np.arange(float(search[0]), float(search[1]) + 1e-6, 0.5)
        crest_raw[i] = float(np.max(elevation.sample_array(x + nx * ds, y + ny * ds)))
        out_pt = Point(x - nx * 2.0, y - ny * 2.0)
        level = next((lvl for poly, lvl in water_polygons if poly.buffer(0.5).contains(out_pt)), None)
        if level is not None:
            foot[i] = level - foot_below_water
        else:
            outs = np.arange(1.0, 4.01, 0.5)
            foot[i] = float(np.min(elevation.sample_array(x - nx * outs, y - ny * outs))) - 0.3
    crest = _cyclic_moving_average(crest_raw, s_arr, length, smoothing)
    top = np.maximum(crest, foot + min_h)
    for i, s_i in enumerate(s_arr):
        hit = fc_at(float(s_i))
        if hit is not None:
            top[i] = hit[1]

    # Gaps at crossings
    gaps = []
    for pt, width, label, _ in crossings:
        s_c = ring.project(pt)
        gaps.append((s_c - width * 0.5, s_c + width * 0.5, label, width))

    def in_gap(s):
        for g0, g1, _, _ in gaps:
            for off in (0.0, length, -length):
                if g0 + off <= s <= g1 + off:
                    return True
        return False

    walls = meshes["FortressWalls"]
    coping = meshes["FortressCoping"]
    dark = meshes["FortressDark"]
    built = 0.0
    s_closed = np.append(s_arr, length)
    top_closed = np.append(top, top[0])
    foot_closed = np.append(foot, foot[0])
    for i in range(len(st_xy)):
        sa, sb = s_closed[i], s_closed[i + 1]
        idx = st_edge[i]
        a, b = coords[idx], coords[idx + 1]
        seg_len = hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        tx, ty = (b[0] - a[0]) / seg_len, (b[1] - a[1]) / seg_len
        nx, ny = ty, -tx  # outward
        # Split the station segment at gap borders
        cuts = [sa, sb]
        for g0, g1, _, _ in gaps:
            for gb in (g0, g1):
                for off in (0.0, length, -length):
                    if sa < gb + off < sb:
                        cuts.append(gb + off)
        cuts.sort()
        for c0, c1 in zip(cuts, cuts[1:]):
            mid = 0.5 * (c0 + c1)
            if c1 - c0 < 1e-3 or in_gap(mid):
                continue
            pa = ring.interpolate(c0 % length)
            pb = ring.interpolate(c1 % length if c1 < length else length - 1e-9)
            pa, pb = (pa.x, pa.y), (pb.x, pb.y)
            za_t = float(np.interp(c0, s_closed, top_closed))
            zb_t = float(np.interp(c1, s_closed, top_closed))
            za_f = float(np.interp(c0, s_closed, foot_closed))
            zb_f = float(np.interp(c1, s_closed, foot_closed))
            built += c1 - c0

            def off(p, d):
                return (p[0] + nx * d, p[1] + ny * d)

            # outer brick face
            _add_quad(walls, (*pa, za_f), (*pb, zb_f), (*pb, zb_t), (*pa, za_t))
            fc = fc_at(c0 + 1e-3) if fc_at(c1 - 1e-3) is not None else None
            if fc is not None:
                # Forecourt parapet: level brick wall with inner face, flat stone coping and a sandstone base
                lvl = fc[0]
                qa, qb = off(pa, 0.05), off(pb, 0.05)
                # sandstone base course about 1.3 m above the moat water, brick above (reference photo Torvorhof)
                z_pl = min(lvl - 0.3, min(za_f, zb_f) + foot_below_water + 1.3)
                _add_quad(meshes["FortressSandstone"], (*qa, za_f), (*qb, zb_f), (*qb, z_pl), (*qa, z_pl))
                _add_quad(meshes["FortressSandstone"], (*qa, z_pl), (*qb, z_pl), (*pb, z_pl), (*pa, z_pl))
                ia, ib = off(pa, -parapet_t), off(pb, -parapet_t)
                _add_quad(walls, (*ib, lvl - 0.6), (*ia, lvl - 0.6), (*ia, za_t), (*ib, zb_t))
                fa, fb = off(pa, 0.08), off(pb, 0.08)
                ka, kb = off(pa, -parapet_t - 0.08), off(pb, -parapet_t - 0.08)
                _add_quad(coping, (*fa, za_t - 0.02), (*fb, zb_t - 0.02), (*fb, zb_t + 0.12), (*fa, za_t + 0.12))
                _add_quad(coping, (*fa, za_t + 0.12), (*fb, zb_t + 0.12), (*kb, zb_t + 0.12), (*ka, za_t + 0.12))
                _add_quad(coping, (*kb, zb_t - 0.02), (*ka, za_t - 0.02), (*ka, za_t + 0.12), (*kb, zb_t + 0.12))
                continue
            # grey stone plinth course from the foot to above the moat water (reference photo Zugbrücke)
            if plinth_h > 0.0 and plinth_scope == "all":
                qa, qb = off(pa, 0.04), off(pb, 0.04)
                za_p = min(za_t - 1.0, za_f + foot_below_water + plinth_h)
                zb_p = min(zb_t - 1.0, zb_f + foot_below_water + plinth_h)
                _add_quad(coping, (*qa, za_f), (*qb, zb_f), (*qb, zb_p), (*qa, za_p))
                _add_quad(coping, (*qa, za_p), (*qb, zb_p), (*pb, zb_p), (*pa, za_p))
            # coping: front lip, top, back face (hides the terrain fill edge)
            fa, fb = off(pa, 0.06), off(pb, 0.06)
            ia, ib = off(pa, -coping_d), off(pb, -coping_d)
            _add_quad(coping, (*fa, za_t - 0.02), (*fb, zb_t - 0.02), (*fb, zb_t + coping_h), (*fa, za_t + coping_h))
            _add_quad(coping, (*fa, za_t + coping_h), (*fb, zb_t + coping_h), (*ib, zb_t + coping_h), (*ia, za_t + coping_h))
            _add_quad(coping, (*ib, zb_t - 0.3), (*ia, za_t - 0.3), (*ia, za_t + coping_h), (*ib, zb_t + coping_h))
            # cordon band below the crest
            ca, cb = off(pa, cordon_p), off(pb, cordon_p)
            za_c0, zb_c0 = za_t - cordon_below - cordon_h, zb_t - cordon_below - cordon_h
            za_c1, zb_c1 = za_t - cordon_below, zb_t - cordon_below
            _add_quad(coping, (*ca, za_c0), (*cb, zb_c0), (*cb, zb_c1), (*ca, za_c1))
            _add_quad(coping, (*ca, za_c1), (*cb, zb_c1), (*pb, zb_c1), (*pa, za_c1))
            _add_quad(coping, (*pa, za_c0), (*pb, zb_c0), (*cb, zb_c0), (*ca, za_c0))


    for idx, (a, b) in enumerate(zip(coords, coords[1:])):
        seg = hypot(b[0] - a[0], b[1] - a[1])
        if seg < 6.0 or seg > emb_max_edge:
            continue
        tx, ty = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        nx, ny = ty, -tx
        count = max(1, int(seg // emb_spacing))
        s_edge0 = ring.project(Point(a))
        for k in range(count):
            u = seg * (k + 0.5) / count
            s_here = s_edge0 + u
            if in_gap(s_here) or in_gap(s_here - 1.0) or in_gap(s_here + 1.0) or fc_at(s_here) is not None:
                continue
            z_f = float(np.interp(s_here, s_closed, foot_closed))
            z_t = float(np.interp(s_here, s_closed, top_closed))
            z0 = max(z_f + emb_above_foot, z_t - cordon_below - 2.6)
            if z0 + 0.6 > z_t - cordon_below - 0.3:
                continue
            _add_box_on_wall(dark, a[0], a[1], tx, ty, nx, ny, u - 0.25, u + 0.25, z0, z0 + 0.6, 0.0, 0.015)

    # Loopholes in the forecourt parapet (outside and court side) and the end faces of the tall escarp where it
    # rises above the parapet at both ends of the forecourt
    loopholes = 0
    gate_s = [ring.project(pt) for pt, _, _, approach in crossings if approach is not None]
    gate_half = (float(gatehouse.get("opening_width_m", 3.3)) * 0.5 + float(gatehouse.get("pier_width_m", 1.45))
                 if gatehouse else 0.0)
    for s0, s1, lvl, ptop in fc_ranges:
        k = 0
        s_l = s0 + 0.9
        while s_l <= s1 - 0.9:
            if not in_gap(s_l) and all(abs(s_l - g) > gate_half + 0.45 for g in gate_s):
                p = ring.interpolate(s_l)
                q = ring.interpolate(min(s_l + 0.05, length))
                tx, ty = q.x - p.x, q.y - p.y
                tl = hypot(tx, ty) or 1.0
                tt = (tx / tl, ty / tl)
                nn = (tt[1], -tt[0])
                z0 = lvl + lh_z
                _add_mesh_quads(dark, frame_box((p.x, p.y), tt, nn, -lh_w / 2, lh_w / 2, -0.01, 0.015, z0, z0 + lh_h,
                                                faces={"side2"}))
                _add_mesh_quads(dark, frame_box((p.x, p.y), tt, nn, -lh_w / 2, lh_w / 2, -parapet_t - 0.015,
                                                -parapet_t + 0.01, z0, z0 + lh_h, faces={"side0"}))
                loopholes += 1
            k += 1
            s_l = s0 + 0.9 + k * lh_spacing
        for s_j, sign in ((s0, 1.0), (s1, -1.0)):
            p = ring.interpolate(s_j % length)
            q = ring.interpolate(min((s_j % length) + 0.05, length))
            tx, ty = q.x - p.x, q.y - p.y
            tl = hypot(tx, ty) or 1.0
            tt = (tx / tl, ty / tl)
            nn = (tt[1], -tt[0])
            z_tall = float(np.interp(s_j - sign * 0.1, s_closed, top_closed)) + coping_h
            if z_tall > ptop + 0.2:
                _add_mesh_quads(walls, [orient([frame_point((p.x, p.y), tt, nn, 0.0, 0.06, ptop),
                                                frame_point((p.x, p.y), tt, nn, 0.0, -coping_d, ptop),
                                                frame_point((p.x, p.y), tt, nn, 0.0, -coping_d, z_tall),
                                                frame_point((p.x, p.y), tt, nn, 0.0, 0.06, z_tall)],
                                               (tt[0] * sign, tt[1] * sign, 0.0))])

    # End caps where the wall stops at an opening (faces point into the opening)
    for g0, g1, _, _ in gaps:
        for s_edge, facing in ((g0, 1.0), (g1, -1.0)):
            s_m = s_edge % length
            p = ring.interpolate(s_m)
            q = ring.interpolate(min(length, s_m + 0.05)) if s_m + 0.05 <= length else ring.interpolate(s_m - 0.05)
            tx, ty = q.x - p.x, q.y - p.y
            tl = hypot(tx, ty) or 1.0
            tx, ty = tx / tl, ty / tl
            if s_m + 0.05 > length:
                tx, ty = -tx, -ty
            ix, iy = -ty, tx
            z_t = float(np.interp(s_m, s_closed, top_closed)) + coping_h
            z_f = float(np.interp(s_m, s_closed, foot_closed))
            o = (p.x, p.y)
            i = (p.x + ix * coping_d, p.y + iy * coping_d)
            if facing > 0:
                _add_quad(walls, (*i, z_f), (*o, z_f), (*o, z_t), (*i, z_t))
            else:
                _add_quad(walls, (*o, z_f), (*i, z_f), (*i, z_t), (*o, z_t))

    # Gate cheek walls along approach roads from the gap to the tunnel portal
    cheek_report = []
    gatehouse_report = []
    corridors = []  # (polygon, floor z) where the terrain is cut out along walled approaches
    for pt, width, label, approach in crossings:
        if approach is None:
            continue
        if gatehouse:
            gh = _add_gatehouse(meshes, ring, length, pt, s_closed, foot_closed, gatehouse, road_z_fn, elevation)
            gatehouse_report.append({"crossing": label, **gh})
        if not cheek_walls:
            continue
        line, half_w = approach
        pts = list(line.coords)
        s_gap = ring.project(pt)
        gap_top = float(np.interp(s_gap, s_closed, top_closed))
        if Point(pts[0]).distance(pt) > Point(pts[-1]).distance(pt):
            pts = list(reversed(pts))

        def cheek_top(k, x, y, side_rx, side_ry):
            # level crest at the escarp crest height of the opening; the rampart may rise behind it
            return gap_top

        for side in (-1.0, 1.0):
            for k, ((ax, ay), (bx, by)) in enumerate(zip(pts, pts[1:])):
                seg = hypot(bx - ax, by - ay)
                if seg < 1e-6:
                    continue
                tx, ty = (bx - ax) / seg, (by - ay) / seg
                rx, ry = ty, -tx
                off_m = half_w + 0.25
                pa = (ax + rx * off_m * side, ay + ry * off_m * side)
                pb = (bx + rx * off_m * side, by + ry * off_m * side)
                za_r = road_z_fn(ax, ay) if road_z_fn else float(elevation.sample(ax, ay))
                zb_r = road_z_fn(bx, by) if road_z_fn else float(elevation.sample(bx, by))
                za_t = max(za_r + 2.2, cheek_top(k, ax, ay, rx * side, ry * side))
                zb_t = max(zb_r + 2.2, cheek_top(k + 1, bx, by, rx * side, ry * side))
                # cheek wall face, double-sided (it is seen from the road and from the rampart behind)
                _add_quad(walls, (*pb, zb_r - 0.4), (*pa, za_r - 0.4), (*pa, za_t), (*pb, zb_t))
                _add_quad(walls, (*pa, za_r - 0.4), (*pb, zb_r - 0.4), (*pb, zb_t), (*pa, za_t))
                # stone strip between the carriageway edge and the cheek wall
                ea = (ax + rx * (half_w - 0.05) * side, ay + ry * (half_w - 0.05) * side)
                eb = (bx + rx * (half_w - 0.05) * side, by + ry * (half_w - 0.05) * side)
                strip = [(*ea, za_r + 0.005), (*eb, zb_r + 0.005), (*pb, zb_r + 0.005), (*pa, za_r + 0.005)]
                cross = (strip[1][0] - strip[0][0]) * (strip[3][1] - strip[0][1]) - (strip[1][1] - strip[0][1]) * (strip[3][0] - strip[0][0])
                _add_quad(coping, *(strip if cross > 0 else [strip[1], strip[0], strip[3], strip[2]]))
                ta, tb = (pa[0] + rx * side * 0.6, pa[1] + ry * side * 0.6), (pb[0] + rx * side * 0.6, pb[1] + ry * side * 0.6)
                cap = [(*pa, za_t), (*pb, zb_t), (*tb, zb_t), (*ta, za_t)]
                cross = (cap[1][0] - cap[0][0]) * (cap[3][1] - cap[0][1]) - (cap[1][1] - cap[0][1]) * (cap[3][0] - cap[0][0])
                _add_quad(coping, *(cap if cross > 0 else [cap[1], cap[0], cap[3], cap[2]]))
        floor_min = min((road_z_fn(x, y) if road_z_fn else float(elevation.sample(x, y))) for x, y in pts)
        corridors.append((LineString(pts).buffer(half_w + 0.25 + 1.2, cap_style="flat"), floor_min - 0.08))
        cheek_report.append({"crossing": label, "length_m": round(line.length, 2)})

    heights = top - foot
    report = {
        "id": cfg.get("id", "fortress_wall"),
        "name": cfg.get("name", "Festungsmauer"),
        "outline_id": cfg.get("outline_id", ""),
        "outline_length_m": round(length, 2),
        "built_length_m": round(built, 2),
        "gaps": [{"label": lbl, "width_m": round(w, 2), "s_m": round(0.5 * (g0 + g1), 2)} for g0, g1, lbl, w in gaps],
        "cheek_walls": cheek_report,
        "gatehouses": gatehouse_report,
        "forecourt_parapets": [
            {"s_m": [round(s0, 2), round(s1, 2)], "length_m": round(s1 - s0, 2), "court_z_m": round(lvl, 3),
             "top_z_m": round(ptop, 3), "height_above_court_m": round(ptop - lvl, 2)}
            for s0, s1, lvl, ptop in fc_ranges
        ],
        "forecourt_loopholes": loopholes,
        "stone_plinth_scope": plinth_scope,
        "foot_z_m": [round(float(foot.min()), 3), round(float(foot.max()), 3)],
        "top_z_m": [round(float(top.min()), 3), round(float(top.max()), 3)],
        "height_m": [round(float(heights.min()), 3), round(float(heights.max()), 3)],
        "dimensions_source": cfg.get("dimensions_source", "assumed_sprint13_fortress_wall"),
        "reference_ids": cfg.get("reference_ids", []),
    }
    profile = FortressWallProfile(
        outline=outline, ring=ring, s_vals=s_closed, top_z=top_closed,
        fill_band_m=float(cfg.get("fill_band_m", 4.0)),
        foot_z=foot_closed,
        gaps=[(g0, g1) for g0, g1, _, _ in gaps],
        corridors=corridors,
        # level gate forecourt 10 cm under the bridge/road surface at the gate
        flat_zones=[(r[4], r[2] - 0.1) for r in fc_full],
    )
    return report, profile
