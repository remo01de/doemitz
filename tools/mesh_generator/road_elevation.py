"""Smoothed longitudinal road elevation profiles and flat cross-section projection."""

from __future__ import annotations

from collections import defaultdict
from math import ceil, dist, hypot

import numpy as np
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.strtree import STRtree

from tools.geo_transform.terrain import ElevationModel


DEFAULT_SMOOTHING_WINDOW_M = 12.0
SAMPLE_STEP_M = 1.0


def _coord_key(xy) -> tuple[float, float]:
    return (round(float(xy[0]), 4), round(float(xy[1]), 4))


def _densify_polyline(coords: list[tuple[float, float]], step_m: float) -> tuple[list[tuple[float, float]], list[float]]:
    """Resample polyline so consecutive samples are at most step_m apart; return (points, cumulative_s)."""
    pts: list[tuple[float, float]] = [(float(coords[0][0]), float(coords[0][1]))]
    cum_s: list[float] = [0.0]
    for a, b in zip(coords, coords[1:]):
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        seg = hypot(bx - ax, by - ay)
        if seg <= 1e-6:
            continue
        n = max(1, int(ceil(seg / step_m)))
        base_s = cum_s[-1]
        for i in range(1, n + 1):
            t = i / n
            pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))
            cum_s.append(base_s + seg * t)
    return pts, cum_s


def _moving_average_1d(s_vals: np.ndarray, z_vals: np.ndarray, window_m: float) -> np.ndarray:
    """Distance-based moving average over [s - window/2, s + window/2]."""
    n = len(s_vals)
    if n <= 1 or window_m <= 0.0:
        return z_vals.copy()
    half = 0.5 * window_m
    out = np.empty(n, dtype=np.float64)
    left = 0
    right = 0
    running_sum = 0.0
    for i in range(n):
        si = s_vals[i]
        while right < n and s_vals[right] <= si + half + 1e-9:
            running_sum += z_vals[right]
            right += 1
        while left < right and s_vals[left] < si - half - 1e-9:
            running_sum -= z_vals[left]
            left += 1
        out[i] = running_sum / max(1, right - left)
    return out


class _RoadProfilePart:
    __slots__ = ("road_id", "name", "highway", "width_m", "line", "s_vals", "z_vals", "length_m", "max_slope_percent")

    def __init__(
        self,
        road_id: str,
        name: str,
        highway: str,
        width_m: float,
        line: LineString,
        s_vals: np.ndarray,
        z_vals: np.ndarray,
        max_slope_percent: float,
    ):
        self.road_id = road_id
        self.name = name
        self.highway = highway
        self.width_m = width_m
        self.line = line
        self.s_vals = s_vals
        self.z_vals = z_vals
        self.length_m = float(s_vals[-1]) if len(s_vals) else 0.0
        self.max_slope_percent = max_slope_percent

    def elevation_at_s(self, s_m: float) -> float:
        return float(np.interp(s_m, self.s_vals, self.z_vals))

    def elevation_at_xy(self, x: float, y: float) -> float:
        s = self.line.project(Point(x, y))
        return self.elevation_at_s(s)


