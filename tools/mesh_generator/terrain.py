"""Generate simplified, crack-free, tiled TIN terrain meshes from the DGM1 elevation grid."""

from __future__ import annotations

from math import ceil, hypot
from typing import Callable

import numpy as np
import shapely
from shapely import constrained_delaunay_triangles, contains_xy, delaunay_triangles, get_coordinates, orient_polygons
import shapely.ops
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.prepared import prep

from tools.geo_transform.terrain import ElevationModel


DEFAULT_TILE_SIZE_M = 64
DEFAULT_MAX_ERROR_M = 0.05
DEFAULT_MAX_TRIANGLES = 150000


def _clip_triangle_at_step(tri_xyz, clips):
    """Split a terrain triangle crossed by a retaining wall line; new vertices take crest (high) or foot (low)."""
    xs = [p[0] for p in tri_xyz]
    ys = [p[1] for p in tri_xyz]
    for step, line_prep, lb in clips:
        if max(xs) < lb[0] or min(xs) > lb[2] or max(ys) < lb[1] or min(ys) > lb[3]:
            continue
        tri = Polygon([(p[0], p[1]) for p in tri_xyz])
        if abs(tri.area) < 1e-9 or not line_prep.intersects(tri):
            continue
        # extend the line a little so it cuts through triangles at its ends
        coords = list(step.line.coords)
        (x0, y0), (x1, y1) = coords[0], coords[1]
        (xa, ya), (xb, yb) = coords[-2], coords[-1]
        d0 = hypot(x1 - x0, y1 - y0) or 1.0
        d1 = hypot(xb - xa, yb - ya) or 1.0
        ext = LineString([(x0 - (x1 - x0) / d0 * 0.5, y0 - (y1 - y0) / d0 * 0.5)] + coords +
                         [(xb + (xb - xa) / d1 * 0.5, yb + (yb - ya) / d1 * 0.5)])
        parts = shapely.ops.split(tri, ext)
        if len(parts.geoms) < 2:
            return None
        (px0, py0, pz0), (px1, py1, pz1), (px2, py2, pz2) = tri_xyz
        det = (py1 - py2) * (px0 - px2) + (px2 - px1) * (py0 - py2)

        def plane(x, y):
            if abs(det) < 1e-12:
                return pz0
            w0 = ((py1 - py2) * (x - px2) + (px2 - px1) * (y - py2)) / det
            w1 = ((py2 - py0) * (x - px2) + (px0 - px2) * (y - py2)) / det
            return w0 * pz0 + w1 * pz1 + (1.0 - w0 - w1) * pz2

        originals = {(round(p[0], 6), round(p[1], 6)): p[2] for p in tri_xyz}
        out = []
        for part in parts.geoms:
            if part.area < 1e-6:
                continue
            rp = part.representative_point()
            high = step.side(rp.x, rp.y) > 0
            for sub in orient_polygons(constrained_delaunay_triangles(part)).geoms:
                pts = []
                for x, y in list(sub.exterior.coords)[:3]:
                    key = (round(x, 6), round(y, 6))
                    if key in originals:
                        z = originals[key]
                    elif step.in_gap(x, y) or step.line.distance(Point(x, y)) > 0.05:
                        z = plane(x, y)
                    elif high:
                        z = max(plane(x, y), step.at(step.top_z, x, y) - 0.03)
                    else:
                        z = min(plane(x, y), step.at(step.base_z, x, y) + 0.05)
                    pts.append((round(x, 4), round(y, 4), round(z, 4)))
                out.append(pts)
        return out
    return None


