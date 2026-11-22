"""Generate 3D bridge deck, parapet/railing, and abutment geometry for SM_Bridges."""

from __future__ import annotations

from math import ceil, hypot

from shapely.geometry import LineString, Point, Polygon

from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.road_elevation import BridgeChain, _densify_polyline


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


def build_bridges_mesh(
    bridges: list[BridgeChain],
    elevation: ElevationModel,
    road_offset_m: float,
    curb_height_m: float,
    sidewalk_widths: dict[str, float],
    default_sidewalk_widths: dict[str, float],
    water_surfaces: list[tuple[Polygon, float]],
) -> tuple[dict | None, list[dict], list[Polygon]]:
    """
    Build SM_Bridges vertex-colored mesh (with collision), bridge clearance report,
    and bridge footprint polygons (for excluding props/trees/terrain depression under bridges).
    """
    builder = _ColoredMeshBuilder()
    report_entries: list[dict] = []
    footprints: list[Polygon] = []

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

    if not builder.triangles:
        return None, report_entries, footprints

    mesh_dict = {
        "color": None,
        "collision": True,
        "vertices": builder.vertices,
        "triangles": builder.triangles,
        "vertex_colors": builder.vertex_colors,
    }
    return mesh_dict, report_entries, footprints