class RoadElevationNetwork:
    """
    Smoothed longitudinal road elevation network with flat cross-sections.
    Every point on a road or adjacent sidewalk projects perpendicularly onto its road axis,
    guaranteeing flat transverse profiles and exact constant curb height (12 cm).
    """

    def __init__(
        self,
        elevation: ElevationModel,
        roads: list[dict],
        road_width_fn,
        road_offset_m: float,
        curb_height_m: float,
        smoothing_window_m: float = DEFAULT_SMOOTHING_WINDOW_M,
    ):
        self.elevation = elevation
        self.road_offset_m = float(road_offset_m)
        self.curb_height_m = float(curb_height_m)
        self.smoothing_window_m = max(10.0, float(smoothing_window_m))
        self.parts: list[_RoadProfilePart] = []
        self.parts_by_road_id: dict[str, list[_RoadProfilePart]] = defaultdict(list)
        self.road_reports: list[dict] = []

        if elevation.is_flat:
            self._tree = None
            return

        # 1. Collect all non-tunnel road polylines and identify shared junction vertices.
        raw_parts: list[tuple[dict, float, list[tuple[float, float]]]] = []
        vertex_uses: dict[tuple[float, float], int] = defaultdict(int)
        for road in roads:
            tags = road["properties"]
            if tags.get("tunnel", "no") != "no":
                continue
            width_m, _ = road_width_fn(tags)
            geom = shape(road["geometry"])
            lines = (
                [geom]
                if geom.geom_type == "LineString"
                else list(geom.geoms)
                if geom.geom_type == "MultiLineString"
                else []
            )
            for line in lines:
                coords = [(float(p[0]), float(p[1])) for p in line.coords]
                if len(coords) < 2:
                    continue
                raw_parts.append((road, float(width_m), coords))
                for pt in coords:
                    vertex_uses[_coord_key(pt)] += 1

        # 2. Split polylines at shared vertices so every junction gets a single continuous elevation.
        segments: list[tuple[dict, float, list[tuple[float, float]]]] = []
        node_sample_pool: dict[tuple[float, float], list[float]] = defaultdict(list)
        half_win = 0.5 * self.smoothing_window_m

        for road, width_m, coords in raw_parts:
            split_idx = [0]
            for i in range(1, len(coords) - 1):
                if vertex_uses[_coord_key(coords[i])] > 1:
                    split_idx.append(i)
            split_idx.append(len(coords) - 1)
            for i0, i1 in zip(split_idx, split_idx[1:]):
                sub = coords[i0 : i1 + 1]
                if len(sub) < 2:
                    continue
                if sum(dist(a, b) for a, b in zip(sub, sub[1:])) < 1e-4:
                    continue
                segments.append((road, width_m, sub))
                pts, cum_s = _densify_polyline(sub, SAMPLE_STEP_M)
                arr = np.asarray(pts, dtype=np.float64)
                zs = elevation.sample_array(arr[:, 0], arr[:, 1])
                s_arr = np.asarray(cum_s, dtype=np.float64)
                k_start = _coord_key(sub[0])
                k_end = _coord_key(sub[-1])
                start_mask = s_arr <= half_win + 1e-9
                end_mask = s_arr >= (s_arr[-1] - half_win - 1e-9)
                node_sample_pool[k_start].extend(zs[start_mask].tolist())
                node_sample_pool[k_end].extend(zs[end_mask].tolist())

        # Shared junction elevation = mean of all road samples within +-window/2 around each node.
        node_z: dict[tuple[float, float], float] = {
            key: float(np.mean(vals)) for key, vals in node_sample_pool.items()
        }

        # 3. Compute smoothed longitudinal profile for each segment, pinned smoothly to shared node_z.
        max_slope_by_road: dict[str, float] = {}
        road_meta: dict[str, tuple[str, str, float]] = {}

        for road, width_m, sub in segments:
            pts, cum_s = _densify_polyline(sub, SAMPLE_STEP_M)
            arr = np.asarray(pts, dtype=np.float64)
            s_arr = np.asarray(cum_s, dtype=np.float64)
            raw_z = elevation.sample_array(arr[:, 0], arr[:, 1])
            smooth_z = _moving_average_1d(s_arr, raw_z, self.smoothing_window_m)

            # Smoothly blend endpoints to exact shared node_z so junctions have zero step.
            z0_target = node_z[_coord_key(sub[0])]
            z1_target = node_z[_coord_key(sub[-1])]
            dz0 = z0_target - smooth_z[0]
            dz1 = z1_target - smooth_z[-1]
            total_len = float(s_arr[-1])
            if total_len > 1e-6:
                blend_len = min(self.smoothing_window_m, 0.5 * total_len)
                if blend_len > 1e-6:
                    w0 = np.clip(1.0 - s_arr / blend_len, 0.0, 1.0)
                    w0 = w0 * w0 * (3.0 - 2.0 * w0)
                    w1 = np.clip(1.0 - (total_len - s_arr) / blend_len, 0.0, 1.0)
                    w1 = w1 * w1 * (3.0 - 2.0 * w1)
                    smooth_z = smooth_z + dz0 * w0 + dz1 * w1
                else:
                    t = s_arr / total_len
                    smooth_z = (1.0 - t) * z0_target + t * z1_target
            smooth_z[0] = z0_target
            smooth_z[-1] = z1_target

            # Compute maximum longitudinal gradient (%) on this segment
            max_slope_pct = 0.0
            if len(s_arr) >= 2:
                ds = np.diff(s_arr)
                dz = np.abs(np.diff(smooth_z))
                valid = ds > 1e-4
                if np.any(valid):
                    max_slope_pct = float(np.max(dz[valid] / ds[valid]) * 100.0)

            rid = road["id"]
            tags = road["properties"]
            part = _RoadProfilePart(
                road_id=rid,
                name=tags.get("name", ""),
                highway=tags["highway"],
                width_m=width_m,
                line=LineString(sub),
                s_vals=s_arr,
                z_vals=smooth_z,
                max_slope_percent=max_slope_pct,
            )
            self.parts.append(part)
            self.parts_by_road_id[rid].append(part)
            prev_max = max_slope_by_road.get(rid, 0.0)
            if max_slope_pct > prev_max:
                max_slope_by_road[rid] = max_slope_pct
            if rid not in road_meta:
                road_meta[rid] = (tags.get("name", ""), tags["highway"], total_len)
            else:
                n_str, hw_str, l_sum = road_meta[rid]
                road_meta[rid] = (n_str, hw_str, l_sum + total_len)

        self._geoms = [p.line for p in self.parts]
        self._tree = STRtree(self._geoms) if self._geoms else None

        for rid in sorted(road_meta):
            rname, hw, length_sum = road_meta[rid]
            self.road_reports.append(
                {
                    "id": rid,
                    "name": rname,
                    "highway": hw,
                    "length_m": round(length_sum, 2),
                    "max_slope_percent": round(max_slope_by_road.get(rid, 0.0), 2),
                }
            )

    def ground_elevation_at(self, east_m: float, north_m: float, road_id: str | None = None) -> float:
        """
        Return smoothed longitudinal road ground elevation (before ROAD_ELEVATION_M)
        by perpendicular projection onto the owning or nearest road axis.
        """
        if self.elevation.is_flat:
            return self.elevation.flat_elevation_m
        pt = Point(float(east_m), float(north_m))

        if road_id and road_id in self.parts_by_road_id:
            candidates = self.parts_by_road_id[road_id]
            best = min(candidates, key=lambda p: p.line.distance(pt))
            return best.elevation_at_xy(east_m, north_m)

        if self._tree is None:
            return self.elevation.sample(east_m, north_m)

        # Query nearby road parts within 12 m; pick closest axis (flat cross-section!)
        idx = self._tree.nearest(pt)
        nearest_part = self.parts[int(idx)]
        d_min = nearest_part.line.distance(pt)
        if d_min > 18.0:
            return self.elevation.sample(east_m, north_m)

        # If near an intersection (multiple segments within d_min + 0.5 m), take deterministic minimum-distance part
        nearby_idxs = self._tree.query(pt.buffer(d_min + 0.25))
        if len(nearby_idxs) <= 1:
            return nearest_part.elevation_at_xy(east_m, north_m)

        best_part = nearest_part
        best_dist = d_min
        for i in nearby_idxs:
            cand = self.parts[int(i)]
            d = cand.line.distance(pt)
            if d < best_dist - 1e-6 or (abs(d - best_dist) <= 1e-6 and cand.road_id < best_part.road_id):
                best_dist = d
                best_part = cand
        return best_part.elevation_at_xy(east_m, north_m)

    def road_surface_z(self, east_m: float, north_m: float, road_id: str | None = None) -> float:
        return self.ground_elevation_at(east_m, north_m, road_id=road_id) + self.road_offset_m

    def sidewalk_surface_z(self, east_m: float, north_m: float, road_id: str | None = None) -> float:
        return self.ground_elevation_at(east_m, north_m, road_id=road_id) + self.road_offset_m + self.curb_height_m

    def max_slope_overall(self) -> float:
        if not self.road_reports:
            return 0.0
        return max(r["max_slope_percent"] for r in self.road_reports)


def densify_polygon(polygon: Polygon, max_segment_m: float = 3.0) -> Polygon:
    """Densify exterior and interior rings so draped surfaces follow terrain smoothly."""
    def densify_ring(ring):
        coords = list(ring.coords)
        if len(coords) < 4:
            return coords
        out = [coords[0]]
        for a, b in zip(coords, coords[1:]):
            seg = hypot(b[0] - a[0], b[1] - a[1])
            if seg > max_segment_m:
                n = int(ceil(seg / max_segment_m))
                for i in range(1, n):
                    t = i / n
                    out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            out.append(b)
        return out

    ext = densify_ring(polygon.exterior)
    ints = [densify_ring(hole) for hole in polygon.interiors]
    return Polygon(ext, ints)