def _clip_triangle_at_wall(tri_xyz, clips):
    """
    Split a terrain triangle that crosses a fortress wall line into its inside and outside parts. New vertices
    on the wall line take the wall crest (inside) or the wall foot level (outside), so the wall face hides a
    clean step instead of a slanted triangle. At wall openings the original plane is kept on both sides.
    """
    xs = [p[0] for p in tri_xyz]
    ys = [p[1] for p in tri_xyz]
    for prof, ring_prep, rb in clips:
        if max(xs) < rb[0] or min(xs) > rb[2] or max(ys) < rb[1] or min(ys) > rb[3]:
            continue
        tri = Polygon([(p[0], p[1]) for p in tri_xyz])
        if abs(tri.area) < 1e-9 or not ring_prep.intersects(tri):
            continue
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri_xyz
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)

        def plane(x, y):
            if abs(det) < 1e-12:
                return z0
            w0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / det
            w1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / det
            return w0 * z0 + w1 * z1 + (1.0 - w0 - w1) * z2

        originals = {(round(p[0], 6), round(p[1], 6)): p[2] for p in tri_xyz}
        out = []
        for part, inside in ((tri.intersection(prof.outline), True), (tri.difference(prof.outline), False)):
            polys = [part] if part.geom_type == "Polygon" else [g for g in getattr(part, "geoms", []) if g.geom_type == "Polygon"]
            for poly in polys:
                if poly.is_empty or poly.area < 1e-6:
                    continue
                for sub in orient_polygons(constrained_delaunay_triangles(poly)).geoms:
                    pts = []
                    for x, y in list(sub.exterior.coords)[:3]:
                        key = (round(x, 6), round(y, 6))
                        if key in originals:
                            z = originals[key]
                        elif prof.in_gap(x, y):
                            z = plane(x, y)
                        elif inside and prof.flat_z(x, y) is not None:
                            z = prof.flat_z(x, y)
                        elif inside:
                            z = max(plane(x, y), prof.top_at(x, y) - 0.03)
                        else:
                            s = prof.ring.project(Point(x, y))
                            z = min(plane(x, y), float(np.interp(s, prof.s_vals, prof.foot_z)) + 0.3)
                        pts.append((round(x, 4), round(y, 4), round(z, 4)))
                    out.append(pts)
        return out
    return None


def _clip_triangle_outside(tri_xyz, cuts):
    """
    Return None if the triangle does not touch any cut polygon, otherwise the CCW sub-triangles of the part
    outside all cut polygons (z from the original triangle plane, coordinates rounded like tile vertices).
    """
    xs = [p[0] for p in tri_xyz]
    ys = [p[1] for p in tri_xyz]
    tb = (min(xs), min(ys), max(xs), max(ys))
    hits = [c for c, b in cuts if not (b[2] < tb[0] or b[0] > tb[2] or b[3] < tb[1] or b[1] > tb[3])]
    if not hits:
        return None
    tri = Polygon([(p[0], p[1]) for p in tri_xyz])
    if not any(tri.intersects(c) for c in hits):
        return None
    rest = tri
    for c in hits:
        rest = rest.difference(c)
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri_xyz
    det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)

    def z_at(x, y):
        if abs(det) < 1e-12:
            return z0
        w0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / det
        w1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / det
        return w0 * z0 + w1 * z1 + (1.0 - w0 - w1) * z2

    out = []
    parts = [rest] if rest.geom_type == "Polygon" else [g for g in getattr(rest, "geoms", []) if g.geom_type == "Polygon"]
    for part in parts:
        if part.is_empty or part.area < 1e-6:
            continue
        for sub in orient_polygons(constrained_delaunay_triangles(part)).geoms:
            pts = list(sub.exterior.coords)[:3]
            out.append([(round(x, 4), round(y, 4), round(z_at(x, y), 4)) for x, y in pts])
    return out


def _rasterize_mask(
    polygons: list[Polygon],
    e_coords: np.ndarray,
    n_coords: np.ndarray,
) -> np.ndarray:
    """Fast deterministic rasterization of polygon union onto a 2D (rows, cols) grid."""
    rows = len(n_coords)
    cols = len(e_coords)
    mask = np.zeros((rows, cols), dtype=np.bool_)
    if not polygons:
        return mask
    for poly in polygons:
        if poly.is_empty:
            continue
        min_e, min_n, max_e, max_n = poly.bounds
        c0 = max(0, int(np.searchsorted(e_coords, min_e, side="left")) - 1)
        c1 = min(cols, int(np.searchsorted(e_coords, max_e, side="right")) + 1)
        r0 = max(0, int(np.searchsorted(n_coords, min_n, side="left")) - 1)
        r1 = min(rows, int(np.searchsorted(n_coords, max_n, side="right")) + 1)
        if c0 >= c1 or r0 >= r1:
            continue
        ee, nn = np.meshgrid(e_coords[c0:c1], n_coords[r0:r1])
        sub = contains_xy(poly, ee, nn)
        if np.any(sub):
            mask[r0:r1, c0:c1] |= sub
    return mask


