"""Generate 3D bridge deck, parapet/railing, and abutment geometry for SM_Bridges."""

from __future__ import annotations

from math import acos, ceil, cos, degrees, hypot, pi, sin

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.road_elevation import BridgeChain, TunnelWayInfo, _densify_polyline
from tools.mesh_generator.solids import arch_curve, arched_face, beam, box_faces, frame_box, orient


BRIDGE_DECK_THICKNESS_M = 0.50
BRIDGE_PARAPET_HEIGHT_M = 1.00
BRIDGE_PARAPET_WIDTH_M = 0.22
BRIDGE_ABUTMENT_SKIRT_M = 1.60
BRIDGE_SAMPLE_STEP_M = 2.5

PATH_CLASSES = {"footway", "cycleway", "path", "steps"}
STONE_SURFACES = {"cobblestone", "unhewn_cobblestone", "sett", "paving_stones", "pebblestone"}

# Vertex colors (linear RGB 0..1) matching Doemitz palette
COLOR_STONE_TOP = (0.50, 0.48, 0.45)
COLOR_STONE_SIDE = (0.42, 0.40, 0.37)
COLOR_STONE_PARAPET = (0.52, 0.49, 0.45)
COLOR_WOOD_TOP = (0.42, 0.28, 0.16)
COLOR_WOOD_SIDE = (0.31, 0.20, 0.11)
COLOR_WOOD_PARAPET = (0.36, 0.23, 0.13)
COLOR_ROAD_ASPHALT = (0.24, 0.24, 0.25)
COLOR_ROAD_PAVING = (0.38, 0.32, 0.27)
COLOR_PIER_STONE = (0.44, 0.41, 0.38)
COLOR_ARCH_STONE = (0.50, 0.46, 0.42)
COLOR_TUNNEL_BRICK = (0.48, 0.22, 0.16)
COLOR_TUNNEL_KEYSTONE = (0.62, 0.59, 0.54)
COLOR_TUNNEL_FLOOR = (0.34, 0.31, 0.27)
COLOR_RAMPART_TURF = (0.26, 0.36, 0.19)
COLOR_SANDSTONE = (0.52, 0.33, 0.15)
COLOR_SANDSTONE_SHADE = (0.42, 0.27, 0.12)
COLOR_SANDSTONE_DARK = (0.31, 0.20, 0.09)
COLOR_DOOR_WOOD = (0.50, 0.18, 0.08)
COLOR_WOOD_PLANK_A = (0.29, 0.23, 0.17)
COLOR_WOOD_PLANK_B = (0.24, 0.19, 0.14)
COLOR_WOOD_POST = (0.19, 0.14, 0.10)
COLOR_WOOD_RAIL = (0.26, 0.20, 0.15)
WOOD_PLANK_M = 0.3
WOOD_POST_SPACING_M = 1.25
WOOD_TRESTLE_SPACING_M = 5.0


def resolve_bridge_material(chain: BridgeChain) -> tuple[str, str]:
    """Determine bridge structural material ('wood' or 'stone') and document source."""
    mat = chain.material_tag.strip().lower()
    struct = chain.bridge_structure.strip().lower()
    surf = chain.surface.strip().lower()

    if any(k in mat for k in ("wood", "timber")):
        return "wood", f"osm_material:{mat}"
    if any(k in mat for k in ("stone", "masonry", "brick", "concrete", "steel", "metal")):
        return "stone", f"osm_material:{mat}"
    if surf == "wood":
        return "wood", "osm_surface:wood"
    if struct in ("arch", "masonry"):
        return "stone", f"osm_bridge_structure:{struct}"
    if chain.highway in PATH_CLASSES:
        return "wood", "assumed_wood_for_footway"
    return "stone", "assumed_natural_stone_for_road_bridge"


class _ColoredMeshBuilder:
    def __init__(self):
        self.vertices: list[tuple[float, float, float]] = []
        self.triangles: list[tuple[int, int, int]] = []
        self.vertex_colors: list[tuple[float, float, float]] = []

    def add_triangle(self, p0, p1, p2, color):
        offset = len(self.vertices)
        for p in (p0, p1, p2):
            self.vertices.append((round(float(p[0]), 4), round(float(p[1]), 4), round(float(p[2]), 4)))
            self.vertex_colors.append(color)
        self.triangles.append((offset, offset + 1, offset + 2))

    def add_quad(self, p0, p1, p2, p3, color):
        offset = len(self.vertices)
        for p in (p0, p1, p2, p3):
            self.vertices.append((round(float(p[0]), 4), round(float(p[1]), 4), round(float(p[2]), 4)))
            self.vertex_colors.append(color)
        self.triangles.append((offset, offset + 1, offset + 2))
        self.triangles.append((offset, offset + 2, offset + 3))


