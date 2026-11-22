"""Generate 3D bridge deck, parapet/railing, and abutment geometry for SM_Bridges."""

from __future__ import annotations

from math import ceil, cos, hypot, pi, sin

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.road_elevation import BridgeChain, TunnelWayInfo, _densify_polyline


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
    n_arch = 6
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
        fwd = (-out_dir[0], -out_dir[1])          # points into the tunnel
        right = (fwd[1], -fwd[0])
        origin = pts[end_idx]
        p_depth = 0.75
        s_a, s_b = -p_depth, 0.0
        for lat_a, lat_b in ((-half_pw, -half_cw), (half_cw, half_pw)):
            _add_prism_along_axis(builder, origin, fwd, right, s_a, s_b, lat_a, lat_b,
                                  ze - 3.6, ze + portal_h, COLOR_TUNNEL_BRICK, add_top=True)
        _add_prism_along_axis(builder, origin, fwd, right, s_a, s_b, -half_cw, half_cw,
                              ze + clear_h - 0.15, ze + portal_h, COLOR_TUNNEL_BRICK, add_top=True)
        # Solid foundation under the threshold so the portal stands on a wall, not on two legs (NW-Steg moat edge)
        _add_prism_along_axis(builder, origin, fwd, right, s_a, s_b, -half_cw, half_cw,
                              ze - 3.6, ze - 0.03, COLOR_TUNNEL_BRICK, add_top=True)
        _add_prism_along_axis(builder, origin, fwd, right, s_a - 0.08, s_b + 0.08, -half_pw - 0.12, half_pw + 0.12,
                              ze + portal_h, ze + portal_h + 0.28, COLOR_TUNNEL_KEYSTONE, add_top=True)
        _add_prism_along_axis(builder, origin, fwd, right, s_a - 0.08, s_b + 0.08, -0.32, 0.32,
                              ze + clear_h - 0.25, ze + clear_h + 0.45, COLOR_TUNNEL_KEYSTONE, add_top=True)
        for side_lat in (-half_cw - 0.35, half_cw):
            _add_prism_along_axis(builder, origin, fwd, right, s_a - 0.06, s_b + 0.06, side_lat, side_lat + 0.35,
                                  ze + spring_h - 0.18, ze + spring_h + 0.14, COLOR_TUNNEL_KEYSTONE, add_top=True)

    corridor_poly = LineString(coords).buffer(corridor_half_w, quad_segs=1, cap_style="flat", join_style="mitre")
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

            # 4. Left & right parapets / railings (1.0 m above outer deck/sidewalk edge)
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

            # Parapet end caps
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