def _dp_1d(vals: np.ndarray, tol: float, active: np.ndarray | None = None) -> list[int]:
    """Deterministic 1D Douglas-Peucker returning sorted indices in [0, len(vals) - 1]."""
    n = len(vals)
    if n <= 2:
        return list(range(n))
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a <= 1:
            continue
        t = np.linspace(0.0, 1.0, b - a + 1)
        line = vals[a] + t * (vals[b] - vals[a])
        errs = np.abs(vals[a : b + 1] - line)
        if active is not None:
            errs = np.where(active[a : b + 1], errs, -1.0)
        idx = int(np.argmax(errs))
        if float(errs[idx]) > tol:
            m = a + idx
            keep.add(m)
            stack.append((a, m))
            stack.append((m, b))
    return sorted(keep)


def _extract_triangles_xy(pts: list[tuple[int, int]]) -> list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]]:
    """Run deterministic 2D Delaunay triangulation on integer tile coordinates and return sorted triangle tuples."""
    gc = delaunay_triangles(MultiPoint(pts))
    coords = get_coordinates(gc)
    if coords.size == 0:
        return []
    # Each triangle polygon in GEOS has 4 coordinates (p0, p1, p2, p0)
    tri_coords = np.rint(coords).astype(np.int64).reshape(-1, 4, 2)
    out = []
    for tri in tri_coords:
        p0 = (int(tri[0, 0]), int(tri[0, 1]))
        p1 = (int(tri[1, 0]), int(tri[1, 1]))
        p2 = (int(tri[2, 0]), int(tri[2, 1]))
        out.append((p0, p1, p2))
    return out


def _build_tile_tin(
    raw_z_sub: np.ndarray,
    mesh_z_sub: np.ndarray,
    open_mask_sub: np.ndarray,
    ceiling_z_sub: np.ndarray,
    has_ceiling_sub: np.ndarray,
    seed_pts: set[tuple[int, int]],
    tol_m: float,
) -> tuple[list[tuple[int, int]], list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]], float]:
    """
    Deterministic batch greedy-insertion TIN on a single tile.
    - Simplifies smooth raw_z so |z_tin - raw_z| <= tol_m on all open (non-depressed) grid cells.
    - Ensures lowered mesh_z triangles stay below depressed ceilings (water/roads/sidewalks).
    - Keeps boundary vertices fixed to seed_pts (zero cracks across adjacent tiles).
    """
    pts_set = set(seed_pts)
    pts = sorted(pts_set)
    # Cache per triangle (sorted 3 vertices): (max_open_err, worst_insert_pt_or_None)
    cache: dict[tuple[tuple[int, int], tuple[int, int], tuple[int, int]], tuple[float, tuple[int, int] | None]] = {}

    triangles: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]] = []
    verified_open_err = 0.0

    for _ in range(28):
        triangles = _extract_triangles_xy(pts)
        max_open_err = 0.0
        to_add: list[tuple[int, int]] = []

        for p0, p1, p2 in triangles:
            key = tuple(sorted((p0, p1, p2)))
            cached = cache.get(key)
            if cached is None:
                x0, y0 = p0
                x1, y1 = p1
                x2, y2 = p2
                bx0, bx1 = min(x0, x1, x2), max(x0, x1, x2)
                by0, by1 = min(y0, y1, y2), max(y0, y1, y2)
                if bx1 - bx0 <= 1 and by1 - by0 <= 1:
                    cached = (0.0, None)
                else:
                    det = float((y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2))
                    if abs(det) < 1e-9:
                        cached = (0.0, None)
                    else:
                        xs = np.arange(bx0, bx1 + 1, dtype=np.float64)[None, :]
                        ys = np.arange(by0, by1 + 1, dtype=np.float64)[:, None]
                        l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / det
                        l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / det
                        l2 = 1.0 - l0 - l1
                        inside = (l0 >= -1e-7) & (l1 >= -1e-7) & (l2 >= -1e-7)
                        if not np.any(inside):
                            cached = (0.0, None)
                        else:
                            # Evaluate open-ground accuracy on smooth raw_z (no artificial cliff splits at curbs/walls)
                            z_pred_raw = (
                                l0 * raw_z_sub[y0, x0]
                                + l1 * raw_z_sub[y1, x1]
                                + l2 * raw_z_sub[y2, x2]
                            )
                            sub_open = open_mask_sub[by0 : by1 + 1, bx0 : bx1 + 1] & inside
                            open_err = 0.0
                            worst_pt = None
                            if np.any(sub_open):
                                errs = np.where(
                                    sub_open,
                                    np.abs(raw_z_sub[by0 : by1 + 1, bx0 : bx1 + 1] - z_pred_raw),
                                    -1.0,
                                )
                                fi = int(np.argmax(errs))
                                open_err = float(errs.flat[fi])
                                if open_err > tol_m:
                                    ry, rx = divmod(fi, bx1 - bx0 + 1)
                                    worst_pt = (bx0 + rx, by0 + ry)

                            # Also verify depressed mesh_z never pokes above water/road surfaces
                            if worst_pt is None:
                                sub_ceil = has_ceiling_sub[by0 : by1 + 1, bx0 : bx1 + 1] & inside
                                if np.any(sub_ceil):
                                    z_pred_dep = (
                                        l0 * mesh_z_sub[y0, x0]
                                        + l1 * mesh_z_sub[y1, x1]
                                        + l2 * mesh_z_sub[y2, x2]
                                    )
                                    overshoot = np.where(
                                        sub_ceil,
                                        z_pred_dep - ceiling_z_sub[by0 : by1 + 1, bx0 : bx1 + 1],
                                        -1.0,
                                    )
                                    fi = int(np.argmax(overshoot))
                                    if float(overshoot.flat[fi]) > 0.02:
                                        ry, rx = divmod(fi, bx1 - bx0 + 1)
                                        worst_pt = (bx0 + rx, by0 + ry)

                            cached = (open_err, worst_pt)
                cache[key] = cached

            tri_err, cand = cached
            if tri_err > max_open_err:
                max_open_err = tri_err
            if cand is not None and cand not in pts_set:
                to_add.append(cand)

        verified_open_err = max_open_err
        if not to_add:
            break
        pts_set.update(to_add)
        pts = sorted(pts_set)

    return pts, triangles, verified_open_err


