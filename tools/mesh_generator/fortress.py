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

from tools.mesh_generator.architecture import _add_box_on_wall, _add_quad


FORTRESS_PALETTE = {
    "FortressWalls": (0.56, 0.23, 0.15),
    "FortressCoping": (0.60, 0.44, 0.36),
    "FortressDark": (0.05, 0.04, 0.04),
}
FORTRESS_MATERIALS = {"FortressWalls": "WallsBrick", "FortressCoping": "StoneTrim"}
FORTRESS_COLLISION_MESHES = {"FortressWalls", "FortressCoping"}
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


def build_fortress_wall(meshes, outline: Polygon, cfg: dict, elevation, water_polygons, crossings, road_z_fn=None):
    """
    Add the escarp to meshes and return (report, profile). crossings: list of (Point, gap_width_m, label, approach)
    where approach is an optional (LineString, half_width_m) road segment inside the fortress that gets brick
    cheek walls up to the next tunnel portal.
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

    # Stations along the ring (every edge densified, corners kept)
    st_xy, st_s, st_edge = [], [], []
    cursor = 0.0
    for idx, (a, b) in enumerate(zip(coords, coords[1:])):
        seg = hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-6:
            continue
        n = max(1, int(ceil(seg / STATION_STEP_M)))
        for k in range(n):
            t = k / n
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
            if in_gap(s_here) or in_gap(s_here - 1.0) or in_gap(s_here + 1.0):
                continue
            z_f = float(np.interp(s_here, s_closed, foot_closed))
            z_t = float(np.interp(s_here, s_closed, top_closed))
            z0 = max(z_f + emb_above_foot, z_t - cordon_below - 2.6)
            if z0 + 0.6 > z_t - cordon_below - 0.3:
                continue
            _add_box_on_wall(dark, a[0], a[1], tx, ty, nx, ny, u - 0.25, u + 0.25, z0, z0 + 0.6, 0.0, 0.015)

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
    corridors = []  # (polygon, floor z) where the terrain is cut out along walled approaches
    for pt, width, label, approach in crossings:
        if approach is None:
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
    )
    return report, profile
