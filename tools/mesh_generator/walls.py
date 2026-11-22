"""Brick walls from OSM barrier=wall ways (fortress gorge and retaining walls, garden walls).

Height comes from the OSM height tag; without it the wall gets an assumed height (free-standing) or the
terrain step it retains. A wall is a retaining wall when the terrain on its two sides differs by at least
RETAINING_STEP_M; then only the low side shows a brick face and the terrain generator fills the high side up
to the crest, lowers the low side to the foot and splits terrain triangles exactly at the wall line (see
terrain.build_terrain_tiles). Openings are left where ways cross the wall; barrier=gate nodes on a
free-standing wall become arched gateways. Per-wall details (crenellations, loopholes, end turrets) are
configured by OSM ID under "walls" in doemitz-altstadt-landmarks.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, cos, hypot, pi, sin

import numpy as np
from shapely.geometry import LineString, Point

from tools.mesh_generator.architecture import _add_quad, _add_triangle

RETAINING_STEP_M = 1.5
STATION_M = 1.5
ASSUMED_FREE_HEIGHT_M = 1.5


@dataclass
class WallStepLine:
    """A retaining wall as a terrain step: high side filled to the crest, low side lowered to the foot."""
    wall_id: str
    line: LineString
    s_vals: np.ndarray
    top_z: np.ndarray
    base_z: np.ndarray
    high_sign: float  # +1: high side to the right of the line direction, -1: to the left
    gaps: list = field(default_factory=list)
    fill_band_m: float = 3.0
    low_band_m: float = 2.5

    def at(self, arr, x, y):
        s = self.line.project(Point(x, y))
        return float(np.interp(s, self.s_vals, arr))

    def side(self, x, y) -> float:
        """+1 high side, -1 low side."""
        s = self.line.project(Point(x, y))
        p = self.line.interpolate(s)
        q = self.line.interpolate(min(self.line.length, s + 0.05)) if s + 0.05 <= self.line.length else self.line.interpolate(s - 0.05)
        dx, dy = q.x - p.x, q.y - p.y
        if s + 0.05 > self.line.length:
            dx, dy = -dx, -dy
        cross = dx * (y - p.y) - dy * (x - p.x)  # >0: left of direction
        right = cross < 0
        return self.high_sign if right else -self.high_sign

    def in_gap(self, x, y, margin=0.3) -> bool:
        s = self.line.project(Point(x, y))
        return any(g0 - margin <= s <= g1 + margin for g0, g1 in self.gaps)


def _smooth(values, s_vals, window):
    out = np.empty_like(values)
    for i, s in enumerate(s_vals):
        out[i] = float(np.mean(values[np.abs(s_vals - s) <= window * 0.5]))
    return out


def _stations(line: LineString):
    n = max(1, int(ceil(line.length / STATION_M)))
    s = np.linspace(0.0, line.length, n + 1)
    pts = [line.interpolate(v) for v in s]
    normals = []
    for v in s:
        a = line.interpolate(max(0.0, v - 0.25))
        b = line.interpolate(min(line.length, v + 0.25))
        dx, dy = b.x - a.x, b.y - a.y
        dl = hypot(dx, dy) or 1.0
        normals.append((dy / dl, -dx / dl))  # right normal
    return s, pts, normals


def build_osm_walls(meshes, walls, details_by_id, elevation, roads, road_width_fn, road_z_fn,
                    built_tunnels, tunnel_portals_cfg, skip_ids=()):
    walls_mesh = meshes["FortressWalls"]
    coping = meshes["FortressCoping"]
    dark = meshes["FortressDark"]
    report = []
    step_lines = []
    exclusion = []
    road_geoms = [(r, LineString(r["geometry"]["coordinates"])) for r in roads if r["geometry"]["type"] == "LineString"]
    for feature in sorted(walls, key=lambda f: f["id"]):
        wid = feature["id"]
        if wid in skip_ids or feature["geometry"]["type"] != "LineString":
            continue
        line = LineString(feature["geometry"]["coordinates"])
        if line.length < 1.0:
            continue
        cfg = details_by_id.get(wid, {})
        tags = feature["properties"]
        try:
            h_tag = float(str(tags.get("height", "")).replace("m", "").strip())
        except ValueError:
            h_tag = None
        s_vals, pts, normals = _stations(line)
        on = np.array([elevation.sample(p.x, p.y) for p in pts])
        ds = np.arange(0.5, 3.01, 0.5)
        right = np.array([float(np.mean(elevation.sample_array(p.x + n[0] * ds, p.y + n[1] * ds))) for p, n in zip(pts, normals)])
        left = np.array([float(np.mean(elevation.sample_array(p.x - n[0] * ds, p.y - n[1] * ds))) for p, n in zip(pts, normals)])
        step = float(np.mean(right) - np.mean(left))
        retaining = abs(step) >= RETAINING_STEP_M and not cfg.get("free_standing", False)
        high_sign = 1.0 if step > 0 else -1.0
        if retaining:
            low_min = np.array([
                float(np.min(elevation.sample_array(p.x - high_sign * n[0] * ds, p.y - high_sign * n[1] * ds)))
                for p, n in zip(pts, normals)
            ])
            base = _smooth(low_min, s_vals, 6.0) - 0.2
            if h_tag is not None:
                top = base + 0.2 + h_tag
                source = "osm_height_on_low_side"
            else:
                high_max = np.array([
                    float(np.max(elevation.sample_array(p.x + high_sign * n[0] * ds, p.y + high_sign * n[1] * ds)))
                    for p, n in zip(pts, normals)
                ])
                top = _smooth(high_max, s_vals, 6.0)
                source = "assumed_terrain_step_crest"
            top = np.maximum(top, base + 1.0)
        else:
            h = h_tag if h_tag is not None else float(cfg.get("assumed_height_m", ASSUMED_FREE_HEIGHT_M))
            source = "osm_height" if h_tag is not None else "assumed_default_free_wall_height"
            ground = _smooth(on, s_vals, 4.0)
            if h >= 3.0:
                # ends of gorge walls sit on the escarp crest; DGM1 there reads the moat slope
                ground = np.maximum(ground, float(np.median(ground)) - 1.0)
            base = ground - 0.3
            if h >= 3.0:
                top = np.full_like(ground, float(np.median(ground)) + h)  # level crest for tall walls
            else:
                top = ground + h
        height_eff = float(np.max(top - base))
        thick = float(cfg.get("thickness_m", 0.6 if height_eff >= 3.0 else 0.4))

        # Openings: crossing ways (built tunnels only), gate nodes
        gaps = []  # (s0, s1, kind, opening_height or None, label)
        for road, rg in road_geoms:
            rtags = road["properties"]
            if rtags.get("tunnel", "no") != "no" and road["id"] not in built_tunnels:
                continue
            if not rg.intersects(line):
                continue
            inter = rg.intersection(line)
            for ip in getattr(inter, "geoms", [inter]):
                if ip.geom_type != "Point":
                    continue
                s_c = line.project(ip)
                width = road_width_fn(rtags)[0] + 0.6
                portal_near = None
                for tid, tun in built_tunnels.items():
                    for end in (tun.coords[0], tun.coords[-1]):
                        if Point(end).distance(ip) < 5.0:
                            portal_near = tid
                if portal_near:
                    width = max(width, float(tunnel_portals_cfg.get(portal_near, {}).get("portal_wall_width_m", width)))
                gaps.append([s_c - width * 0.5, s_c + width * 0.5, "crossing", None, road["id"]])
        for gate in feature.get("gates", []):
            gp = Point(gate["position_m"])
            s_g = line.project(gp)
            hit = next((g for g in gaps if g[0] - 1.0 <= s_g <= g[1] + 1.0), None)
            arch_h = float(cfg.get("gate_opening_height_m", 3.0))
            if hit is None:
                w = float(cfg.get("gate_opening_width_m", 2.4))
                gaps.append([s_g - w * 0.5, s_g + w * 0.5, "gate", arch_h, gate["id"]])
            elif not retaining and height_eff >= arch_h + 0.8 and (hit[1] - hit[0]) <= 4.0:
                hit[2], hit[3], hit[4] = "gate", arch_h, f"{hit[4]},{gate['id']}"
        gaps.sort(key=lambda g: g[0])
        merged = []
        for g in gaps:
            if merged and g[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], g[1])
                merged[-1][4] += "," + g[4]
            else:
                merged.append(list(g))
        gaps = merged

        def zt(s):
            return float(np.interp(s, s_vals, top))

        def zb(s):
            return float(np.interp(s, s_vals, base))

        def pt_at(s, off):
            p = line.interpolate(max(0.0, min(line.length, s)))
            a = line.interpolate(max(0.0, s - 0.25))
            b = line.interpolate(min(line.length, s + 0.25))
            dx, dy = b.x - a.x, b.y - a.y
            dl = hypot(dx, dy) or 1.0
            return (p.x + dy / dl * off, p.y - dx / dl * off)

        # face offsets: free-standing walls have both faces, retaining walls show only the low side
        faces = [(+thick * 0.5, +1.0), (-thick * 0.5, -1.0)] if not retaining else [(0.0, -high_sign)]

        def wall_quad(mesh, s0, s1, off, facing, z0a, z0b, z1a, z1b):
            a, b = pt_at(s0, off), pt_at(s1, off)
            if facing > 0:  # face to the right of the line direction
                _add_quad(mesh, (*a, z0a), (*b, z0b), (*b, z1b), (*a, z1a))
            else:
                _add_quad(mesh, (*b, z0b), (*a, z0a), (*a, z1a), (*b, z1b))

        # Solid spans between openings, sampled at the stations
        bounds = [0.0]
        for g in gaps:
            bounds += [max(0.0, g[0]), min(line.length, g[1])]
        bounds.append(line.length)
        spans = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds), 2) if bounds[i + 1] - bounds[i] > 0.05]
        built = 0.0
        for s0, s1 in spans:
            built += s1 - s0
            cuts = [s0] + [v for v in s_vals if s0 < v < s1] + [s1]
            for a_s, b_s in zip(cuts, cuts[1:]):
                for off, facing in faces:
                    wall_quad(walls_mesh, a_s, b_s, off, facing, zb(a_s), zb(b_s), zt(a_s), zt(b_s))
                # coping over the full thickness (retaining: into the high side)
                o0, o1 = (thick * 0.5 + 0.05, -thick * 0.5 - 0.05) if not retaining else (-high_sign * 0.05, high_sign * (thick + 0.05))
                ca0, cb0 = pt_at(a_s, o0), pt_at(b_s, o0)
                ca1, cb1 = pt_at(a_s, o1), pt_at(b_s, o1)
                ch = 0.18
                quad = [(*ca1, zt(a_s) + ch), (*cb1, zt(b_s) + ch), (*cb0, zt(b_s) + ch), (*ca0, zt(a_s) + ch)]
                cross = (quad[1][0] - quad[0][0]) * (quad[3][1] - quad[0][1]) - (quad[1][1] - quad[0][1]) * (quad[3][0] - quad[0][0])
                _add_quad(coping, *(quad if cross > 0 else [quad[1], quad[0], quad[3], quad[2]]))
                for off_c, fac in ((o0, 1.0 if o0 > 0 else -1.0), (o1, 1.0 if o1 > 0 else -1.0)):
                    wall_quad(coping, a_s, b_s, off_c, fac, zt(a_s) - 0.02, zt(b_s) - 0.02, zt(a_s) + ch, zt(b_s) + ch)
            # end caps at span ends
            for s_e, sgn in ((s0, -1.0), (s1, 1.0)):
                if (s_e <= 0.01 or s_e >= line.length - 0.01) and cfg.get("end_turrets"):
                    continue
                offs = (thick * 0.5, -thick * 0.5) if not retaining else (0.0, high_sign * thick)
                a, b = pt_at(s_e, offs[0]), pt_at(s_e, offs[1])
                quad = [(*a, zb(s_e)), (*b, zb(s_e)), (*b, zt(s_e)), (*a, zt(s_e))]
                _add_quad(walls_mesh, *quad)
                _add_quad(walls_mesh, quad[1], quad[0], quad[3], quad[2])

        # Arches over gate openings in free-standing walls
        for g0, g1, kind, arch_h, label in gaps:
            if kind != "gate" or retaining or arch_h is None:
                continue
            s_m = 0.5 * (g0 + g1)
            z_open = zb(s_m) + 0.3 + arch_h
            if z_open + 0.4 > zt(s_m):
                continue
            for off, facing in faces:
                wall_quad(walls_mesh, g0, g1, off, facing, z_open, z_open, zt(g0), zt(g1))
            # soffit (underside of the lintel) and stone archivolt
            a0, b0 = pt_at(g0, thick * 0.5), pt_at(g1, thick * 0.5)
            a1, b1 = pt_at(g0, -thick * 0.5), pt_at(g1, -thick * 0.5)
            _add_quad(walls_mesh, (*a0, z_open), (*b0, z_open), (*b1, z_open), (*a1, z_open))
            _add_quad(walls_mesh, (*b0, z_open), (*a0, z_open), (*a1, z_open), (*b1, z_open))
            for off, facing in ((thick * 0.5 + 0.06, 1.0), (-thick * 0.5 - 0.06, -1.0)):
                wall_quad(coping, g0 - 0.25, g1 + 0.25, off, facing, z_open, z_open, z_open + 0.3, z_open + 0.3)
            for jamb in (g0, g1):
                for off, facing in ((thick * 0.5 + 0.06, 1.0), (-thick * 0.5 - 0.06, -1.0)):
                    wall_quad(coping, jamb - 0.25 if jamb == g0 else jamb, jamb if jamb == g0 else jamb + 0.25, off, facing,
                              zb(jamb), zb(jamb), z_open, z_open)

        # Crenellations (merlons) on top of free-standing walls
        if cfg.get("crenellations") and not retaining:
            pitch = float(cfg.get("merlon_pitch_m", 1.6))
            mw = float(cfg.get("merlon_width_m", 0.8))
            mh = float(cfg.get("merlon_height_m", 0.75))
            for s0, s1 in spans:
                k = s0 + pitch * 0.5
                while k + mw * 0.5 <= s1 - 0.2:
                    z0 = zt(k) + 0.18
                    for off, facing in faces:
                        wall_quad(walls_mesh, k - mw * 0.5, k + mw * 0.5, off, facing, z0, z0, z0 + mh, z0 + mh)
                    a0, b0 = pt_at(k - mw * 0.5, thick * 0.5), pt_at(k + mw * 0.5, thick * 0.5)
                    a1, b1 = pt_at(k - mw * 0.5, -thick * 0.5), pt_at(k + mw * 0.5, -thick * 0.5)
                    quad = [(*a1, z0 + mh), (*b1, z0 + mh), (*b0, z0 + mh), (*a0, z0 + mh)]
                    cross = (quad[1][0] - quad[0][0]) * (quad[3][1] - quad[0][1]) - (quad[1][1] - quad[0][1]) * (quad[3][0] - quad[0][0])
                    _add_quad(coping, *(quad if cross > 0 else [quad[1], quad[0], quad[3], quad[2]]))
                    for sx in (k - mw * 0.5, k + mw * 0.5):
                        a, b = pt_at(sx, thick * 0.5), pt_at(sx, -thick * 0.5)
                        q = [(*a, z0), (*b, z0), (*b, z0 + mh), (*a, z0 + mh)]
                        _add_quad(walls_mesh, *q)
                        _add_quad(walls_mesh, q[1], q[0], q[3], q[2])
                    k += pitch

        # Loopholes (dark slits) along the faces
        if cfg.get("loopholes"):
            pitch = float(cfg.get("loophole_pitch_m", 2.2))
            for s0, s1 in spans:
                k = s0 + pitch * 0.5
                while k <= s1 - 0.6:
                    z0 = zb(k) + 0.3 + float(cfg.get("loophole_height_above_ground_m", 1.3))
                    if z0 + 0.45 < zt(k) - 0.3:
                        for off, facing in faces:
                            o = off + (0.012 if off >= 0 else -0.012)
                            wall_quad(dark, k - 0.14, k + 0.14, o, facing, z0, z0, z0 + 0.4, z0 + 0.4)
                    k += pitch

        # Round turrets with conical caps at both wall ends
        turrets = []
        if cfg.get("end_turrets"):
            r = float(cfg.get("turret_radius_m", 1.6))
            extra = float(cfg.get("turret_extra_height_m", 1.4))
            cap_h = float(cfg.get("turret_cap_height_m", 1.5))
            sides = 12
            for s_e in (0.0, line.length):
                c = line.interpolate(s_e)
                z0 = zb(s_e) - 0.2
                z1 = zt(s_e) + extra
                ring = [(c.x + r * cos(2 * pi * i / sides), c.y + r * sin(2 * pi * i / sides)) for i in range(sides)]
                for i in range(sides):
                    a, b = ring[i], ring[(i + 1) % sides]
                    _add_quad(walls_mesh, (*a, z0), (*b, z0), (*b, z1), (*a, z1))
                    # corbel ring under the cap
                    ao = (c.x + (r + 0.18) * cos(2 * pi * i / sides), c.y + (r + 0.18) * sin(2 * pi * i / sides))
                    bo = (c.x + (r + 0.18) * cos(2 * pi * (i + 1) / sides), c.y + (r + 0.18) * sin(2 * pi * (i + 1) / sides))
                    _add_quad(coping, (*ao, z1 - 0.35), (*bo, z1 - 0.35), (*bo, z1), (*ao, z1))
                    # conical cap
                    _add_triangle(coping, (*ao, z1), (*bo, z1), (c.x, c.y, z1 + cap_h))
                # finial
                for i in range(4):
                    a = (c.x + 0.12 * cos(pi * i / 2), c.y + 0.12 * sin(pi * i / 2))
                    b = (c.x + 0.12 * cos(pi * (i + 1) / 2), c.y + 0.12 * sin(pi * (i + 1) / 2))
                    _add_quad(coping, (*a, z1 + cap_h - 0.2), (*b, z1 + cap_h - 0.2), (*b, z1 + cap_h + 0.35), (*a, z1 + cap_h + 0.35))
                # door arch facing the wall's free side
                turrets.append({"position_m": [round(c.x, 3), round(c.y, 3)], "top_z_m": round(z1 + cap_h, 3)})

        if retaining:
            step_lines.append(WallStepLine(
                wall_id=wid, line=line, s_vals=s_vals, top_z=top, base_z=base, high_sign=high_sign,
                gaps=[(g[0], g[1]) for g in gaps],
            ))
        exclusion.append(line.buffer(max(thick, 1.0) + (2.0 if cfg.get("end_turrets") else 0.0)))
        report.append({
            "id": wid,
            "kind": "retaining" if retaining else "free_standing",
            "length_m": round(line.length, 2),
            "built_length_m": round(built, 2),
            "height_m": [round(float(np.min(top - base)), 3), round(float(np.max(top - base)), 3)],
            "height_source": source,
            "osm_height_m": h_tag,
            "terrain_step_m": round(step, 2),
            "thickness_m": thick,
            "openings": [{"kind": g[2], "width_m": round(g[1] - g[0], 2), "label": g[4]} for g in gaps],
            "turrets": turrets,
            "details": {k: v for k, v in cfg.items() if k in ("crenellations", "loopholes", "end_turrets")},
            "dimensions_source": cfg.get("dimensions_source", "assumed_sprint13_wall_details" if cfg else "osm_or_assumed"),
            "reference_ids": cfg.get("reference_ids", []),
        })
    return report, step_lines, exclusion