def build_terrain_tiles(
    elevation: ElevationModel,
    bounds: Polygon,
    water_surfaces: list[tuple[Polygon, float]],
    road_polygons: list[Polygon],
    sidewalk_polygons: list[Polygon],
    building_entries: list[tuple[Polygon, float]],
    road_ground_z_fn: Callable[[float, float], float] | None = None,
    bridge_polygons: list[Polygon] | None = None,
    tunnel_corridors: list[tuple[Polygon, float]] | None = None,
    interior_floors: list[tuple[Polygon, float]] | None = None,
    fortress_profiles: list | None = None,
    wall_steps: list | None = None,
    portal_aprons: list | None = None,
    tile_size_m: int = DEFAULT_TILE_SIZE_M,
    max_error_m: float = DEFAULT_MAX_ERROR_M,
    max_triangles: int = DEFAULT_MAX_TRIANGLES,
) -> tuple[dict[str, dict], dict]:
    """
    Build simplified, crack-free 64 m TIN terrain mesh tiles from DGM1.
    Guarantees <= max_error_m vertical error on all open terrain, depression beneath
    water/roads/sidewalks/buildings to avoid Z-fighting, and <= max_triangles total.
    """
    min_e, min_n, max_e, max_n = bounds.bounds
    if elevation.is_flat:
        return {}, {
            "kind": "flat_placeholder",
            "tile_size_m": tile_size_m,
            "tile_count": 1,
            "triangle_count": 2,
            "max_vertical_error_m": 0.0,
            "max_error_budget_m": max_error_m,
            "max_triangles_budget": max_triangles,
            "depressed_cells": 0,
        }

    tile_size = int(tile_size_m)
    if tile_size <= 0:
        raise ValueError(f"tile_size_m must be positive, got {tile_size}")

    span_e = max_e - min_e
    span_n = max_n - min_n
    max_gx = int(ceil(span_e))
    max_gy = int(ceil(span_n))
    n_tiles_x = max(1, int(ceil(max_gx / tile_size)))
    n_tiles_y = max(1, int(ceil(max_gy / tile_size)))

    e_coords = np.minimum(max_e, min_e + np.arange(max_gx + 1, dtype=np.float64))
    n_coords = np.minimum(max_n, min_n + np.arange(max_gy + 1, dtype=np.float64))
    ee, nn = np.meshgrid(e_coords, n_coords)

    raw_z = elevation.sample_array(ee, nn)
    # 0. Sprint 13: fill the rampart behind a fortress escarp up to the wall crest (DGM1 models the brick
    # revetment as a slope). Inside the outline, within fill_band_m of the wall: full fill up to 2 m, then a
    # linear blend back to the DGM. Applied to raw_z, so the 5 cm TIN tolerance refers to the filled surface.
    for prof in fortress_profiles or []:
        band = float(prof.fill_band_m)
        inside = _rasterize_mask([prof.outline], e_coords, n_coords)
        core = prof.outline.buffer(-band, join_style="mitre")
        if not core.is_empty:
            inside &= ~_rasterize_mask([core] if core.geom_type == "Polygon" else list(core.geoms), e_coords, n_coords)
        ys, xs = np.nonzero(inside)
        if len(ys) == 0:
            continue
        px = e_coords[xs]
        py = n_coords[ys]
        pts = shapely.points(px, py)
        dist = shapely.distance(prof.ring, pts)
        s_proj = shapely.line_locate_point(prof.ring, pts)
        target = np.interp(s_proj, prof.s_vals, prof.top_z) - 0.03
        w = np.clip((band - dist) / max(band - 2.0, 1e-6), 0.0, 1.0)
        cur = raw_z[ys, xs]
        filled = np.maximum(cur, cur * (1.0 - w) + target * w)
        raw_z[ys, xs] = filled
        # level courts inside the outline (gate forecourt between escarp and gate wall)
        for zone_poly, zone_z in prof.flat_zones or []:
            zmask_f = _rasterize_mask([zone_poly.buffer(0.6, join_style="mitre")], e_coords, n_coords)
            raw_z[zmask_f] = zone_z
        # Outside the wall: the DGM revetment slope reaches up to 3 m into the moat; the wall rises from the
        # moat floor, so lower that band to the wall foot level (+0.3 m) except at openings (gate, steg).
        out_band = prof.outline.buffer(3.0, join_style="mitre").difference(prof.outline)
        omask = _rasterize_mask([out_band] if out_band.geom_type == "Polygon" else list(out_band.geoms), e_coords, n_coords)
        oys, oxs = np.nonzero(omask)
        if len(oys):
            opts = shapely.points(e_coords[oxs], n_coords[oys])
            os_proj = shapely.line_locate_point(prof.ring, opts)
            ofoot = np.interp(os_proj, prof.s_vals, prof.foot_z) + 0.3
            length = prof.ring.length
            gap_hit = np.zeros(len(oys), dtype=bool)
            for g0, g1 in prof.gaps or []:
                for off in (0.0, length, -length):
                    gap_hit |= (os_proj >= g0 + off - 2.0) & (os_proj <= g1 + off + 2.0)
            low = ~gap_hit
            raw_z[oys[low], oxs[low]] = np.minimum(raw_z[oys[low], oxs[low]], ofoot[low])
    # 0b. Retaining walls from OSM (walls.py): fill the high side up to the crest, lower the low side to the foot
    for step in wall_steps or []:
        zone = step.line.buffer(max(step.fill_band_m, step.low_band_m), cap_style="flat")
        zmask = _rasterize_mask([zone], e_coords, n_coords)
        zys, zxs = np.nonzero(zmask)
        if len(zys) == 0:
            continue
        zp = shapely.points(e_coords[zxs], n_coords[zys])
        dist = shapely.distance(step.line, zp)
        s_proj = shapely.line_locate_point(step.line, zp)
        top_v = np.interp(s_proj, step.s_vals, step.top_z) - 0.03
        base_v = np.interp(s_proj, step.s_vals, step.base_z) + 0.05
        sides = np.array([step.side(float(x), float(y)) for x, y in zip(e_coords[zxs], n_coords[zys])])
        in_gap = np.zeros(len(zys), dtype=bool)
        for g0, g1 in step.gaps:
            # up to the gap edge: the wall end sits inside a portal block or is closed by an end cap
            in_gap |= (s_proj >= g0) & (s_proj <= g1)
        cur = raw_z[zys, zxs]
        w_hi = np.clip((step.fill_band_m - dist) / max(step.fill_band_m - 1.5, 1e-6), 0.0, 1.0)
        hi = (sides > 0) & ~in_gap
        lo = (sides < 0) & ~in_gap & (dist <= step.low_band_m)
        new = cur.copy()
        new[hi] = np.maximum(cur[hi], cur[hi] * (1.0 - w_hi[hi]) + top_v[hi] * w_hi[hi])
        new[lo] = np.minimum(cur[lo], base_v[lo])
        raw_z[zys, zxs] = new
    # 0c. Level aprons in front of passage portals (terrain is only lowered, never raised)
    for apron_poly, apron_z in portal_aprons or []:
        amask = _rasterize_mask([apron_poly], e_coords, n_coords)
        raw_z[amask] = np.minimum(raw_z[amask], apron_z)
    mesh_z = raw_z.copy()
    step_clip = [(step, prep(step.line), step.line.bounds) for step in (wall_steps or [])]
    fortress_clip = [
        (prof, prep(prof.ring), prof.ring.bounds) for prof in (fortress_profiles or [])
    ]
    depressed = np.zeros((max_gy + 1, max_gx + 1), dtype=np.bool_)
    has_ceiling = np.zeros((max_gy + 1, max_gx + 1), dtype=np.bool_)
    ceiling_z = np.full((max_gy + 1, max_gx + 1), np.inf, dtype=np.float64)

    # 1. Depress terrain under water bodies strictly below fixed water level
    for water_poly, water_level_m in water_surfaces:
        wmask = _rasterize_mask([water_poly], e_coords, n_coords)
        if np.any(wmask):
            mesh_z[wmask] = np.minimum(mesh_z[wmask], water_level_m - 0.50)
            ceiling_z[wmask] = np.minimum(ceiling_z[wmask], water_level_m - 0.06)
            has_ceiling |= wmask
            depressed |= wmask

    # 2. Depress terrain under roads and sidewalks to eliminate Z-fighting
    road_sw_mask = _rasterize_mask([*road_polygons, *sidewalk_polygons], e_coords, n_coords)
    if np.any(road_sw_mask):
        ys, xs = np.nonzero(road_sw_mask)
        if road_ground_z_fn is not None:
            for r, c in zip(ys.tolist(), xs.tolist()):
                rg = road_ground_z_fn(float(e_coords[c]), float(n_coords[r]))
                mesh_z[r, c] = min(mesh_z[r, c], rg - 0.14)
                ceiling_z[r, c] = min(ceiling_z[r, c], rg + 0.05)
        else:
            mesh_z[road_sw_mask] -= 0.14
            ceiling_z[road_sw_mask] = np.minimum(ceiling_z[road_sw_mask], raw_z[road_sw_mask] + 0.05)
        has_ceiling |= road_sw_mask
        depressed |= road_sw_mask

    # 2b. Under bridge footprints, keep canal/moat floor 100% untouched, but clamp embankment crests
    # that rise above the linear bridge deck so bare-earth DGM1 never pokes through a bridge deck.
    if bridge_polygons and road_ground_z_fn is not None:
        padded_bridges = [
            poly.buffer(0.75, quad_segs=1, cap_style="flat")
            for poly in bridge_polygons
            if not poly.is_empty
        ]
        bridge_mask = _rasterize_mask(padded_bridges, e_coords, n_coords)
        if np.any(bridge_mask):
            ys, xs = np.nonzero(bridge_mask)
            for r, c in zip(ys.tolist(), xs.tolist()):
                rg = road_ground_z_fn(float(e_coords[c]), float(n_coords[r]))
                if mesh_z[r, c] > rg - 0.14:
                    mesh_z[r, c] = rg - 0.14
                    ceiling_z[r, c] = min(ceiling_z[r, c], rg + 0.02)
                    has_ceiling[r, c] = True
                    depressed[r, c] = True

    # 3. Depress & cut out terrain strictly inside building footprints (inset 0.40 m so plinths meet ground seamlessly)
    building_cut_mask = np.zeros((max_gy + 1, max_gx + 1), dtype=np.bool_)
    for bpoly, b_min_z in building_entries:
        inset = bpoly.buffer(-0.40)
        if inset.is_empty:
            continue
        parts = [inset] if inset.geom_type == "Polygon" else list(getattr(inset, "geoms", []))
        bmask = _rasterize_mask([p for p in parts if p.geom_type == "Polygon"], e_coords, n_coords)
        if np.any(bmask):
            mesh_z[bmask] = np.minimum(mesh_z[bmask], b_min_z - 0.15)
            building_cut_mask |= bmask
            depressed |= bmask

    # 3b. Cut out & depress terrain along walkable tunnel corridors (e.g. NW-Steg fortress rampart passage)
    # so the earthen hillside never blocks the walkable vaulted brick tunnel bore.
    for tpoly, t_floor_z in tunnel_corridors or []:
        if tpoly.is_empty:
            continue
        parts = [tpoly] if tpoly.geom_type == "Polygon" else list(getattr(tpoly, "geoms", []))
        tmask = _rasterize_mask([p for p in parts if p.geom_type == "Polygon"], e_coords, n_coords)
        if np.any(tmask):
            mesh_z[tmask] = np.minimum(mesh_z[tmask], t_floor_z - 0.14)
            ceiling_z[tmask] = np.minimum(ceiling_z[tmask], t_floor_z - 0.04)
            has_ceiling |= tmask
            building_cut_mask |= tmask
            depressed |= tmask

    # 3c. Walk-in interiors (Sprint 13): terrain triangles are clipped exactly at the outer wall below (see
    # _clip_triangle_outside). Under ordinary buildings large TIN triangles may rise up the slope inside the
    # footprint because the walls hide them; inside a room they would poke through the floor.
    interior_cuts = [
        (fpoly.buffer(-0.05, join_style="mitre"), fpoly.buffer(-0.05, join_style="mitre").bounds)
        for fpoly, _ in (interior_floors or [])
    ]
    if interior_cuts:
        building_cut_mask |= _rasterize_mask([c for c, _ in interior_cuts], e_coords, n_coords)

    # Open terrain points: strictly non-depressed
    open_mask = ~depressed
    edge_tol = max(0.005, max_error_m - 0.001)
    tin_tol = max(0.005, max_error_m - 0.0005)

    # Precompute deterministic shared tile-edge vertices on smooth raw_z so adjacent tiles match vertex-for-vertex (zero cracks!)
    h_edge_pts: dict[tuple[int, int], list[int]] = {}
    for ty in range(n_tiles_y + 1):
        gy = min(max_gy, ty * tile_size)
        for tx in range(n_tiles_x):
            x0 = tx * tile_size
            x1 = min(max_gx, (tx + 1) * tile_size)
            if x1 <= x0:
                continue
            h_edge_pts[(tx, ty)] = _dp_1d(raw_z[gy, x0 : x1 + 1], edge_tol, open_mask[gy, x0 : x1 + 1])

    v_edge_pts: dict[tuple[int, int], list[int]] = {}
    for tx in range(n_tiles_x + 1):
        gx = min(max_gx, tx * tile_size)
        for ty in range(n_tiles_y):
            y0 = ty * tile_size
            y1 = min(max_gy, (ty + 1) * tile_size)
            if y1 <= y0:
                continue
            v_edge_pts[(tx, ty)] = _dp_1d(raw_z[y0 : y1 + 1, gx], edge_tol, open_mask[y0 : y1 + 1, gx])

    tile_meshes: dict[str, dict] = {}
    total_triangles = 0
    verified_max_open_err = 0.0

    for ty in range(n_tiles_y):
        y0 = ty * tile_size
        y1 = min(max_gy, (ty + 1) * tile_size)
        h = y1 - y0
        if h <= 0:
            continue
        for tx in range(n_tiles_x):
            x0 = tx * tile_size
            x1 = min(max_gx, (tx + 1) * tile_size)
            w = x1 - x0
            if w <= 0:
                continue

            seed_pts: set[tuple[int, int]] = {(0, 0), (w, 0), (0, h), (w, h)}
            for ix in h_edge_pts[(tx, ty)]:
                seed_pts.add((ix, 0))
            for ix in h_edge_pts[(tx, ty + 1)]:
                seed_pts.add((ix, h))
            for iy in v_edge_pts[(tx, ty)]:
                seed_pts.add((0, iy))
            for iy in v_edge_pts[(tx + 1, ty)]:
                seed_pts.add((w, iy))

            _, tri_list, tile_open_err = _build_tile_tin(
                raw_z_sub=raw_z[y0 : y1 + 1, x0 : x1 + 1],
                mesh_z_sub=mesh_z[y0 : y1 + 1, x0 : x1 + 1],
                open_mask_sub=open_mask[y0 : y1 + 1, x0 : x1 + 1],
                ceiling_z_sub=ceiling_z[y0 : y1 + 1, x0 : x1 + 1],
                has_ceiling_sub=has_ceiling[y0 : y1 + 1, x0 : x1 + 1],
                seed_pts=seed_pts,
                tol_m=tin_tol,
            )
            if tile_open_err > verified_max_open_err:
                verified_max_open_err = tile_open_err

            vertices: list[tuple[float, float, float]] = []
            v_map: dict[tuple[int, int], int] = {}
            triangles: list[tuple[int, int, int]] = []

            def get_v(lx: int, ly: int) -> int:
                key = (lx, ly)
                idx = v_map.get(key)
                if idx is None:
                    idx = len(vertices)
                    v_map[key] = idx
                    gx, gy = x0 + lx, y0 + ly
                    vertices.append((
                        round(float(e_coords[gx]), 4),
                        round(float(n_coords[gy]), 4),
                        round(float(mesh_z[gy, gx]), 4),
                    ))
                return idx

            for p0, p1, p2 in tri_list:
                # Cut out triangles lying completely inside solid building interiors
                gx0, gy0 = x0 + p0[0], y0 + p0[1]
                gx1, gy1 = x0 + p1[0], y0 + p1[1]
                gx2, gy2 = x0 + p2[0], y0 + p2[1]
                if building_cut_mask[gy0, gx0] and building_cut_mask[gy1, gx1] and building_cut_mask[gy2, gx2]:
                    cx_g = (gx0 + gx1 + gx2) // 3
                    cy_g = (gy0 + gy1 + gy2) // 3
                    if building_cut_mask[cy_g, cx_g]:
                        continue
                ax, ay = float(e_coords[gx0]), float(n_coords[gy0])
                bx, by = float(e_coords[gx1]), float(n_coords[gy1])
                cx, cy = float(e_coords[gx2]), float(n_coords[gy2])
                area2 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
                if abs(area2) < 1e-6:
                    continue
                if step_clip:
                    tri_s = [
                        (ax, ay, float(mesh_z[gy0, gx0])),
                        (bx, by, float(mesh_z[gy1, gx1])),
                        (cx, cy, float(mesh_z[gy2, gx2])),
                    ]
                    clipped_s = _clip_triangle_at_step(tri_s, step_clip)
                    if clipped_s is not None:
                        for sub in clipped_s:
                            base = len(vertices)
                            vertices.extend(sub)
                            triangles.append((base, base + 1, base + 2))
                        continue
                if fortress_clip:
                    tri_f = [
                        (ax, ay, float(mesh_z[gy0, gx0])),
                        (bx, by, float(mesh_z[gy1, gx1])),
                        (cx, cy, float(mesh_z[gy2, gx2])),
                    ]
                    clipped_f = _clip_triangle_at_wall(tri_f, fortress_clip)
                    if clipped_f is not None:
                        for sub in clipped_f:
                            base = len(vertices)
                            vertices.extend(sub)
                            triangles.append((base, base + 1, base + 2))
                        continue
                if interior_cuts:
                    tri_xyz = [
                        (ax, ay, float(mesh_z[gy0, gx0])),
                        (bx, by, float(mesh_z[gy1, gx1])),
                        (cx, cy, float(mesh_z[gy2, gx2])),
                    ]
                    clipped = _clip_triangle_outside(tri_xyz, interior_cuts)
                    if clipped is not None:
                        for sub in clipped:
                            base = len(vertices)
                            vertices.extend(sub)
                            triangles.append((base, base + 1, base + 2))
                        continue
                ia, ib, ic = get_v(*p0), get_v(*p1), get_v(*p2)
                if area2 > 0.0:
                    triangles.append((ia, ib, ic))
                else:
                    triangles.append((ia, ic, ib))

            if triangles:
                tile_name = f"Terrain_{tx:02d}_{ty:02d}"
                tile_meshes[tile_name] = {
                    "material": "Terrain",
                    "collision": True,
                    "vertices": vertices,
                    "triangles": triangles,
                }
                total_triangles += len(triangles)

    if total_triangles > max_triangles:
        raise ValueError(
            f"terrain mesh triangle count {total_triangles} exceeds budget {max_triangles}"
        )
    if verified_max_open_err > max_error_m + 1e-6:
        raise ValueError(
            f"terrain mesh max vertical error {verified_max_open_err:.4f} m exceeds budget {max_error_m:.4f} m"
        )

    report = {
        "kind": "dgm1",
        "tile_size_m": tile_size,
        "tile_grid": [n_tiles_x, n_tiles_y],
        "tile_count": len(tile_meshes),
        "triangle_count": total_triangles,
        "max_triangles_budget": max_triangles,
        "max_vertical_error_m": round(verified_max_open_err, 5),
        "max_error_budget_m": max_error_m,
        "depressed_cells": int(depressed.sum()),
    }
    return tile_meshes, report