def _station_normals(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Compute smooth unit right-hand normal (ty, -tx) perpendicular to polyline at each vertex."""
    n = len(pts)
    normals: list[tuple[float, float]] = []
    for i in range(n):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            dx1, dy1 = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
            dx2, dy2 = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            l1 = hypot(dx1, dy1) or 1.0
            l2 = hypot(dx2, dy2) or 1.0
            dx, dy = dx1 / l1 + dx2 / l2, dy1 / l1 + dy2 / l2
        norm = hypot(dx, dy)
        if norm <= 1e-9:
            normals.append((1.0, 0.0))
        else:
            tx, ty = dx / norm, dy / norm
            normals.append((ty, -tx))
    return normals


def _add_prism_along_axis(
    builder: _ColoredMeshBuilder,
    origin: tuple[float, float],
    fwd: tuple[float, float],
    right: tuple[float, float],
    s0: float,
    s1: float,
    lat0: float,
    lat1: float,
    z0: float,
    z1: float,
    color: tuple[float, float, float],
    add_top: bool = True,
    add_bottom: bool = False,
) -> None:
    ox, oy = origin
    fx, fy = fwd
    rx, ry = right

    def pt(s: float, lat: float, z: float) -> tuple[float, float, float]:
        return (ox + fx * s + rx * lat, oy + fy * s + ry * lat, z)

    b0 = pt(s0, lat0, z0)
    b1 = pt(s0, lat1, z0)
    b2 = pt(s1, lat1, z0)
    b3 = pt(s1, lat0, z0)
    t0 = pt(s0, lat0, z1)
    t1 = pt(s0, lat1, z1)
    t2 = pt(s1, lat1, z1)
    t3 = pt(s1, lat0, z1)

    builder.add_quad(b0, b1, t1, t0, color)
    builder.add_quad(b1, b2, t2, t1, color)
    builder.add_quad(b2, b3, t3, t2, color)
    builder.add_quad(b3, b0, t0, t3, color)
    if add_top:
        builder.add_quad(t0, t1, t2, t3, color)
    if add_bottom:
        builder.add_quad(b1, b0, b3, b2, color)


def _add_faces(builder: _ColoredMeshBuilder, quads, color) -> None:
    for q in quads:
        if len(q) == 3:
            builder.add_triangle(q[0], q[1], q[2], color)
        else:
            builder.add_quad(q[0], q[1], q[2], q[3], color)


def _add_timber_details(builder, chain, pts, cum_s, normals, z_tops, z_bots, total_half_w, elevation, water_level_m):
    """
    Wooden bridges (OSM material=wood or footways): transverse deck planks, an open timber railing (posts,
    handrail, middle rail) instead of a solid parapet, and timber trestle bents down to the moat or river floor
    (reference photos of the fortress drawbridge approach).
    """
    def frame(i):
        j = i + 1 if i + 1 < len(pts) else i
        k = j - 1
        tx, ty = pts[j][0] - pts[k][0], pts[j][1] - pts[k][1]
        tl = hypot(tx, ty) or 1.0
        return (tx / tl, ty / tl), normals[i]

    def z_top_at(s_pos):
        return float(np.interp(s_pos, cum_s, z_tops))

    def xy_at(s_pos):
        for i in range(len(cum_s) - 1):
            if cum_s[i] - 1e-9 <= s_pos <= cum_s[i + 1] + 1e-9:
                t = 0.0 if cum_s[i + 1] - cum_s[i] < 1e-9 else (s_pos - cum_s[i]) / (cum_s[i + 1] - cum_s[i])
                x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t
                y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
                n0, n1 = normals[i], normals[i + 1]
                nx, ny = n0[0] + (n1[0] - n0[0]) * t, n0[1] + (n1[1] - n0[1]) * t
                nl = hypot(nx, ny) or 1.0
                tx, ty = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
                tl = hypot(tx, ty) or 1.0
                return (x, y), (tx / tl, ty / tl), (nx / nl, ny / nl)
        return pts[-1], frame(len(pts) - 1)[0], normals[-1]

    length = cum_s[-1]
    # 1. deck planks (2 mm above the walkable deck so the colours read without z-fighting)
    n_planks = max(1, int(round(length / WOOD_PLANK_M)))
    for k in range(n_planks):
        sa, sb = length * k / n_planks, length * (k + 1) / n_planks
        (pa, _, na), (pb, _, nb) = xy_at(sa), xy_at(sb)
        za, zb = z_top_at(sa) + 0.002, z_top_at(sb) + 0.002
        hw = total_half_w - 0.02
        quad = [(pa[0] - na[0] * hw, pa[1] - na[1] * hw, za), (pa[0] + na[0] * hw, pa[1] + na[1] * hw, za),
                (pb[0] + nb[0] * hw, pb[1] + nb[1] * hw, zb), (pb[0] - nb[0] * hw, pb[1] - nb[1] * hw, zb)]
        _add_faces(builder, [orient(quad, (0.0, 0.0, 1.0))], COLOR_WOOD_PLANK_A if k % 2 == 0 else COLOR_WOOD_PLANK_B)
    # 2. railing: posts, handrail and middle rail on both edges
    n_posts = max(1, int(ceil(length / WOOD_POST_SPACING_M)))
    for side in (-1.0, 1.0):
        lat_c = side * (total_half_w - 0.08)
        for k in range(n_posts + 1):
            sp = min(length, k * length / n_posts)
            (pxy, t, nrm) = xy_at(sp)
            z0 = z_top_at(sp)
            _add_faces(builder, frame_box(pxy, t, nrm, -0.06, 0.06, lat_c - 0.06, lat_c + 0.06, z0, z0 + 1.08), COLOR_WOOD_POST)
        for i in range(len(pts) - 1):
            for dz0, dz1, h_w in ((0.97, 1.09, 0.07), (0.46, 0.56, 0.05)):
                la, lb = lat_c - h_w, lat_c + h_w
                corners = []
                for z_off in (dz0, dz1):
                    for idx, lat in ((i, la), (i, lb), (i + 1, lb), (i + 1, la)):
                        nx, ny = normals[idx]
                        corners.append((pts[idx][0] + nx * lat, pts[idx][1] + ny * lat, z_tops[idx] + z_off))
                _add_faces(builder, box_faces(corners), COLOR_WOOD_RAIL)
    # 3. trestle bents every few metres where the deck stands clear of the ground
    n_bents = int(length // WOOD_TRESTLE_SPACING_M)
    for k in range(1, n_bents + 1):
        sp = k * length / (n_bents + 1)
        (pxy, t, nrm) = xy_at(sp)
        z_bot = float(np.interp(sp, cum_s, z_bots))
        lats = [-(total_half_w - 0.3), total_half_w - 0.3]
        if total_half_w > 1.6:
            lats.insert(1, 0.0)
        bases = []
        for lat in lats:
            x, y = pxy[0] + nrm[0] * lat, pxy[1] + nrm[1] * lat
            g = float(elevation.sample(x, y))
            if water_level_m is not None:
                g = min(g, water_level_m - 0.4)
            bases.append(g - 0.3)
        if z_bot - max(bases) < 0.8:
            continue
        for lat, zb in zip(lats, bases):
            _add_faces(builder, frame_box(pxy, t, nrm, -0.1, 0.1, lat - 0.1, lat + 0.1, zb, z_bot - 0.02), COLOR_WOOD_POST)
        _add_faces(builder, frame_box(pxy, t, nrm, -0.13, 0.13, -total_half_w + 0.05, total_half_w - 0.05,
                                      z_bot - 0.3, z_bot - 0.01), COLOR_WOOD_SIDE)
        d = 1.0 if k % 2 else -1.0
        z_lo = max(bases) + 0.6
        p0 = (pxy[0] + nrm[0] * lats[0] * d, pxy[1] + nrm[1] * lats[0] * d, z_lo)
        p1 = (pxy[0] + nrm[0] * lats[-1] * d, pxy[1] + nrm[1] * lats[-1] * d, z_bot - 0.35)
        _add_faces(builder, beam((p0[0] + t[0] * 0.12, p0[1] + t[1] * 0.12, p0[2]),
                                 (p1[0] + t[0] * 0.12, p1[1] + t[1] * 0.12, p1[2]), 0.08, 0.16), COLOR_WOOD_POST)


def _add_stone_bridge_arches_and_piers(
    builder: _ColoredMeshBuilder,
    chain: BridgeChain,
    total_half_w: float,
    road_offset_m: float,
    elevation: ElevationModel,
    water_level_m: float | None,
    detail_cfg: dict,
) -> None:
    """Add masonry arches and river/abutment piers beneath Torbrücke or Steinbrücke while keeping clear water headroom."""
    p_start = chain.coords[0]
    p_end = chain.coords[-1]
    dx = p_end[0] - p_start[0]
    dy = p_end[1] - p_start[1]
    span_len = max(hypot(dx, dy), 1.0)
    fx, fy = dx / span_len, dy / span_len
    rx, ry = fy, -fx

    arch_count = max(1, int(detail_cfg.get("arch_count", 1)))
    pier_w = float(detail_cfg.get("pier_width_m", 1.35))
    arch_rise = float(detail_cfg.get("arch_rise_m", 1.45))

    base_floor = (water_level_m - 1.2) if water_level_m is not None else (min(chain.z_vals) - 5.5)
    pier_half_w = total_half_w - 0.15

    pier_stations = [0.85, span_len - 0.85]
    if arch_count > 1:
        for k in range(1, arch_count):
            pier_stations.append((k / arch_count) * span_len)
    pier_stations.sort()

    for ps in pier_stations:
        z_top = chain.ground_elevation_at_s(ps) + road_offset_m - BRIDGE_DECK_THICKNESS_M + 0.05
        half_p = pier_w * 0.5
        _add_prism_along_axis(
            builder, p_start, (fx, fy), (rx, ry),
            ps - half_p, ps + half_p,
            -pier_half_w, pier_half_w,
            base_floor, z_top,
            COLOR_PIER_STONE, add_top=True,
        )
        _add_prism_along_axis(
            builder, p_start, (fx, fy), (rx, ry),
            ps - half_p - 0.18, ps + half_p + 0.18,
            -pier_half_w - 0.25, pier_half_w + 0.25,
            z_top - 0.45, z_top,
            COLOR_ARCH_STONE, add_top=True,
        )

    n_seg = 8
    for s_left_pier, s_right_pier in zip(pier_stations, pier_stations[1:]):
        a0 = s_left_pier + pier_w * 0.42
        a1 = s_right_pier - pier_w * 0.42
        bay_span = a1 - a0
        if bay_span < 2.0:
            continue
        deck_bot_mid = chain.ground_elevation_at_s(0.5 * (a0 + a1)) + road_offset_m - BRIDGE_DECK_THICKNESS_M
        max_rise = max(0.45, min(arch_rise, (deck_bot_mid - (water_level_m + 1.8)) if water_level_m is not None else arch_rise))

        def arch_z(frac: float, s_pos: float) -> float:
            deck_bot = chain.ground_elevation_at_s(s_pos) + road_offset_m - BRIDGE_DECK_THICKNESS_M
            drop = max_rise * ((2.0 * frac - 1.0) ** 2)
            return deck_bot - drop

        def pt(s: float, lat: float, z: float) -> tuple[float, float, float]:
            return (p_start[0] + fx * s + rx * lat, p_start[1] + fy * s + ry * lat, z)

        arch_half_w = total_half_w - 0.08
        for k in range(n_seg):
            f0 = k / n_seg
            f1 = (k + 1) / n_seg
            s0 = a0 + bay_span * f0
            s1 = a0 + bay_span * f1
            zb0 = chain.ground_elevation_at_s(s0) + road_offset_m - BRIDGE_DECK_THICKNESS_M + 0.02
            zb1 = chain.ground_elevation_at_s(s1) + road_offset_m - BRIDGE_DECK_THICKNESS_M + 0.02
            za0 = arch_z(f0, s0)
            za1 = arch_z(f1, s1)

            builder.add_quad(
                pt(s0, arch_half_w, za0), pt(s1, arch_half_w, za1),
                pt(s1, arch_half_w, zb1), pt(s0, arch_half_w, zb0),
                COLOR_ARCH_STONE,
            )
            builder.add_quad(
                pt(s1, -arch_half_w, za1), pt(s0, -arch_half_w, za0),
                pt(s0, -arch_half_w, zb0), pt(s1, -arch_half_w, zb1),
                COLOR_ARCH_STONE,
            )
            builder.add_quad(
                pt(s0, arch_half_w, za0), pt(s0, -arch_half_w, za0),
                pt(s1, -arch_half_w, za1), pt(s1, arch_half_w, za1),
                COLOR_PIER_STONE,
            )


def _pt(origin, fwd, right, s_pos, lat, z):
    return (origin[0] + fwd[0] * s_pos + right[0] * lat, origin[1] + fwd[1] * s_pos + right[1] * lat, z)


def _add_sandstone_gate(builder, origin, fwd, right, s_front, ze, half_cw, clear_h, spring_h, arch_r, n_arch):
    """
    Renaissance sandstone gate (Sandsteintor 1565, reference photos): rusticated jambs and voussoir arch with
    keystone, pilasters with diamond bosses, entablature with inscription tablet, an attic with two coats of
    arms between volutes and urns, a triangular pediment with a bust, and the small side door with its own
    pediment to the right of the gate. Everything stands in front of the portal face (s < s_front).
    """
    out = (-fwd[0], -fwd[1])
    out3 = (out[0], out[1], 0.0)

    def box(lat0, lat1, z0, z1, proud, color, back=0.0):
        _add_prism_along_axis(builder, origin, fwd, right, s_front - proud, s_front - back, min(lat0, lat1),
                              max(lat0, lat1), ze + z0, ze + z1, color, add_top=True, add_bottom=True)

    def face(lat_z, proud, color):
        """Flat polygon (list of (lat, z)) in a plane `proud` in front of the portal, as a triangle fan."""
        c_lat = sum(p[0] for p in lat_z) / len(lat_z)
        c_z = sum(p[1] for p in lat_z) / len(lat_z)
        c = _pt(origin, fwd, right, s_front - proud, c_lat, ze + c_z)
        for (la, za), (lb, zb) in zip(lat_z, lat_z[1:] + lat_z[:1]):
            tri = [c, _pt(origin, fwd, right, s_front - proud, la, ze + za), _pt(origin, fwd, right, s_front - proud, lb, ze + zb)]
            _add_faces(builder, [orient(tri, out3)], color)

    def edge(la, za, lb, zb, p0, p1, toward, color):
        q = [_pt(origin, fwd, right, s_front - p0, la, ze + za), _pt(origin, fwd, right, s_front - p0, lb, ze + zb),
             _pt(origin, fwd, right, s_front - p1, lb, ze + zb), _pt(origin, fwd, right, s_front - p1, la, ze + za)]
        _add_faces(builder, [orient(q, toward)], color)

    ent0 = clear_h + 0.55
    hw_panel = half_cw + 0.65
    # stone background of the gate front (spandrels) with the arched opening
    arch = arch_curve(half_cw, spring_h, arch_r, n_arch)
    arch_w = [(u, ze + z) for u, z in arch]
    _add_faces(builder, arched_face(origin, right, out, -(s_front - 0.06), -hw_panel, hw_panel, ze - 0.05,
                                    lambda _u: ze + ent0, arch_w, out3), COLOR_SANDSTONE)
    for lat_e, d in ((-hw_panel, -1.0), (hw_panel, 1.0)):
        edge(lat_e, -0.05, lat_e, ent0, 0.0, 0.06, (right[0] * d, right[1] * d, 0.0), COLOR_SANDSTONE)
    # voussoirs around the arch, alternating shades, and a keystone
    ring = 0.42
    outer = [(u * (half_cw + ring) / half_cw, spring_h + (z - spring_h) * (arch_r + ring) / arch_r) for u, z in arch]
    for k, ((ua, za), (ub, zb), (uc, zc), (ud, zd)) in enumerate(zip(arch, arch[1:], outer[1:], outer)):
        color = COLOR_SANDSTONE if k % 2 == 0 else COLOR_SANDSTONE_SHADE
        face([(ua, za), (ub, zb), (uc, zc), (ud, zd)], 0.18, color)
        um, zm = 0.5 * (uc + ud), 0.5 * (zc + zd)
        edge(ud, zd, uc, zc, 0.06, 0.18, (right[0] * um, right[1] * um, zm - spring_h), color)
        um, zm = 0.5 * (ua + ub), 0.5 * (za + zb)
        edge(ua, za, ub, zb, 0.0, 0.18, (-right[0] * um, -right[1] * um, spring_h - zm), color)
    box(-0.22, 0.22, clear_h - 0.08, clear_h + 0.55, 0.28, COLOR_SANDSTONE_SHADE)
    # rusticated jambs below the spring and impost blocks
    for side in (-1.0, 1.0):
        z = -0.05
        k = 0
        while z < spring_h - 0.05:
            z1 = min(spring_h, z + 0.48)
            box(side * half_cw, side * (half_cw + ring), z, z1, 0.18 if k % 2 == 0 else 0.22,
                COLOR_SANDSTONE if k % 2 == 0 else COLOR_SANDSTONE_SHADE)
            z, k = z1, k + 1
        box(side * (half_cw - 0.05), side * (half_cw + 0.55), spring_h - 0.24, spring_h, 0.26, COLOR_SANDSTONE)
    # pilasters with pedestal, diamond bosses and capital
    for side in (-1.0, 1.0):
        l0, l1 = side * (half_cw + 0.65), side * (half_cw + 1.2)
        box(l0, l1, -0.05, ent0, 0.24, COLOR_SANDSTONE)
        box(side * (half_cw + 0.58), side * (half_cw + 1.27), -0.05, 0.7, 0.3, COLOR_SANDSTONE_SHADE)
        box(side * (half_cw + 0.58), side * (half_cw + 1.27), ent0 - 0.3, ent0, 0.32, COLOR_SANDSTONE_SHADE)
        zb = 1.0
        while zb + 0.3 < ent0 - 0.35:
            box(side * (half_cw + 0.75), side * (half_cw + 1.1), zb, zb + 0.3, 0.33, COLOR_SANDSTONE_SHADE)
            zb += 0.85
        # medallion head in the spandrel
        box(side * (half_cw + 0.05), side * (half_cw + 0.5), clear_h - 0.05, clear_h + 0.4, 0.12, COLOR_SANDSTONE_DARK)
    # entablature: architrave, frieze with inscription tablet and lion heads, cornice
    hw_ent = half_cw + 1.4
    box(-hw_ent, hw_ent, ent0, ent0 + 0.22, 0.32, COLOR_SANDSTONE)
    box(-hw_ent, hw_ent, ent0 + 0.22, ent0 + 0.72, 0.26, COLOR_SANDSTONE_SHADE)
    box(-1.05, 1.05, ent0 + 0.28, ent0 + 0.66, 0.3, COLOR_SANDSTONE)
    for lat_c in (-2.6, -1.65, 1.65, 2.6):
        box(lat_c - 0.18, lat_c + 0.18, ent0 + 0.3, ent0 + 0.64, 0.32, COLOR_SANDSTONE_DARK)
    box(-hw_ent - 0.15, hw_ent + 0.15, ent0 + 0.72, ent0 + 0.98, 0.45, COLOR_SANDSTONE)
    # attic with two coats of arms, side pilasters, volutes and urns
    a0, a1 = ent0 + 0.98, ent0 + 2.33
    box(-1.75, 1.75, a0, a1, 0.24, COLOR_SANDSTONE)
    for l0, l1 in ((-1.42, -0.12), (0.12, 1.42)):
        box(l0, l1, a0 + 0.15, a1 - 0.12, 0.3, COLOR_SANDSTONE_DARK)
    for side in (-1.0, 1.0):
        box(side * 1.55, side * 1.8, a0, a1, 0.3, COLOR_SANDSTONE_SHADE)
        v_in, v_out = side * 1.8, side * 2.55
        tri = [(v_in, a0), (v_out, a0), (v_in, a0 + 0.95)]
        face(tri if side > 0 else tri[::-1], 0.22, COLOR_SANDSTONE_SHADE)
        dl, dz = v_out - v_in, -0.95
        slope_n = (right[0] * side * 0.95, right[1] * side * 0.95, abs(dl))
        edge(v_in, a0 + 0.95, v_out, a0, 0.0, 0.22, slope_n, COLOR_SANDSTONE_SHADE)
        box(side * 2.8, side * 3.1, a0, a0 + 0.22, 0.34, COLOR_SANDSTONE_SHADE)
        box(side * 2.85, side * 3.05, a0 + 0.22, a0 + 0.48, 0.3, COLOR_SANDSTONE)
    # triangular pediment with its cornice, bust on the apex
    p0, apex = a1 + 0.16, a1 + 0.86
    box(-1.95, 1.95, a1, p0, 0.32, COLOR_SANDSTONE)
    face([(-1.95, p0), (1.95, p0), (0.0, apex)], 0.3, COLOR_SANDSTONE)
    for side in (-1.0, 1.0):
        edge(0.0, apex, side * 1.95, p0, 0.0, 0.3, (right[0] * side * 0.7, right[1] * side * 0.7, 1.95), COLOR_SANDSTONE)
    box(-0.17, 0.17, apex - 0.1, apex + 0.18, 0.3, COLOR_SANDSTONE_SHADE)
    box(-0.13, 0.13, apex + 0.18, apex + 0.58, 0.27, COLOR_SANDSTONE_DARK)
    # side door with arched frame, frieze, cornice and pediment (to the right seen from the forecourt)
    d0, d1 = half_cw + 1.65, half_cw + 2.75
    dc, dr = 0.5 * (d0 + d1), 0.5 * (d1 - d0)
    d_spring = 2.1
    face([(d1, -0.02), (d1, d_spring)] + [(dc + dr * cos(pi * k / 8), d_spring + dr * sin(pi * k / 8)) for k in range(1, 8)]
         + [(d0, d_spring), (d0, -0.02)], 0.01, COLOR_DOOR_WOOD)
    for l0, l1 in ((d0 - 0.3, d0), (d1, d1 + 0.3)):
        z = -0.05
        k = 0
        while z < d_spring + 0.6:
            z1 = min(d_spring + 0.65, z + 0.45)
            box(l0, l1, z, z1, 0.14 if k % 2 == 0 else 0.18, COLOR_SANDSTONE if k % 2 == 0 else COLOR_SANDSTONE_SHADE)
            z, k = z1, k + 1
    door_arch = [(dc - dr * cos(pi * k / 8), d_spring + dr * sin(pi * k / 8)) for k in range(9)]
    door_out = [(dc - (dr + 0.3) * cos(pi * k / 8), d_spring + (dr + 0.3) * sin(pi * k / 8)) for k in range(9)]
    for (ua, za), (ub, zb), (uc, zc), (ud, zd) in zip(door_arch, door_arch[1:], door_out[1:], door_out):
        face([(ua, za), (ub, zb), (uc, zc), (ud, zd)], 0.14, COLOR_SANDSTONE)
    box(d0 - 0.3, d1 + 0.3, d_spring + 0.65, d_spring + 0.95, 0.14, COLOR_SANDSTONE)
    box(d0 - 0.35, d1 + 0.35, d_spring + 0.95, d_spring + 1.4, 0.16, COLOR_SANDSTONE_SHADE)
    box(d0 - 0.45, d1 + 0.45, d_spring + 1.4, d_spring + 1.55, 0.26, COLOR_SANDSTONE)
    face([(d0 - 0.42, d_spring + 1.55), (d1 + 0.42, d_spring + 1.55), (dc, d_spring + 2.05)], 0.22, COLOR_SANDSTONE)
    for side, lat_e in ((-1.0, d0 - 0.42), (1.0, d1 + 0.42)):
        edge(dc, d_spring + 2.05, lat_e, d_spring + 1.55, 0.0, 0.22,
             (right[0] * side * 0.5, right[1] * side * 0.5, abs(lat_e - dc)), COLOR_SANDSTONE)


def _add_fortress_tunnel_portal_and_passage(
    builder: _ColoredMeshBuilder,
    tunnel: TunnelWayInfo,
    road_offset_m: float,
    portal_cfg: dict,
    elevation: ElevationModel | None = None,
) -> tuple[Polygon, float, dict]:
    """
    Build a red-brick fortress passage along the OSM tunnel polyline (bends included): walkable floor,
    side walls, barrel vault, a turf cap that closes the rampart over the bore at DGM height, and a
    portal wall at each end that reaches up to the rampart surface.
    """
    clear_w = float(portal_cfg.get("clear_width_m", 2.6))
    clear_h = float(portal_cfg.get("clear_height_m", 3.1))
    portal_w = float(portal_cfg.get("portal_wall_width_m", 5.4))
    portal_h_cfg = float(portal_cfg.get("portal_wall_height_m", 4.4))
    half_cw = clear_w * 0.5
    half_pw = max(portal_w * 0.5, half_cw + 0.9)
    wall_thick = 0.65
    # The terrain cut-out is wider than the bore by more than one 1 m DGM cell, so no terrain triangle
    # straddling the cut edge can rise into the bore; the turf cap covers the cut-out completely.
    corridor_half_w = half_cw + wall_thick + 1.6
    cap_hw = corridor_half_w + 1.25

    coords = [(float(x), float(y)) for x, y in tunnel.coords]
    pts, cum_s = _densify_polyline(coords, 1.0)
    length = max(cum_s[-1], 1.0)
    normals = _station_normals(pts)
    # Portal facade in the plane of the wall the passage opens into (e.g. the Sandsteintor in the gate wall):
    # the last cross-section of the bore is turned into the wall line, the portal is built in that frame.
    facades = {}
    for key, end_idx in (("entry", 0), ("exit", len(pts) - 1)):
        fl = (portal_cfg.get("facade_lines") or {}).get(key)
        if not fl:
            continue
        (fx0, fy0), (fx1, fy1) = fl[0], fl[1]
        wl = hypot(fx1 - fx0, fy1 - fy0) or 1.0
        w = ((fx1 - fx0) / wl, (fy1 - fy0) / wl)
        n0 = normals[end_idx]
        if w[0] * n0[0] + w[1] * n0[1] < 0:
            w = (-w[0], -w[1])
        skew = degrees(acos(max(-1.0, min(1.0, w[0] * n0[0] + w[1] * n0[1]))))
        if skew < 5.0 or skew > 35.0:
            continue
        normals[end_idx] = w
        # signed distance of the bore end in front of the wall line (out of the passage)
        ex, ey = pts[end_idx]
        nbx, nby = pts[end_idx + (1 if end_idx == 0 else -1)]
        ox, oy = ex - nbx, ey - nby
        fn = (w[1], -w[0])
        if fn[0] * ox + fn[1] * oy < 0:
            fn = (-fn[0], -fn[1])
        sd = (ex - fx0) * fn[0] + (ey - fy0) * fn[1]
        facades[end_idx] = {"tangent": w, "out": fn, "end_offset_m": sd, "skew_deg": round(skew, 1)}
    z0 = tunnel.portal_z_m[0] + road_offset_m
    z1 = tunnel.portal_z_m[1] + road_offset_m

    def z_floor(s: float) -> float:
        return z0 + (s / length) * (z1 - z0)

    def at(i: int, lat: float, z: float) -> tuple[float, float, float]:
        nx, ny = normals[i]
        return (pts[i][0] + nx * lat, pts[i][1] + ny * lat, z)

    def dgm(x: float, y: float) -> float | None:
        if elevation is None or elevation.is_flat:
            return None
        return float(elevation.sample(x, y))

    spring_h = clear_h * 0.62
    arch_r = clear_h - spring_h
    n_arch = 10
    min_cover = clear_h + 0.85

    def cap_z(i: int, lat: float) -> float:
        x, y, _ = at(i, lat, 0.0)
        top = z_floor(cum_s[i]) + min_cover
        g = dgm(x, y)
        return max(top, g + 0.03) if g is not None else top

    for i in range(len(pts) - 1):
        za = z_floor(cum_s[i]) - 0.01
        zb = z_floor(cum_s[i + 1]) - 0.01
        # Walkable floor slab (1 cm under the approach road surface to avoid z-fighting at the portal)
        builder.add_quad(at(i, -half_cw - 0.1, za), at(i, half_cw + 0.1, za),
                         at(i + 1, half_cw + 0.1, zb), at(i + 1, -half_cw - 0.1, zb), COLOR_TUNNEL_FLOOR)
        # Side walls up to the vault springing line (inner faces)
        builder.add_quad(at(i, -half_cw, za), at(i + 1, -half_cw, zb),
                         at(i + 1, -half_cw, zb + spring_h), at(i, -half_cw, za + spring_h), COLOR_TUNNEL_BRICK)
        builder.add_quad(at(i + 1, half_cw, zb), at(i, half_cw, za),
                         at(i, half_cw, za + spring_h), at(i + 1, half_cw, zb + spring_h), COLOR_TUNNEL_BRICK)
        # Outer masonry faces (hidden in the rampart, keep the bore closed if terrain is thin)
        builder.add_quad(at(i + 1, -half_cw - wall_thick, zb - 0.5), at(i, -half_cw - wall_thick, za - 0.5),
                         at(i, -half_cw - wall_thick, za + clear_h + 0.8), at(i + 1, -half_cw - wall_thick, zb + clear_h + 0.8),
                         COLOR_TUNNEL_BRICK)
        builder.add_quad(at(i, half_cw + wall_thick, za - 0.5), at(i + 1, half_cw + wall_thick, zb - 0.5),
                         at(i + 1, half_cw + wall_thick, zb + clear_h + 0.8), at(i, half_cw + wall_thick, za + clear_h + 0.8),
                         COLOR_TUNNEL_BRICK)
        # Barrel vault (faces point down into the bore)
        for k in range(n_arch):
            th0 = pi * (1.0 - k / n_arch)
            th1 = pi * (1.0 - (k + 1) / n_arch)
            lat0 = half_cw * cos(th0)
            lat1 = half_cw * cos(th1)
            hz0 = spring_h + arch_r * sin(th0)
            hz1 = spring_h + arch_r * sin(th1)
            builder.add_quad(at(i, lat0, za + hz0), at(i + 1, lat0, zb + hz0),
                             at(i + 1, lat1, zb + hz1), at(i, lat1, za + hz1), COLOR_TUNNEL_BRICK)
        # Turf cap closing the terrain cut-out over the bore, following the rampart surface (CCW upward)
        lats = [-cap_hw, -corridor_half_w, 0.0, corridor_half_w, cap_hw]
        for la, lb in zip(lats, lats[1:]):
            builder.add_quad(at(i, la, cap_z(i, la)), at(i, lb, cap_z(i, lb)),
                             at(i + 1, lb, cap_z(i + 1, lb)), at(i + 1, la, cap_z(i + 1, la)), COLOR_RAMPART_TURF)

    portal_tops: list[float] = []
    aprons: list[dict] = []
    for end_idx, is_entry in ((0, True), (len(pts) - 1, False)):
        ze = z_floor(cum_s[end_idx])
        # Portal frame reaches the rampart surface (highest cap height across the portal width).
        top_needed = max(cap_z(end_idx, lat) for lat in (-cap_hw, -half_pw, 0.0, half_pw, cap_hw)) - ze + 0.25
        portal_h = max(portal_h_cfg, top_needed)
        portal_tops.append(round(portal_h, 3))
        tx = pts[end_idx][0] - pts[end_idx + (1 if is_entry else -1)][0]
        ty = pts[end_idx][1] - pts[end_idx + (1 if is_entry else -1)][1]
        tl = hypot(tx, ty) or 1.0
        out_dir = (tx / tl, ty / tl)              # points out of the tunnel
        p_depth = 0.75
        if end_idx in facades:
            out_dir = facades[end_idx]["out"]
            # portal front 5 cm proud of the wall face (retaining wall face = OSM line)
            p_depth = max(0.15, 0.05 - facades[end_idx]["end_offset_m"])
        fwd = (-out_dir[0], -out_dir[1])          # points into the tunnel
        right = (fwd[1], -fwd[0])
        origin = pts[end_idx]
        s_a, s_b = -p_depth, 0.0
        # level apron in front of and under the portal block (hidden there): no DGM rampart slope may
        # reach out in front of the portal face
        apron = [_pt(origin, fwd, right, s, lat, 0.0)[:2]
                 for s, lat in ((s_b + 0.3, -half_pw - 0.3), (s_b + 0.3, half_pw + 0.3),
                                (s_a - 3.0, half_pw + 0.3), (s_a - 3.0, -half_pw - 0.3))]
        aprons.append({"polygon_m": [[round(x, 4), round(y, 4)] for x, y in apron], "z_m": round(ze - 0.05, 4)})
        for lat_a, lat_b in ((-half_pw, -half_cw), (half_cw, half_pw)):
            _add_prism_along_axis(builder, origin, fwd, right, s_a, s_b, lat_a, lat_b,
                                  ze - 3.6, ze + portal_h, COLOR_TUNNEL_BRICK, add_top=True)
        # arched opening matching the barrel vault: spandrel face and soffit
        arch_pts = arch_curve(half_cw, ze + spring_h, arch_r, n_arch)
        out3 = (out_dir[0], out_dir[1], 0.0)
        _add_faces(builder, arched_face(origin, right, out_dir, p_depth, -half_cw, half_cw, ze + spring_h,
                                        lambda _u: ze + portal_h, arch_pts, out3), COLOR_TUNNEL_BRICK)
        for (ua, za), (ub, zb) in zip(arch_pts, arch_pts[1:]):
            um, zm = 0.5 * (ua + ub), 0.5 * (za + zb)
            qa = [_pt(origin, fwd, right, s_a, ua, za), _pt(origin, fwd, right, s_a, ub, zb),
                  _pt(origin, fwd, right, s_b, ub, zb), _pt(origin, fwd, right, s_b, ua, za)]
            _add_faces(builder, [orient(qa, (-right[0] * um, -right[1] * um, ze + spring_h - zm))], COLOR_TUNNEL_BRICK)
        _add_faces(builder, [orient([_pt(origin, fwd, right, s_a, -half_cw, ze + portal_h),
                                     _pt(origin, fwd, right, s_a, half_cw, ze + portal_h),
                                     _pt(origin, fwd, right, s_b, half_cw, ze + portal_h),
                                     _pt(origin, fwd, right, s_b, -half_cw, ze + portal_h)], (0, 0, 1))],
                   COLOR_TUNNEL_BRICK)
        # Solid foundation under the threshold so the portal stands on a wall, not on two legs (NW-Steg moat edge)
        _add_prism_along_axis(builder, origin, fwd, right, s_a, s_b, -half_cw, half_cw,
                              ze - 3.6, ze - 0.03, COLOR_TUNNEL_BRICK, add_top=True)
        _add_prism_along_axis(builder, origin, fwd, right, s_a - 0.08, s_b + 0.08, -half_pw - 0.12, half_pw + 0.12,
                              ze + portal_h, ze + portal_h + 0.28, COLOR_TUNNEL_KEYSTONE, add_top=True)
        sandstone_end = (portal_cfg.get("end_styles") or {}).get("entry" if is_entry else "exit") == "sandstone_aedicula"
        if not sandstone_end:
            _add_prism_along_axis(builder, origin, fwd, right, s_a - 0.08, s_b + 0.08, -0.32, 0.32,
                                  ze + clear_h - 0.25, ze + clear_h + 0.45, COLOR_TUNNEL_KEYSTONE, add_top=True)
        for side_lat in ((-half_cw - 0.35, half_cw) if not sandstone_end else ()):
            _add_prism_along_axis(builder, origin, fwd, right, s_a - 0.06, s_b + 0.06, side_lat, side_lat + 0.35,
                                  ze + spring_h - 0.18, ze + spring_h + 0.14, COLOR_TUNNEL_KEYSTONE, add_top=True)
        end_style = (portal_cfg.get("end_styles") or {}).get("entry" if is_entry else "exit")
        if end_style == "sandstone_aedicula":
            _add_sandstone_gate(builder, origin, fwd, right, s_a, ze, half_cw, clear_h, spring_h, arch_r, n_arch)

    corridor_poly = LineString(coords).buffer(corridor_half_w, quad_segs=1, cap_style="flat", join_style="mitre")
    if facades:
        # terrain cut-out with the same turned end as the bore, so no cut sliver shows in front of the facade
        left = [at(i, -corridor_half_w, 0.0)[:2] for i in range(len(pts))]
        right_side = [at(i, corridor_half_w, 0.0)[:2] for i in range(len(pts))]
        corridor_poly = Polygon(left + right_side[::-1]).buffer(0)
    floor_ref_z = min(tunnel.portal_z_m[0], tunnel.portal_z_m[1])
    report = {
        "road_id": tunnel.road_id,
        "name": portal_cfg.get("name", tunnel.name or "Tunnelportal"),
        "style": portal_cfg.get("style", "fortress_brick_arch"),
        "highway": tunnel.highway,
        "length_m": round(length, 2),
        "clear_width_m": clear_w,
        "clear_height_m": clear_h,
        "portal_wall_height_m": portal_tops,
        "floor_sources": list(tunnel.floor_sources),
        "floor_slope_percent": round(abs(z1 - z0) / length * 100.0, 2),
        "facades": {("entry" if k == 0 else "exit"): {"skew_deg": v["skew_deg"], "end_offset_m": round(v["end_offset_m"], 3)}
                    for k, v in sorted(facades.items())},
        "end_styles": portal_cfg.get("end_styles") or {},
        "aprons": aprons,
        "dimensions_source": portal_cfg.get("dimensions_source", "assumed_sprint12_tunnel_portal"),
        "polyline_3d_m": [
            [round(x, 4), round(y, 4), round(z_floor(_s), 4)]
            for (x, y), _s in zip(coords, [0.0] + list(np.cumsum([hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(coords, coords[1:])])))
        ],
        "entry_point_3d_m": [round(coords[0][0], 4), round(coords[0][1], 4), round(z0, 4)],
        "exit_point_3d_m": [round(coords[-1][0], 4), round(coords[-1][1], 4), round(z1, 4)],
    }
    return corridor_poly, floor_ref_z, report


def build_bridges_mesh(
    bridges: list[BridgeChain],
    elevation: ElevationModel,
    road_offset_m: float,
    curb_height_m: float,
    sidewalk_widths: dict[str, float],
    default_sidewalk_widths: dict[str, float],
    water_surfaces: list[tuple[Polygon, float]],
    bridge_details_config: dict[str, dict] | None = None,
    tunnels: list[TunnelWayInfo] | None = None,
    tunnel_portals_config: dict[str, dict] | None = None,
) -> tuple[dict | None, list[dict], list[Polygon], list[tuple[Polygon, float]], list[dict]]:
    """
    Build SM_Bridges vertex-colored mesh (with collision), bridge clearance report,
    bridge footprint polygons, walkable tunnel corridors, and tunnel portal reports.
    """
    builder = _ColoredMeshBuilder()
    report_entries: list[dict] = []
    footprints: list[Polygon] = []
    tunnel_corridors: list[tuple[Polygon, float]] = []
    tunnel_portals_report: list[dict] = []
    bridge_details_config = bridge_details_config or {}
    tunnel_portals_config = tunnel_portals_config or {}

    for chain in bridges:
        material_kind, material_source = resolve_bridge_material(chain)

        # Determine if this bridge carries road sidewalks
        sw_width = 0.0
        if chain.highway not in PATH_CLASSES:
            for wid in chain.way_ids:
                if wid in sidewalk_widths:
                    sw_width = max(sw_width, float(sidewalk_widths[wid]))
            if sw_width <= 0.0 and chain.highway in default_sidewalk_widths:
                sw_width = float(default_sidewalk_widths[chain.highway])

        road_half_w = chain.width_m * 0.5
        total_half_w = road_half_w + sw_width
        has_sidewalk = sw_width > 0.0

        # Colors for deck surface, structural sides/underside, and parapets/railings
        if material_kind == "wood":
            deck_top_color = COLOR_WOOD_TOP
            side_color = COLOR_WOOD_SIDE
            parapet_color = COLOR_WOOD_PARAPET
        else:
            side_color = COLOR_STONE_SIDE
            parapet_color = COLOR_STONE_PARAPET
            if chain.surface in STONE_SURFACES:
                deck_top_color = COLOR_ROAD_PAVING
            elif chain.highway in PATH_CLASSES:
                deck_top_color = COLOR_STONE_TOP
            else:
                deck_top_color = COLOR_ROAD_ASPHALT

        pts, cum_s = _densify_polyline(chain.coords, BRIDGE_SAMPLE_STEP_M)
        normals = _station_normals(pts)
        z_tops = [chain.ground_elevation_at_s(s) + road_offset_m for s in cum_s]
        z_bots = [zt - BRIDGE_DECK_THICKNESS_M for zt in z_tops]
        parapet_base_offset = curb_height_m if has_sidewalk else 0.0
        z_para_bases = [zt + parapet_base_offset for zt in z_tops]
        z_para_tops = [zb + BRIDGE_PARAPET_HEIGHT_M for zb in z_para_bases]

        # Precompute offset points at each station:
        # outer left (-total_half_w), inner-parapet left, inner-parapet right, outer right (+total_half_w)
        para_w = min(BRIDGE_PARAPET_WIDTH_M, total_half_w * 0.25)

        def off(i: int, lat_m: float, z: float) -> tuple[float, float, float]:
            px, py = pts[i]
            rx, ry = normals[i]
            return (px + rx * lat_m, py + ry * lat_m, z)

        for i in range(len(pts) - 1):
            # 1. Main deck top surface (walkable/drivable solid collision)
            l0_t = off(i, -total_half_w, z_tops[i])
            r0_t = off(i, total_half_w, z_tops[i])
            r1_t = off(i + 1, total_half_w, z_tops[i + 1])
            l1_t = off(i + 1, -total_half_w, z_tops[i + 1])
            builder.add_quad(l0_t, r0_t, r1_t, l1_t, deck_top_color)

            # 2. Deck underside (facing -Z)
            l0_b = off(i, -total_half_w, z_bots[i])
            r0_b = off(i, total_half_w, z_bots[i])
            r1_b = off(i + 1, total_half_w, z_bots[i + 1])
            l1_b = off(i + 1, -total_half_w, z_bots[i + 1])
            builder.add_quad(r0_b, l0_b, l1_b, r1_b, side_color)

            # 3. Visible left and right structural side faces (z_bot -> z_top)
            builder.add_quad(r0_b, r1_b, r1_t, r0_t, side_color)
            builder.add_quad(l1_b, l0_b, l0_t, l1_t, side_color)

            # 4. Left & right parapets (1.0 m above outer deck/sidewalk edge); wooden bridges get timber railings
            if material_kind == "wood":
                continue
            for lat_lo, lat_hi in (
                (-total_half_w, -total_half_w + para_w),
                (total_half_w - para_w, total_half_w),
            ):
                pb0_l = off(i, lat_lo, z_tops[i])
                pb0_r = off(i, lat_hi, z_tops[i])
                pb1_r = off(i + 1, lat_hi, z_tops[i + 1])
                pb1_l = off(i + 1, lat_lo, z_tops[i + 1])

                pt0_l = off(i, lat_lo, z_para_tops[i])
                pt0_r = off(i, lat_hi, z_para_tops[i])
                pt1_r = off(i + 1, lat_hi, z_para_tops[i + 1])
                pt1_l = off(i + 1, lat_lo, z_para_tops[i + 1])

                # Top, right, left of parapet
                builder.add_quad(pt0_l, pt0_r, pt1_r, pt1_l, parapet_color)
                builder.add_quad(pb0_r, pb1_r, pt1_r, pt0_r, parapet_color)
                builder.add_quad(pb1_l, pb0_l, pt0_l, pt1_l, parapet_color)

        # 5. Parapet end caps + vertical abutment end walls extending down into embankment
        for end_idx, is_start in ((0, True), (len(pts) - 1, False)):
            ex, ey = pts[end_idx]
            terr_z = elevation.sample(ex, ey)
            skirt_bot = min(z_bots[end_idx] - BRIDGE_ABUTMENT_SKIRT_M, terr_z - 0.35)
            l_top = off(end_idx, -total_half_w, z_tops[end_idx])
            r_top = off(end_idx, total_half_w, z_tops[end_idx])
            l_sk = off(end_idx, -total_half_w, skirt_bot)
            r_sk = off(end_idx, total_half_w, skirt_bot)
            if is_start:
                builder.add_quad(l_sk, r_sk, r_top, l_top, side_color)
            else:
                builder.add_quad(r_sk, l_sk, l_top, r_top, side_color)

            # Parapet end caps (stone parapets only)
            if material_kind == "wood":
                continue
            for lat_lo, lat_hi in (
                (-total_half_w, -total_half_w + para_w),
                (total_half_w - para_w, total_half_w),
            ):
                p_bl = off(end_idx, lat_lo, z_tops[end_idx])
                p_br = off(end_idx, lat_hi, z_tops[end_idx])
                p_tr = off(end_idx, lat_hi, z_para_tops[end_idx])
                p_tl = off(end_idx, lat_lo, z_para_tops[end_idx])
                if is_start:
                    builder.add_quad(p_bl, p_br, p_tr, p_tl, parapet_color)
                else:
                    builder.add_quad(p_br, p_bl, p_tl, p_tr, parapet_color)

        # Bridge footprint polygon (flat cap so it stays strictly over the bridge span)
        line = LineString(chain.coords)
        railing = "solid_parapet"
        if material_kind == "wood":
            wood_water = [wl for wpoly, wl in water_surfaces if wpoly.intersects(line.buffer(total_half_w))]
            _add_timber_details(builder, chain, pts, cum_s, normals, z_tops, z_bots, total_half_w, elevation,
                                max(wood_water) if wood_water else None)
            railing = "timber_posts_rails"
        fp = line.buffer(total_half_w, quad_segs=2, cap_style="flat")
        if fp.geom_type == "Polygon" and not fp.is_empty:
            footprints.append(fp)

        # Clearance calculations over water and terrain along the clear span
        cross_water_levels = [
            wl for wpoly, wl in water_surfaces if wpoly.intersects(fp)
        ]
        if cross_water_levels:
            water_level_m = max(cross_water_levels)
            water_level_source = "intersecting_waterbody"
        elif water_surfaces:
            # Narrow channels (e.g. Alte Elde under Steinbrücke) may be mapped as lines rather than water polygons;
            # reference the nearest waterbody level so clearance over water is still reported transparently.
            nearest_wpoly, nearest_wl = min(water_surfaces, key=lambda item: item[0].distance(fp))
            water_level_m = nearest_wl
            water_level_source = "nearest_waterbody_reference"
        else:
            water_level_m = None
            water_level_source = "none"

        clearance_over_water_m = None
        clearance_over_terrain_m = None
        min_deck_bot = min(z_bots)
        max_deck_top = max(z_tops)

        interior_clear_water = []
        midspan_clear_terr = []
        n_check = max(6, int(ceil(chain.length_m / 1.0)))
        for k in range(n_check + 1):
            frac = k / n_check
            s = frac * chain.length_m
            pt = line.interpolate(s)
            z_bot = chain.ground_elevation_at_s(s) + road_offset_m - BRIDGE_DECK_THICKNESS_M
            if 0.30 <= frac <= 0.70:
                midspan_clear_terr.append(z_bot - elevation.sample(pt.x, pt.y))
            for wpoly, wl in water_surfaces:
                if wpoly.contains(pt):
                    interior_clear_water.append(z_bot - wl)

        if interior_clear_water:
            clearance_over_water_m = round(min(interior_clear_water), 3)
        elif water_level_m is not None:
            clearance_over_water_m = round(min_deck_bot - water_level_m, 3)

        if midspan_clear_terr:
            # Clear opening height under the bridge midspan (over channel/moat floor)
            clearance_over_terrain_m = round(max(midspan_clear_terr), 3)

        # Optional Sprint 12 historic bridge details (stone arches & piers) from versioned landmark config
        detail_cfg = bridge_details_config.get(chain.id)
        detail_style = None
        if detail_cfg is not None:
            detail_style = detail_cfg.get("detail_style")
            _add_stone_bridge_arches_and_piers(
                builder, chain, total_half_w, road_offset_m, elevation, water_level_m, detail_cfg,
            )

        ab_a, ab_b = chain.abutments
        mid_s = 0.5 * chain.length_m
        mid_pt = line.interpolate(mid_s)
        mid_z = chain.ground_elevation_at_s(mid_s) + road_offset_m
        report_entries.append({
            "id": chain.id,
            "way_ids": chain.way_ids,
            "name": chain.name,
            "highway": chain.highway,
            "bridge_structure": chain.bridge_structure,
            "detail_style": detail_style,
            "material": material_kind,
            "material_source": material_source,
            "length_m": round(chain.length_m, 2),
            "width_m": round(chain.width_m, 2),
            "sidewalk_width_m": round(sw_width, 2),
            "total_width_m": round(total_half_w * 2.0, 2),
            "deck_thickness_m": BRIDGE_DECK_THICKNESS_M,
            "parapet_height_m": BRIDGE_PARAPET_HEIGHT_M,
            "railing": railing,
            "dimensions_source": "assumed_sprint11_1_bridge_defaults",
            "max_slope_percent": chain.max_slope_percent,
            "incline": chain.incline,
            "warnings": list(chain.warnings),
            "min_deck_bottom_m": round(min_deck_bot, 4),
            "max_deck_top_m": round(max_deck_top, 4),
            "mid_point_3d_m": [round(mid_pt.x, 4), round(mid_pt.y, 4), round(mid_z, 4)],
            "water_level_m": round(water_level_m, 4) if water_level_m is not None else None,
            "water_level_source": water_level_source,
            "clearance_over_water_m": clearance_over_water_m,
            "clearance_over_terrain_m": clearance_over_terrain_m,
            "abutments": [
                {
                    "position_m": [ab.position_xy[0], ab.position_xy[1], round(ab.ground_z_m + road_offset_m, 4)],
                    "ground_z_m": ab.ground_z_m,
                    "elevation_nhn_m": round(elevation.local_to_nhn(ab.ground_z_m), 4),
                    "source": ab.source,
                    "connected_road_ids": ab.connected_road_ids,
                }
                for ab in (ab_a, ab_b)
            ],
        })

    # 6. Configured historic tunnel portals & walkable passages (e.g. NW-Steg fortress rampart portal)
    for tunnel in tunnels or []:
        p_cfg = tunnel_portals_config.get(tunnel.road_id)
        if p_cfg is None:
            continue
        corridor_poly, floor_z, p_rep = _add_fortress_tunnel_portal_and_passage(
            builder, tunnel, road_offset_m, p_cfg, elevation,
        )
        tunnel_corridors.append((corridor_poly, floor_z))
        tunnel_portals_report.append(p_rep)

    if not builder.triangles:
        return None, report_entries, footprints, tunnel_corridors, tunnel_portals_report

    mesh_dict = {
        "color": None,
        "collision": True,
        "vertices": builder.vertices,
        "triangles": builder.triangles,
        "vertex_colors": builder.vertex_colors,
    }
    return mesh_dict, report_entries, footprints, tunnel_corridors, tunnel_portals_report
