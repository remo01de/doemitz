"""Smoothed longitudinal road elevation profiles, linear bridge decks, and flat cross-section projection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import ceil, dist, hypot

import numpy as np
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.strtree import STRtree

from tools.geo_transform.terrain import ElevationModel


DEFAULT_SMOOTHING_WINDOW_M = 12.0
SAMPLE_STEP_M = 1.0
ABUTMENT_FALLBACK_RADIUS_M = 3.0


def _coord_key(xy) -> tuple[float, float]:
    return (round(float(xy[0]), 4), round(float(xy[1]), 4))


def is_bridge_road(tags: dict) -> bool:
    raw = str(tags.get("bridge", "no")).strip().lower()
    return raw not in ("", "no", "false", "0")


def _way_sort_key(way_id: str) -> tuple[int, str]:
    tail = way_id.rsplit(":", 1)[-1]
    return (int(tail), way_id) if tail.isdigit() else (10**12, way_id)


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


def _max_dgm_in_radius(elevation: ElevationModel, east_m: float, north_m: float, radius_m: float = ABUTMENT_FALLBACK_RADIUS_M) -> float:
    """Sample DGM1 on a deterministic 0.5 m disk of radius_m around (east_m, north_m) and return max."""
    if elevation.is_flat:
        return elevation.flat_elevation_m
    offsets = np.arange(-radius_m, radius_m + 1e-6, 0.5, dtype=np.float64)
    ox, oy = np.meshgrid(offsets, offsets)
    mask = (ox * ox + oy * oy) <= (radius_m * radius_m + 1e-6)
    zs = elevation.sample_array(east_m + ox[mask], north_m + oy[mask])
    return float(np.max(zs))


@dataclass
class BridgeAbutment:
    key: tuple[float, float]
    position_xy: tuple[float, float]
    ground_z_m: float
    source: str
    connected_road_ids: list[str] = field(default_factory=list)


@dataclass
class BridgeChain:
    id: str
    way_ids: list[str]
    name: str
    highway: str
    surface: str
    material_tag: str
    bridge_structure: str
    width_m: float
    coords: list[tuple[float, float]]
    s_vals: np.ndarray
    z_vals: np.ndarray
    length_m: float
    abutments: tuple[BridgeAbutment, BridgeAbutment]
    max_slope_percent: float
    incline: str = ""
    warnings: list[str] = field(default_factory=list)

    def ground_elevation_at_s(self, s_m: float) -> float:
        return float(np.interp(s_m, self.s_vals, self.z_vals))


@dataclass
class TunnelWayInfo:
    road_id: str
    name: str
    highway: str
    width_m: float
    coords: list[tuple[float, float]]
    portal_z_m: tuple[float, float]


class _RoadProfilePart:
    __slots__ = (
        "road_id", "name", "highway", "width_m", "line", "s_vals", "z_vals",
        "length_m", "max_slope_percent", "is_bridge", "bridge_id",
    )

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
        is_bridge: bool = False,
        bridge_id: str = "",
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
        self.is_bridge = is_bridge
        self.bridge_id = bridge_id

    def elevation_at_s(self, s_m: float) -> float:
        return float(np.interp(s_m, self.s_vals, self.z_vals))

    def elevation_at_xy(self, x: float, y: float) -> float:
        s = self.line.project(Point(x, y))
        return self.elevation_at_s(s)


def _group_bridge_chains(
    bridge_raw: list[tuple[dict, float, list[tuple[float, float]]]],
) -> list[list[tuple[dict, float, list[tuple[float, float]]]]]:
    """Group connected bridge ways sharing endpoints into ordered continuous chains."""
    if not bridge_raw:
        return []

    n = len(bridge_raw)
    adj: dict[int, list[int]] = defaultdict(list)
    endpoint_map: dict[tuple[float, float], list[int]] = defaultdict(list)
    for idx, (_, _, coords) in enumerate(bridge_raw):
        endpoint_map[_coord_key(coords[0])].append(idx)
        endpoint_map[_coord_key(coords[-1])].append(idx)

    for indices in endpoint_map.values():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                adj[indices[i]].append(indices[j])
                adj[indices[j]].append(indices[i])

    visited = [False] * n
    components: list[list[int]] = []
    for i in range(n):
        if visited[i]:
            continue
        comp = []
        stack = [i]
        visited[i] = True
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in sorted(adj[cur]):
                if not visited[nb]:
                    visited[nb] = True
                    stack.append(nb)
        components.append(sorted(comp, key=lambda idx: _way_sort_key(bridge_raw[idx][0]["id"])))

    ordered_chains: list[list[tuple[dict, float, list[tuple[float, float]]]]] = []
    for comp in components:
        if len(comp) == 1:
            ordered_chains.append([bridge_raw[comp[0]]])
            continue

        # Order ways into a continuous chain starting from a degree-1 endpoint way
        comp_set = set(comp)
        start_idx = next(
            (idx for idx in comp if sum(1 for nb in adj[idx] if nb in comp_set) <= 1),
            comp[0],
        )
        chain_indices = [start_idx]
        used = {start_idx}
        while len(chain_indices) < len(comp):
            cur = chain_indices[-1]
            nxt = next((nb for nb in sorted(adj[cur]) if nb in comp_set and nb not in used), None)
            if nxt is None:
                break
            chain_indices.append(nxt)
            used.add(nxt)

        # Orient consecutive ways so each way's end matches the next way's start
        oriented: list[tuple[dict, float, list[tuple[float, float]]]] = []
        for pos, idx in enumerate(chain_indices):
            road, w, coords = bridge_raw[idx]
            if pos == 0 and len(chain_indices) > 1:
                next_coords = bridge_raw[chain_indices[1]][2]
                next_keys = {_coord_key(next_coords[0]), _coord_key(next_coords[-1])}
                if _coord_key(coords[0]) in next_keys and _coord_key(coords[-1]) not in next_keys:
                    coords = list(reversed(coords))
            elif pos > 0:
                prev_end = _coord_key(oriented[-1][2][-1])
                if _coord_key(coords[-1]) == prev_end and _coord_key(coords[0]) != prev_end:
                    coords = list(reversed(coords))
            oriented.append((road, w, coords))
        ordered_chains.append(oriented)

    ordered_chains.sort(key=lambda ch: _way_sort_key(min((r["id"] for r, _, _ in ch), key=_way_sort_key)))
    return ordered_chains


class RoadElevationNetwork:
    """
    Smoothed longitudinal road elevation network with linear bridge spans and flat cross-sections.
    - Bridge chains are detected first; abutment heights come from connecting non-bridge road profiles
      (or max DGM within 3 m if disconnected) and stay fixed before non-bridge smoothing.
    - Bridge decks run strictly linear between abutments without sampling DGM under the bridge.
    - Every point on a road or adjacent sidewalk projects perpendicularly onto its road axis,
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
        self.bridges: list[BridgeChain] = []
        self.bridge_way_ids: set[str] = set()
        self.bridge_by_way_id: dict[str, BridgeChain] = {}
        self.tunnels: list[TunnelWayInfo] = []
        self._tree = None
        self._geoms: list[LineString] = []

        # 1. Partition roads into non-bridge, bridge, and tunnel ways.
        # Tunnel ways stay excluded from draped surface roads, but their portal nodes count as valid bridge connections.
        non_bridge_raw: list[tuple[dict, float, list[tuple[float, float]]]] = []
        bridge_raw: list[tuple[dict, float, list[tuple[float, float]]]] = []
        non_bridge_vertex_uses: dict[tuple[float, float], int] = defaultdict(int)
        non_bridge_roads_at_key: dict[tuple[float, float], set[str]] = defaultdict(set)
        tunnel_roads_at_key: dict[tuple[float, float], set[str]] = defaultdict(set)

        for road in roads:
            tags = road["properties"]
            width_m, _ = road_width_fn(tags)
            geom = shape(road["geometry"])
            lines = (
                [geom]
                if geom.geom_type == "LineString"
                else list(geom.geoms)
                if geom.geom_type == "MultiLineString"
                else []
            )
            if tags.get("tunnel", "no") != "no":
                for line in lines:
                    coords = [(float(p[0]), float(p[1])) for p in line.coords]
                    if len(coords) < 2:
                        continue
                    for pt in (coords[0], coords[-1]):
                        tunnel_roads_at_key[_coord_key(pt)].add(road["id"])
                    z0 = elevation.flat_elevation_m if elevation.is_flat else float(elevation.sample(coords[0][0], coords[0][1]))
                    z1 = elevation.flat_elevation_m if elevation.is_flat else float(elevation.sample(coords[-1][0], coords[-1][1]))
                    self.tunnels.append(
                        TunnelWayInfo(
                            road_id=road["id"],
                            name=tags.get("name", ""),
                            highway=tags["highway"],
                            width_m=float(width_m),
                            coords=coords,
                            portal_z_m=(round(z0, 4), round(z1, 4)),
                        )
                    )
                continue
            bridge_flag = is_bridge_road(tags)
            for line in lines:
                coords = [(float(p[0]), float(p[1])) for p in line.coords]
                if len(coords) < 2:
                    continue
                if bridge_flag:
                    bridge_raw.append((road, float(width_m), coords))
                    self.bridge_way_ids.add(road["id"])
                else:
                    non_bridge_raw.append((road, float(width_m), coords))
                    for pt in coords:
                        k = _coord_key(pt)
                        non_bridge_vertex_uses[k] += 1
                        non_bridge_roads_at_key[k].add(road["id"])

        # 2. Group connected bridge ways into continuous chains & locate their abutment keys.
        grouped_chains = _group_bridge_chains(bridge_raw)
        abutment_keys: set[tuple[float, float]] = set()
        for chain_entries in grouped_chains:
            abutment_keys.add(_coord_key(chain_entries[0][2][0]))
            abutment_keys.add(_coord_key(chain_entries[-1][2][-1]))

        # 3. Split non-bridge polylines at shared non-bridge junctions AND at bridge abutments.
        non_bridge_segments: list[tuple[dict, float, list[tuple[float, float]]]] = []
        node_sample_pool: dict[tuple[float, float], list[float]] = defaultdict(list)
        abutment_sample_pool: dict[tuple[float, float], list[float]] = defaultdict(list)
        half_win = 0.5 * self.smoothing_window_m

        for road, width_m, coords in non_bridge_raw:
            split_idx = [0]
            for i in range(1, len(coords) - 1):
                k = _coord_key(coords[i])
                if non_bridge_vertex_uses[k] > 1 or k in abutment_keys:
                    split_idx.append(i)
            split_idx.append(len(coords) - 1)
            for i0, i1 in zip(split_idx, split_idx[1:]):
                sub = coords[i0 : i1 + 1]
                if len(sub) < 2:
                    continue
                if sum(dist(a, b) for a, b in zip(sub, sub[1:])) < 1e-4:
                    continue
                non_bridge_segments.append((road, width_m, sub))
                if elevation.is_flat:
                    continue
                pts, cum_s = _densify_polyline(sub, SAMPLE_STEP_M)
                arr = np.asarray(pts, dtype=np.float64)
                zs = elevation.sample_array(arr[:, 0], arr[:, 1])
                s_arr = np.asarray(cum_s, dtype=np.float64)
                total_len = float(s_arr[-1])
                k_start = _coord_key(sub[0])
                k_end = _coord_key(sub[-1])

                # Guard against bare-earth canal/moat lip drop right at a bridge abutment:
                # if DGM drops > 0.35 m within 1.5 m of an abutment compared to 1.5..6.0 m inland,
                # use the inland connecting road profile samples for the abutment height.
                if k_start in abutment_keys:
                    inland = (s_arr >= 1.5) & (s_arr <= min(total_len, half_win + 1.5))
                    if np.any(inland) and zs[0] < float(np.median(zs[inland])) - 0.35:
                        abutment_sample_pool[k_start].extend(zs[inland].tolist())
                    else:
                        abutment_sample_pool[k_start].extend(zs[s_arr <= half_win + 1e-9].tolist())
                else:
                    node_sample_pool[k_start].extend(zs[s_arr <= half_win + 1e-9].tolist())

                if k_end in abutment_keys:
                    inland = (s_arr <= total_len - 1.5) & (s_arr >= max(0.0, total_len - half_win - 1.5))
                    if np.any(inland) and zs[-1] < float(np.median(zs[inland])) - 0.35:
                        abutment_sample_pool[k_end].extend(zs[inland].tolist())
                    else:
                        abutment_sample_pool[k_end].extend(zs[s_arr >= total_len - half_win - 1e-9].tolist())
                else:
                    node_sample_pool[k_end].extend(zs[s_arr >= total_len - half_win - 1e-9].tolist())

        # Compute non-bridge node heights first (never polluted by DGM under bridges).
        node_z: dict[tuple[float, float], float] = {
            key: float(np.mean(vals)) for key, vals in node_sample_pool.items()
        }

        # 4. Determine fixed abutment heights & strictly linear bridge profiles BEFORE non-bridge smoothing.
        max_slope_by_road: dict[str, float] = {}
        road_meta: dict[str, tuple[str, str, float]] = {}

        for chain_entries in grouped_chains:
            way_ids = [r["id"] for r, _, _ in chain_entries]
            first_way_id = min(way_ids, key=_way_sort_key)
            bridge_id = f"bridge:{first_way_id}"

            # Combine ordered coords without duplicating shared interior vertices
            chain_coords: list[tuple[float, float]] = []
            way_ranges: list[tuple[dict, float, list[tuple[float, float]], float, float]] = []
            cursor_s = 0.0
            for road, w_m, sub in chain_entries:
                seg_len = sum(dist(a, b) for a, b in zip(sub, sub[1:]))
                way_ranges.append((road, w_m, sub, cursor_s, cursor_s + seg_len))
                cursor_s += seg_len
                if not chain_coords:
                    chain_coords.extend(sub)
                else:
                    chain_coords.extend(sub[1:])

            start_xy = chain_coords[0]
            end_xy = chain_coords[-1]
            k_a = _coord_key(start_xy)
            k_b = _coord_key(end_xy)

            def resolve_abutment(key: tuple[float, float], xy: tuple[float, float]) -> BridgeAbutment:
                conn_roads = sorted(non_bridge_roads_at_key.get(key, set()))
                conn_tunnels = sorted(tunnel_roads_at_key.get(key, set()))
                conn = sorted(set(conn_roads) | set(conn_tunnels))
                if elevation.is_flat:
                    z_val = elevation.flat_elevation_m
                    src = "flat_placeholder"
                elif key in abutment_sample_pool and abutment_sample_pool[key]:
                    z_val = float(np.mean(abutment_sample_pool[key]))
                    src = "connecting_road_profile"
                elif key in node_z:
                    z_val = node_z[key]
                    src = "connecting_road_profile"
                elif conn_tunnels:
                    # A tunnel way counts as an abutment connection; use DGM elevation directly at the portal node.
                    z_val = float(elevation.sample(xy[0], xy[1]))
                    src = "tunnel_portal_dgm"
                else:
                    z_val = _max_dgm_in_radius(elevation, xy[0], xy[1], ABUTMENT_FALLBACK_RADIUS_M)
                    src = "assumed_max_dgm_3m_radius"
                return BridgeAbutment(
                    key=key,
                    position_xy=(round(xy[0], 4), round(xy[1], 4)),
                    ground_z_m=round(z_val, 4),
                    source=src,
                    connected_road_ids=conn,
                )

            ab_a = resolve_abutment(k_a, start_xy)
            ab_b = resolve_abutment(k_b, end_xy)
            # Pin abutment heights in node_z so connecting non-bridge roads match with 0.0 cm step.
            node_z[k_a] = ab_a.ground_z_m
            node_z[k_b] = ab_b.ground_z_m

            chain_warnings: list[str] = []
            for idx_ab, (ab_cur, ab_other) in enumerate(((ab_a, ab_b), (ab_b, ab_a))):
                if ab_cur.source == "assumed_max_dgm_3m_radius" and (ab_cur.ground_z_m - ab_other.ground_z_m) > 1.0:
                    chain_warnings.append(
                        f"abutment_{idx_ab} used 3m DGM fallback and sits "
                        f"{ab_cur.ground_z_m - ab_other.ground_z_m:.2f} m above the opposite abutment"
                    )

            total_chain_len = max(cursor_s, 1e-4)
            chain_pts, chain_cum_s = _densify_polyline(chain_coords, SAMPLE_STEP_M)
            chain_s_arr = np.asarray(chain_cum_s, dtype=np.float64)
            # Strictly linear deck elevation between abutment A and abutment B (never reads DGM underneath!)
            chain_z_arr = ab_a.ground_z_m + (chain_s_arr / total_chain_len) * (ab_b.ground_z_m - ab_a.ground_z_m)
            chain_slope_pct = abs(ab_b.ground_z_m - ab_a.ground_z_m) / total_chain_len * 100.0

            # Pick primary metadata from chain ways (prefer bridge:name > name, material > surface)
            b_name = ""
            b_struct = ""
            b_mat = ""
            b_surface = ""
            b_incline = ""
            b_highway = chain_entries[0][0]["properties"]["highway"]
            b_width = max(w for _, w, _ in chain_entries)
            for road, _, _ in chain_entries:
                props = road["properties"]
                if not b_name:
                    b_name = props.get("bridge:name") or props.get("name", "")
                if not b_struct and props.get("bridge:structure"):
                    b_struct = props["bridge:structure"]
                if not b_mat and props.get("material"):
                    b_mat = props["material"]
                if not b_surface and props.get("surface"):
                    b_surface = props["surface"]
                if not b_incline and props.get("incline"):
                    b_incline = props["incline"]

            chain_obj = BridgeChain(
                id=bridge_id,
                way_ids=way_ids,
                name=b_name,
                highway=b_highway,
                surface=b_surface,
                material_tag=b_mat,
                bridge_structure=b_struct,
                width_m=float(b_width),
                coords=chain_coords,
                s_vals=chain_s_arr,
                z_vals=chain_z_arr,
                length_m=round(total_chain_len, 4),
                abutments=(ab_a, ab_b),
                max_slope_percent=round(chain_slope_pct, 2),
                incline=b_incline,
                warnings=chain_warnings,
            )
            self.bridges.append(chain_obj)
            for wid in way_ids:
                self.bridge_by_way_id[wid] = chain_obj

            # Register each constituent bridge way as a strictly linear _RoadProfilePart
            for road, w_m, sub, s0, s1 in way_ranges:
                pts, cum_s = _densify_polyline(sub, SAMPLE_STEP_M)
                s_arr = np.asarray(cum_s, dtype=np.float64)
                z_arr = ab_a.ground_z_m + ((s0 + s_arr) / total_chain_len) * (ab_b.ground_z_m - ab_a.ground_z_m)
                rid = road["id"]
                tags = road["properties"]
                part = _RoadProfilePart(
                    road_id=rid,
                    name=tags.get("name", ""),
                    highway=tags["highway"],
                    width_m=w_m,
                    line=LineString(sub),
                    s_vals=s_arr,
                    z_vals=z_arr,
                    max_slope_percent=chain_slope_pct,
                    is_bridge=True,
                    bridge_id=bridge_id,
                )
                self.parts.append(part)
                self.parts_by_road_id[rid].append(part)
                max_slope_by_road[rid] = max(max_slope_by_road.get(rid, 0.0), chain_slope_pct)
                seg_len = float(s_arr[-1])
                if rid not in road_meta:
                    road_meta[rid] = (tags.get("name", ""), tags["highway"], seg_len)
                else:
                    n_str, hw_str, l_sum = road_meta[rid]
                    road_meta[rid] = (n_str, hw_str, l_sum + seg_len)

        if elevation.is_flat:
            for rid in sorted(road_meta):
                rname, hw, length_sum = road_meta[rid]
                self.road_reports.append({
                    "id": rid,
                    "name": rname,
                    "highway": hw,
                    "length_m": round(length_sum, 2),
                    "max_slope_percent": 0.0,
                    "is_bridge": rid in self.bridge_way_ids,
                })
            return

        # 5. Smooth all non-bridge road segments, pinned strictly to shared junctions & fixed bridge abutments.
        for road, width_m, sub in non_bridge_segments:
            pts, cum_s = _densify_polyline(sub, SAMPLE_STEP_M)
            arr = np.asarray(pts, dtype=np.float64)
            s_arr = np.asarray(cum_s, dtype=np.float64)
            total_len = float(s_arr[-1])
            raw_z = elevation.sample_array(arr[:, 0], arr[:, 1])

            k_start = _coord_key(sub[0])
            k_end = _coord_key(sub[-1])
            z0_target = node_z[k_start]
            z1_target = node_z[k_end]

            # Replace any bare-earth cliff drop right at a bridge abutment lip before 12 m smoothing
            clean_z = raw_z.copy()
            if k_start in abutment_keys:
                lip = s_arr <= min(2.0, total_len * 0.5)
                clean_z[lip] = np.maximum(clean_z[lip], z0_target - 0.15)
            if k_end in abutment_keys:
                lip = s_arr >= max(0.0, total_len - min(2.0, total_len * 0.5))
                clean_z[lip] = np.maximum(clean_z[lip], z1_target - 0.15)

            smooth_z = _moving_average_1d(s_arr, clean_z, self.smoothing_window_m)

            dz0 = z0_target - smooth_z[0]
            dz1 = z1_target - smooth_z[-1]
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
                is_bridge=False,
                bridge_id="",
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
                    "is_bridge": rid in self.bridge_way_ids,
                }
            )

    def ground_elevation_at(self, east_m: float, north_m: float, road_id: str | None = None) -> float:
        """
        Return smoothed longitudinal road (or linear bridge) ground elevation (before ROAD_ELEVATION_M)
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

        idx = self._tree.nearest(pt)
        nearest_part = self.parts[int(idx)]
        d_min = nearest_part.line.distance(pt)
        if d_min > 18.0:
            return self.elevation.sample(east_m, north_m)

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
