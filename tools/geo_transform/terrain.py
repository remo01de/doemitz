"""Central elevation model and terrain sampler for local metric coordinates."""

from __future__ import annotations

from hashlib import sha256
from math import ceil, floor, hypot
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon


class ElevationModel:
    """Single source of truth for local elevation Z (meters) from DGM1 or flat placeholder."""

    def __init__(
        self,
        kind: str,
        reference_elevation_m: float = 0.0,
        flat_elevation_m: float = 0.0,
        grid: np.ndarray | None = None,
        origin_east_m: float = 0.0,
        origin_north_m: float = 0.0,
        spacing_m: float = 1.0,
    ):
        self.kind = kind
        self.reference_elevation_m = float(reference_elevation_m)
        self.flat_elevation_m = float(flat_elevation_m)
        self.grid = np.asarray(grid, dtype=np.float64) if grid is not None else None
        self.origin_east_m = float(origin_east_m)
        self.origin_north_m = float(origin_north_m)
        self.spacing_m = float(spacing_m)
        if self.kind == "dgm1":
            if self.grid is None or self.grid.ndim != 2:
                raise ValueError("dgm1 elevation model requires a 2D height grid")
            self.rows, self.cols = self.grid.shape
        else:
            self.rows, self.cols = 0, 0

    @classmethod
    def flat(cls, elevation_m: float = 0.0) -> "ElevationModel":
        return cls(kind="flat_placeholder", reference_elevation_m=0.0, flat_elevation_m=elevation_m)

    @classmethod
    def from_scene(cls, scene: dict, scene_dir: Path | None = None) -> "ElevationModel":
        terrain = scene["terrain"]
        kind = terrain["kind"]
        if kind == "flat_placeholder":
            return cls.flat(float(terrain.get("elevation_m", 0.0)))
        if kind != "dgm1":
            raise ValueError(f"unsupported terrain kind: {kind!r}")
        if scene_dir is None:
            raise ValueError("scene_dir is required to load dgm1 terrain grid")
        gmeta = terrain["grid"]
        grid_path = scene_dir / gmeta["file"]
        raw = grid_path.read_bytes()
        expected_sha = gmeta.get("sha256")
        if expected_sha and sha256(raw).hexdigest() != expected_sha:
            raise ValueError(f"terrain grid SHA-256 mismatch for {grid_path}")
        arr = np.frombuffer(raw, dtype=np.dtype(gmeta["dtype"])).reshape(
            int(gmeta["rows"]), int(gmeta["cols"])
        )
        return cls(
            kind="dgm1",
            reference_elevation_m=float(terrain["reference_elevation_m"]),
            grid=arr.astype(np.float64),
            origin_east_m=float(gmeta["origin_local_east_m"]),
            origin_north_m=float(gmeta["origin_local_north_m"]),
            spacing_m=float(gmeta["spacing_m"]),
        )

    @property
    def is_flat(self) -> bool:
        return self.kind != "dgm1"

    def nhn_to_local(self, nhn_m: float) -> float:
        return float(nhn_m) - self.reference_elevation_m

    def local_to_nhn(self, local_m: float) -> float:
        return float(local_m) + self.reference_elevation_m

    def sample(self, east_m: float, north_m: float) -> float:
        """Bilinear elevation sample in local meters."""
        if self.is_flat or self.grid is None:
            return self.flat_elevation_m
        fx = (float(east_m) - self.origin_east_m) / self.spacing_m
        fy = (float(north_m) - self.origin_north_m) / self.spacing_m
        fx = max(0.0, min(float(self.cols - 1), fx))
        fy = max(0.0, min(float(self.rows - 1), fy))
        c0 = int(floor(fx))
        r0 = int(floor(fy))
        c1 = min(self.cols - 1, c0 + 1)
        r1 = min(self.rows - 1, r0 + 1)
        tx = fx - c0
        ty = fy - r0
        z00 = self.grid[r0, c0]
        z10 = self.grid[r0, c1]
        z01 = self.grid[r1, c0]
        z11 = self.grid[r1, c1]
        return float((1.0 - ty) * ((1.0 - tx) * z00 + tx * z10) + ty * ((1.0 - tx) * z01 + tx * z11))

    def sample_array(self, east_m: np.ndarray, north_m: np.ndarray) -> np.ndarray:
        """Vectorized bilinear elevation sample in local meters."""
        east_arr = np.asarray(east_m, dtype=np.float64)
        north_arr = np.asarray(north_m, dtype=np.float64)
        if self.is_flat or self.grid is None:
            return np.full(np.broadcast_shapes(east_arr.shape, north_arr.shape), self.flat_elevation_m, dtype=np.float64)
        fx = np.clip((east_arr - self.origin_east_m) / self.spacing_m, 0.0, float(self.cols - 1))
        fy = np.clip((north_arr - self.origin_north_m) / self.spacing_m, 0.0, float(self.rows - 1))
        c0 = np.floor(fx).astype(np.int64)
        r0 = np.floor(fy).astype(np.int64)
        c1 = np.minimum(self.cols - 1, c0 + 1)
        r1 = np.minimum(self.rows - 1, r0 + 1)
        tx = fx - c0
        ty = fy - r0
        z00 = self.grid[r0, c0]
        z10 = self.grid[r0, c1]
        z01 = self.grid[r1, c0]
        z11 = self.grid[r1, c1]
        return (1.0 - ty) * ((1.0 - tx) * z00 + tx * z10) + ty * ((1.0 - tx) * z01 + tx * z11)

    def _ring_sample_points(self, ring, step_m: float = 1.0) -> list[tuple[float, float]]:
        pts = []
        coords = list(ring.coords)
        for a, b in zip(coords, coords[1:]):
            pts.append((float(a[0]), float(a[1])))
            seg = hypot(b[0] - a[0], b[1] - a[1])
            if seg > step_m:
                n = int(ceil(seg / step_m))
                for i in range(1, n):
                    t = i / n
                    pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if coords:
            pts.append((float(coords[-1][0]), float(coords[-1][1])))
        return pts

    def boundary_min_max(self, polygon: Polygon, step_m: float = 1.0) -> tuple[float, float]:
        """Min and max terrain elevation along all exterior and interior boundary rings."""
        if self.is_flat:
            return self.flat_elevation_m, self.flat_elevation_m
        pts = self._ring_sample_points(polygon.exterior, step_m=step_m)
        for interior in polygon.interiors:
            pts.extend(self._ring_sample_points(interior, step_m=step_m))
        arr = np.asarray(pts, dtype=np.float64)
        zs = self.sample_array(arr[:, 0], arr[:, 1])
        return float(zs.min()), float(zs.max())

    def polygon_min_max(self, polygon: Polygon, step_m: float = 1.0) -> tuple[float, float]:
        """Min and max terrain elevation across a polygon's boundary and interior grid points."""
        if self.is_flat:
            return self.flat_elevation_m, self.flat_elevation_m
        pts = self._ring_sample_points(polygon.exterior, step_m=step_m)
        for interior in polygon.interiors:
            pts.extend(self._ring_sample_points(interior, step_m=step_m))
        rp = polygon.representative_point()
        pts.append((float(rp.x), float(rp.y)))

        # Also include all 1 m grid nodes falling inside the polygon bounding box and covered by it
        min_e, min_n, max_e, max_n = polygon.bounds
        c_start = max(0, int(ceil((min_e - self.origin_east_m) / self.spacing_m)))
        c_end = min(self.cols - 1, int(floor((max_e - self.origin_east_m) / self.spacing_m)))
        r_start = max(0, int(ceil((min_n - self.origin_north_m) / self.spacing_m)))
        r_end = min(self.rows - 1, int(floor((max_n - self.origin_north_m) / self.spacing_m)))

        zs_list = []
        if pts:
            arr = np.asarray(pts, dtype=np.float64)
            zs_list.append(self.sample_array(arr[:, 0], arr[:, 1]))

        if c_start <= c_end and r_start <= r_end and self.grid is not None:
            from shapely import contains_xy

            cs = np.arange(c_start, c_end + 1, dtype=np.float64)
            rs = np.arange(r_start, r_end + 1, dtype=np.float64)
            ee, nn = np.meshgrid(self.origin_east_m + cs * self.spacing_m, self.origin_north_m + rs * self.spacing_m)
            inside = contains_xy(polygon, ee, nn)
            if np.any(inside):
                sub = self.grid[r_start : r_end + 1, c_start : c_end + 1]
                zs_list.append(sub[inside])

        all_z = np.concatenate(zs_list)
        return float(all_z.min()), float(all_z.max())
