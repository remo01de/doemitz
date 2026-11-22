"""Sprint 13: walk-in ground-floor interiors, selected by OSM building ID in doemitz-altstadt-interiors.json.

The building generators (architecture.add_stylized_building, landmarks._build_rathaus) receive an
InteriorShell. They cut the door and the ground-floor windows out of the exterior wall and set the ceiling
height. build_interior() then adds the inner wall face with the same openings, reveals, floor, ceiling,
furniture from the configured template, citizen stand spots, lights and the door leaf for Unreal.

All room layouts are assumptions (there are no public floor plans); the footprint is the OSM geometry.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import atan2, ceil, degrees, hypot

import numpy as np
import shapely
from shapely import constrained_delaunay_triangles, orient_polygons
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

from tools.mesh_generator.architecture import _add_box_on_wall, _add_quad

INTERIOR_PALETTE = {
    "InteriorFloor": (0.42, 0.30, 0.19),
    "InteriorWalls": (0.88, 0.85, 0.78),
    "InteriorCeiling": (0.93, 0.92, 0.89),
    "InteriorFurniture": (0.46, 0.31, 0.18),
    "InteriorGoods": (0.70, 0.52, 0.32),
    "NoticeBoard": (0.60, 0.44, 0.27),
    "NoticePaper": (0.95, 0.95, 0.91),
    "WindowGlassClear": (0.62, 0.76, 0.84),
    "InteriorLamp": (1.00, 0.93, 0.78),
}
INTERIOR_COLLISION_MESHES = {"InteriorFloor", "InteriorWalls", "InteriorCeiling", "InteriorFurniture", "WindowGlassClear"}

CAPSULE_RADIUS_M = 0.36
GRID_STEP_M = 0.2


@dataclass
class Opening:
    edge_idx: int
    u0: float
    u1: float
    z0: float
    z1: float
    kind: str  # "door" | "window"


def _edge_frame(ring, idx):
    a, b = ring[idx], ring[idx + 1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = hypot(dx, dy)
    tx, ty = (dx / length, dy / length) if length > 1e-9 else (1.0, 0.0)
    return a, b, length, (tx, ty), (ty, -tx)  # outward normal of a CCW ring


class InteriorShell:
    """Door, window openings and storey heights shared by the exterior builder and build_interior()."""

    def __init__(self, cfg: dict, polygon: Polygon, base_m: float, ground_z_fn, assumptions: dict):
        self.cfg = cfg
        self.id = cfg["id"]
        self.polygon = orient_polygons(polygon)
        self.ring = list(self.polygon.exterior.coords)
        self.base_m = float(base_m)
        self.wall_thickness_m = float(cfg.get("wall_thickness_m", assumptions.get("wall_thickness_m", 0.4)))
        self.door_width_m = float(cfg.get("door_width_m", assumptions.get("door_width_m", 1.2)))
        self.door_height_m = float(cfg.get("door_height_m", assumptions.get("door_height_m", 2.3)))
        door_xy = cfg["door_local_m"]
        door_pt = Point(float(door_xy[0]), float(door_xy[1]))
        best = None
        for idx in range(len(self.ring) - 1):
            a, b, length, _, _ = _edge_frame(self.ring, idx)
            if length < self.door_width_m + 1.0:
                continue
            d = LineString([a, b]).distance(door_pt)
            if best is None or d < best[0] - 1e-9:
                best = (d, idx)
        if best is None:
            raise ValueError(f"{self.id}: no facade edge long enough for a {self.door_width_m} m door")
        if best[0] > 1.5:
            raise ValueError(f"{self.id}: door_local_m is {best[0]:.2f} m away from the building outline")
        self.door_edge_idx = best[1]
        a, _, length, (tx, ty), (nx, ny) = _edge_frame(self.ring, self.door_edge_idx)
        u = (door_pt.x - a[0]) * tx + (door_pt.y - a[1]) * ty
        margin = self.door_width_m * 0.5 + 0.45
        self.door_u = min(max(u, margin), length - margin)
        self.door_outer_xy = (a[0] + tx * self.door_u, a[1] + ty * self.door_u)
        self.tangent = (tx, ty)
        self.outward = (nx, ny)
        self.inward = (-nx, -ny)
        out_x, out_y = self.door_outer_xy[0] + nx * 0.8, self.door_outer_xy[1] + ny * 0.8
        self.outside_ground_z = float(ground_z_fn(out_x, out_y))
        min_above_base = float(cfg.get("min_floor_above_base_m", 0.10))
        sill_step = float(assumptions.get("door_sill_step_m", 0.15))
        self.floor_z = round(max(self.base_m + min_above_base, self.outside_ground_z + sill_step), 4)
        self.ceiling_z: float | None = None
        half = self.door_width_m * 0.5
        self.openings: list[Opening] = [
            Opening(self.door_edge_idx, self.door_u - half, self.door_u + half,
                    self.floor_z, self.floor_z + self.door_height_m, "door")
        ]

    # --- used by the exterior builders -------------------------------------------------------------
    def door_range(self, edge_idx: int, margin: float = 0.0):
        if edge_idx != self.door_edge_idx:
            return None
        half = self.door_width_m * 0.5 + margin
        return (self.door_u - half, self.door_u + half)

    def overlaps_door(self, edge_idx: int, u0: float, u1: float, margin: float = 0.35) -> bool:
        rng = self.door_range(edge_idx, margin)
        return rng is not None and u1 > rng[0] and u0 < rng[1]

    def add_window(self, edge_idx: int, u0: float, u1: float, z0: float, z1: float) -> bool:
        """Register a ground-floor window opening; returns False if it collides with the door."""
        if self.overlaps_door(edge_idx, u0, u1):
            return False
        top = z1 if self.ceiling_z is None else min(z1, self.ceiling_z - 0.08)
        bottom = max(z0, self.floor_z + 0.35)
        if top - bottom < 0.4:
            return False
        self.openings.append(Opening(edge_idx, u0, u1, bottom, top, "window"))
        return True

    def openings_by_edge(self) -> dict[int, list[Opening]]:
        out: dict[int, list[Opening]] = {}
        for op in self.openings:
            out.setdefault(op.edge_idx, []).append(op)
        for ops in out.values():
            ops.sort(key=lambda o: o.u0)
        return out

    def add_door_frame(self, frame_mesh, protrude_m: float = 0.07, jamb_w: float = 0.14) -> None:
        a, _, _, (tx, ty), (nx, ny) = _edge_frame(self.ring, self.door_edge_idx)
        u0, u1 = self.door_range(self.door_edge_idx)
        z_top = self.floor_z + self.door_height_m
        _add_box_on_wall(frame_mesh, a[0], a[1], tx, ty, nx, ny, u0 - jamb_w, u0, self.base_m, z_top + jamb_w, 0.0, protrude_m)
        _add_box_on_wall(frame_mesh, a[0], a[1], tx, ty, nx, ny, u1, u1 + jamb_w, self.base_m, z_top + jamb_w, 0.0, protrude_m)
        _add_box_on_wall(frame_mesh, a[0], a[1], tx, ty, nx, ny, u0 - jamb_w, u1 + jamb_w, z_top, z_top + jamb_w, 0.0, protrude_m)


def add_window_frame_and_glass(frame_mesh, glass_mesh, ox, oy, tx, ty, nx, ny, u0, u1, z0, z1,
                               frame_w: float = 0.07, protrude_m: float = 0.06, wall_thickness_m: float = 0.4) -> None:
    """Open window: frame ring around the opening and a clear double-sided pane inside the reveal."""
    _add_box_on_wall(frame_mesh, ox, oy, tx, ty, nx, ny, u0 - frame_w, u0, z0 - frame_w, z1 + frame_w, 0.0, protrude_m)
    _add_box_on_wall(frame_mesh, ox, oy, tx, ty, nx, ny, u1, u1 + frame_w, z0 - frame_w, z1 + frame_w, 0.0, protrude_m)
    _add_box_on_wall(frame_mesh, ox, oy, tx, ty, nx, ny, u0, u1, z1, z1 + frame_w, 0.0, protrude_m)
    _add_box_on_wall(frame_mesh, ox, oy, tx, ty, nx, ny, u0, u1, z0 - frame_w, z0, 0.0, protrude_m)
    d = -0.12 if wall_thickness_m > 0.15 else 0.0

    def p(u, z):
        return (ox + tx * u + nx * d, oy + ty * u + ny * d, z)

    _add_quad(glass_mesh, p(u0, z0), p(u1, z0), p(u1, z1), p(u0, z1))  # facing outward
    _add_quad(glass_mesh, p(u1, z0), p(u0, z0), p(u0, z1), p(u1, z1))  # facing inward


def add_walls_with_openings(mesh, polygon: Polygon, height_m: float, base_m: float, openings_by_edge: dict) -> None:
    """Exterior wall faces like Mesh.add_walls, with rectangular holes for the registered openings."""
    ring = list(orient_polygons(polygon).exterior.coords)
    top = base_m + height_m
    for idx in range(len(ring) - 1):
        a, b, length, (tx, ty), _ = _edge_frame(ring, idx)
        if length <= 1e-9:
            continue
        _add_wall_strips(mesh, a, (tx, ty), length, base_m, top, openings_by_edge.get(idx, []), inward=False)


def _add_wall_strips(mesh, origin, t, length, z_bottom, z_top, openings, inward: bool, u_shift: float = 0.0):
    tx, ty = t

    def p(u, z):
        return (round(origin[0] + tx * u, 4), round(origin[1] + ty * u, 4), round(z, 4))

    def quad(ua, ub, za, zb):
        if ub - ua < 1e-4 or zb - za < 1e-4:
            return
        if inward:
            _add_quad(mesh, p(ub, za), p(ua, za), p(ua, zb), p(ub, zb))
        else:
            _add_quad(mesh, p(ua, za), p(ub, za), p(ub, zb), p(ua, zb))

    cursor = 0.0
    for op in openings:
        u0 = max(0.0, min(length, op.u0 - u_shift))
        u1 = max(0.0, min(length, op.u1 - u_shift))
        if u1 <= u0:
            continue
        quad(cursor, u0, z_bottom, z_top)
        quad(u0, u1, z_bottom, max(z_bottom, min(z_top, op.z0)))
        quad(u0, u1, min(z_top, max(z_bottom, op.z1)), z_top)
        cursor = max(cursor, u1)
    quad(cursor, length, z_bottom, z_top)


def _offset_ring_inward(ring, d):
    """Mitre offset of a closed CCW ring by d metres inward; vertex i starts inner edge i."""
    pts = ring[:-1]
    n = len(pts)
    lines = []
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dy)
        tx, ty = dx / length, dy / length
        ix, iy = -ty, tx
        lines.append(((a[0] + ix * d, a[1] + iy * d), (tx, ty)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-6:
            out.append(p2)
            continue
        s = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * s, p1[1] + d1[1] * s))
    out.append(out[0])
    return out


def _rect(center, t, half_len, half_depth):
    tx, ty = t
    nx, ny = -ty, tx
    cx, cy = center
    return Polygon([
        (cx - tx * half_len - nx * half_depth, cy - ty * half_len - ny * half_depth),
        (cx + tx * half_len - nx * half_depth, cy + ty * half_len - ny * half_depth),
        (cx + tx * half_len + nx * half_depth, cy + ty * half_len + ny * half_depth),
        (cx - tx * half_len + nx * half_depth, cy - ty * half_len + ny * half_depth),
    ])


def _add_block(mesh, center, t, half_len, half_depth, z0, z1, add_bottom: bool = False):
    """Closed oriented box (outward faces, top included)."""
    tx, ty = t
    rx, ry = ty, -tx
    cx, cy = center

    def pt(u, v, z):
        return (round(cx + tx * u + rx * v, 4), round(cy + ty * u + ry * v, 4), round(z, 4))

    b0, b1, b2, b3 = pt(-half_len, half_depth, z0), pt(half_len, half_depth, z0), pt(half_len, -half_depth, z0), pt(-half_len, -half_depth, z0)
    t0, t1, t2, t3 = pt(-half_len, half_depth, z1), pt(half_len, half_depth, z1), pt(half_len, -half_depth, z1), pt(-half_len, -half_depth, z1)
    _add_quad(mesh, b0, b1, t1, t0)
    _add_quad(mesh, b1, b2, t2, t1)
    _add_quad(mesh, b2, b3, t3, t2)
    _add_quad(mesh, b3, b0, t0, t3)
    _add_quad(mesh, t0, t1, t2, t3)
    if add_bottom:
        _add_quad(mesh, b1, b0, b3, b2)


def _yaw_deg(from_xy, to_xy):
    """Unreal yaw (X = north, Y = east) of the direction from_xy -> to_xy given in (east, north)."""
    return round(degrees(atan2(to_xy[0] - from_xy[0], to_xy[1] - from_xy[1])), 2)


class _Walkable:
    def __init__(self, room: Polygon):
        self.room = room
        self.free_area = room.buffer(-CAPSULE_RADIUS_M, join_style="mitre")
        minx, miny, maxx, maxy = room.bounds
        self.xs = np.arange(minx + GRID_STEP_M * 0.5, maxx, GRID_STEP_M)
        self.ys = np.arange(miny + GRID_STEP_M * 0.5, maxy, GRID_STEP_M)

    def reachable(self, obstacles: list[Polygon], start_xy, targets) -> list[bool]:
        blocked = unary_union([o.buffer(CAPSULE_RADIUS_M, join_style="mitre") for o in obstacles]) if obstacles else None
        area = self.free_area.difference(blocked) if blocked is not None else self.free_area
        nx_, ny_ = len(self.xs), len(self.ys)
        xx, yy = np.meshgrid(self.xs, self.ys)
        free = shapely.contains_xy(area, xx, yy) if not area.is_empty else np.zeros((ny_, nx_), dtype=bool)

        def snap(xy):
            best = None
            for j in range(max(0, int((xy[1] - self.ys[0]) / GRID_STEP_M) - 3), min(ny_, int((xy[1] - self.ys[0]) / GRID_STEP_M) + 4)):
                for i in range(max(0, int((xy[0] - self.xs[0]) / GRID_STEP_M) - 3), min(nx_, int((xy[0] - self.xs[0]) / GRID_STEP_M) + 4)):
                    if free[j, i]:
                        d = hypot(self.xs[i] - xy[0], self.ys[j] - xy[1])
                        if d <= 0.45 and (best is None or d < best[0]):
                            best = (d, j, i)
            return None if best is None else (best[1], best[2])

        start = snap(start_xy)
        if start is None:
            return [False for _ in targets]
        seen = np.zeros_like(free)
        seen[start] = True
        queue = deque([start])
        while queue:
            j, i = queue.popleft()
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jj, ii = j + dj, i + di
                if 0 <= jj < ny_ and 0 <= ii < nx_ and free[jj, ii] and not seen[jj, ii]:
                    seen[jj, ii] = True
                    queue.append((jj, ii))
        out = []
        for xy in targets:
            cell = snap(xy)
            out.append(cell is not None and bool(seen[cell]))
        return out


@dataclass
class _Furniture:
    kind: str
    footprint: Polygon
    front_xy: tuple[float, float] | None = None
    front_yaw: float = 0.0


def build_interior(meshes, shell: InteriorShell, template: dict) -> dict:
    """Add room geometry for one InteriorShell and return its package entry (Unreal + report)."""
    if shell.ceiling_z is None:
        raise ValueError(f"{shell.id}: exterior builder did not set the ceiling height")
    floor_z = shell.floor_z
    ceil_z = round(shell.ceiling_z, 4)
    if ceil_z - floor_z < 2.5:
        raise ValueError(f"{shell.id}: room height {ceil_z - floor_z:.2f} m is below 2.5 m")
    wt = shell.wall_thickness_m
    ring = shell.ring
    inner_ring = _offset_ring_inward(ring, wt)
    room = Polygon(inner_ring)
    if not room.is_valid or room.area < 8.0:
        raise ValueError(f"{shell.id}: inner room polygon is invalid")
    for idx in range(len(ring) - 1):
        _, _, _, t_out, _ = _edge_frame(ring, idx)
        _, _, length_in, t_in, _ = _edge_frame(inner_ring, idx)
        if length_in > 1e-6 and (t_out[0] * t_in[0] + t_out[1] * t_in[1]) < 0.0:
            raise ValueError(f"{shell.id}: wall thickness collapses edge {idx}")
    if not shell.polygon.contains(room):
        raise ValueError(f"{shell.id}: inner room leaves the OSM footprint")

    floor_mesh = meshes["InteriorFloor"]
    walls_mesh = meshes["InteriorWalls"]
    ceiling_mesh = meshes["InteriorCeiling"]
    furn_mesh = meshes["InteriorFurniture"]
    goods_mesh = meshes["InteriorGoods"]
    lamp_mesh = meshes["InteriorLamp"]

    # Floor (up) and ceiling (down)
    floor_mesh.add_surface(room, floor_z)
    for tri in orient_polygons(constrained_delaunay_triangles(room)).geoms:
        c = list(tri.exterior.coords)[:3]
        ceiling_mesh.triangles.append(tuple(ceiling_mesh.vertex(xy, ceil_z) for xy in reversed(c)))

    # Inner wall faces with the same openings, plus reveals
    by_edge = shell.openings_by_edge()
    for idx in range(len(ring) - 1):
        a_out, _, _, t, _ = _edge_frame(ring, idx)
        a_in, _, length_in, _, _ = _edge_frame(inner_ring, idx)
        if length_in <= 1e-6:
            continue
        s0 = (a_in[0] - a_out[0]) * t[0] + (a_in[1] - a_out[1]) * t[1]
        ops = [op for op in by_edge.get(idx, [])]
        clipped = [Opening(op.edge_idx, op.u0, op.u1, max(floor_z, op.z0), min(ceil_z, op.z1), op.kind) for op in ops]
        _add_wall_strips(walls_mesh, a_in, t, length_in, floor_z, ceil_z, clipped, inward=True, u_shift=s0)
    for op in shell.openings:
        a, _, _, (tx, ty), (nx, ny) = _edge_frame(ring, op.edge_idx)
        ix, iy = -nx * wt, -ny * wt
        o0 = (a[0] + tx * op.u0, a[1] + ty * op.u0)
        o1 = (a[0] + tx * op.u1, a[1] + ty * op.u1)
        i0 = (o0[0] + ix, o0[1] + iy)
        i1 = (o1[0] + ix, o1[1] + iy)
        z0, z1 = op.z0, op.z1
        _add_quad(walls_mesh, (*o0, z0), (*i0, z0), (*i0, z1), (*o0, z1))   # left jamb
        _add_quad(walls_mesh, (*i1, z0), (*o1, z0), (*o1, z1), (*i1, z1))   # right jamb
        _add_quad(walls_mesh, (*o0, z1), (*i0, z1), (*i1, z1), (*o1, z1))   # head
        sill_mesh = floor_mesh if op.kind == "door" else walls_mesh
        _add_quad(sill_mesh, (*o0, z0), (*o1, z0), (*i1, z0), (*i0, z0))    # sill / threshold

    # Steps in front of the door when the floor sits above the outside ground
    rise = floor_z - shell.outside_ground_z
    a, _, _, (tx, ty), (nx, ny) = _edge_frame(ring, shell.door_edge_idx)
    du0, du1 = shell.door_range(shell.door_edge_idx, 0.25)
    if rise > 0.22:
        n_steps = max(1, int(ceil(rise / 0.18)))
        for k in range(n_steps):
            z_top = shell.outside_ground_z + rise * (k + 1) / n_steps - 0.005
            depth = 0.32 * (n_steps - k)
            _add_box_on_wall(meshes["InteriorFloor"], a[0], a[1], tx, ty, nx, ny, du0, du1, shell.outside_ground_z - 0.3, z_top, 0.0, depth)
            # top face for walking
            p = lambda u, d, z: (a[0] + tx * u + nx * d, a[1] + ty * u + ny * d, z)
            _add_quad(meshes["InteriorFloor"], p(du0, depth, z_top), p(du1, depth, z_top), p(du1, 0.0, z_top), p(du0, 0.0, z_top))

    # --- furniture --------------------------------------------------------------------------------
    door_in = (shell.door_outer_xy[0] + shell.inward[0] * (wt + 0.55), shell.door_outer_xy[1] + shell.inward[1] * (wt + 0.55))
    walk = _Walkable(room)
    clear_room = room.buffer(-0.9, join_style="mitre")
    furniture: list[_Furniture] = []
    required_points: list[tuple[float, float]] = []

    # Counter (Tresen / Schalter), parallel to the door wall
    counter_cfg = template.get("counter") or {}
    counter = None
    if counter_cfg:
        half_len = float(counter_cfg.get("length_m", 2.4)) * 0.5
        half_dep = float(counter_cfg.get("depth_m", 0.6)) * 0.5
        dist = float(counter_cfg.get("distance_from_door_m", 2.8))
        lat = float(counter_cfg.get("lateral_offset_m", 2.0))
        candidates = [(dist + dd, l) for dd in (0.0, 0.8, -0.6, 1.6) for l in (lat, -lat, 0.0)]
        for dd, ll in candidates:
            cx = shell.door_outer_xy[0] + shell.inward[0] * (wt + dd) + shell.tangent[0] * ll
            cy = shell.door_outer_xy[1] + shell.inward[1] * (wt + dd) + shell.tangent[1] * ll
            rect = _rect((cx, cy), shell.tangent, half_len, half_dep)
            if not clear_room.contains(rect):
                continue
            customer = (cx - shell.inward[0] * (half_dep + 0.65), cy - shell.inward[1] * (half_dep + 0.65))
            staff = (cx + shell.inward[0] * (half_dep + 0.6), cy + shell.inward[1] * (half_dep + 0.6))
            if all(walk.reachable([rect], door_in, [customer, staff])):
                counter = _Furniture("counter", rect)
                counter.front_xy = customer
                counter_center = (cx, cy)
                counter_staff = staff
                break
        if counter is None:
            raise ValueError(f"{shell.id}: no walkable position for the counter")
        _add_block(furn_mesh, counter_center, shell.tangent, half_len, half_dep, floor_z, floor_z + float(counter_cfg.get("height_m", 1.0)))
        _add_block(goods_mesh, counter_center, shell.tangent, half_len + 0.05, half_dep + 0.05,
                   floor_z + float(counter_cfg.get("height_m", 1.0)), floor_z + float(counter_cfg.get("height_m", 1.0)) + 0.04)
        furniture.append(counter)
        required_points += [counter.front_xy, counter_staff]

    # Notice board (Aushang) on a wall with a free 1.6 m span, 1.5..7 m from the door
    board = None
    if template.get("notice_board"):
        order = list(range(shell.door_edge_idx + 1, len(ring) - 1)) + list(range(0, shell.door_edge_idx + 1))
        for idx in order:
            a_in, _, length_in, t, _ = _edge_frame(inner_ring, idx)
            if length_in < 2.2:
                continue
            a_out, _, _, _, _ = _edge_frame(ring, idx)
            s0 = (a_in[0] - a_out[0]) * t[0] + (a_in[1] - a_out[1]) * t[1]
            ops = [(op.u0 - s0, op.u1 - s0) for op in by_edge.get(idx, [])]
            n_in = (-t[1], t[0])
            for u_c in np.arange(0.8, length_in - 0.79, 0.25):
                if any(u_c + 0.62 > o0 and u_c - 0.62 < o1 for o0, o1 in ops):
                    continue
                wall_xy = (a_in[0] + t[0] * u_c, a_in[1] + t[1] * u_c)
                front = (wall_xy[0] + n_in[0] * 0.85, wall_xy[1] + n_in[1] * 0.85)
                if not (1.5 <= hypot(front[0] - door_in[0], front[1] - door_in[1]) <= 9.0):
                    continue
                if any(f.footprint.distance(Point(front)) < 0.6 for f in furniture):
                    continue
                if not walk.reachable([f.footprint for f in furniture], door_in, [front])[0]:
                    continue
                board = {"edge": idx, "u": float(u_c), "wall_xy": wall_xy, "front": front, "t": t, "n_in": n_in}
                break
            if board:
                break
        if board is None:
            raise ValueError(f"{shell.id}: no wall span for the notice board")
        bx, by = board["wall_xy"]
        t = board["t"]
        n_in = board["n_in"]
        c = (bx + n_in[0] * 0.025, by + n_in[1] * 0.025)
        _add_block(meshes["NoticeBoard"], c, t, 0.5, 0.025, floor_z + 1.05, floor_z + 2.0)
        for k, (du, dz) in enumerate(((-0.3, 1.58), (0.0, 1.64), (0.3, 1.55), (-0.18, 1.24), (0.16, 1.22))):
            pc = (c[0] + t[0] * du + n_in[0] * 0.03, c[1] + t[1] * du + n_in[1] * 0.03)
            _add_block(meshes["NoticePaper"], pc, t, 0.105, 0.006, floor_z + dz - 0.15, floor_z + dz + 0.15)
        required_points.append(board["front"])

    # Wall units (shelves, chair rows) along the inner walls
    stand_spots: list[dict] = []
    if counter is not None:
        stand_spots.append({"xy": counter_staff, "yaw": _yaw_deg(counter_staff, counter_center), "role": "staff"})
    units = template.get("wall_units") or []
    door_clear = float(template.get("door_clearance_m", 2.6))
    for unit in units:
        max_count = int(unit.get("max_count", 99))
        placed = 0
        u_len = float(unit.get("length_m", 1.6))
        depth = float(unit.get("depth_m", 0.45))
        height = float(unit.get("height_m", 1.9))
        step = u_len + float(unit.get("gap_m", 0.25))
        for idx in range(len(ring) - 1):
            if placed >= max_count:
                break
            a_in, _, length_in, t, _ = _edge_frame(inner_ring, idx)
            if length_in < u_len + 1.0:
                continue
            a_out, _, _, _, _ = _edge_frame(ring, idx)
            s0 = (a_in[0] - a_out[0]) * t[0] + (a_in[1] - a_out[1]) * t[1]
            # Low units (chairs) may stand below a window sill; tall ones keep windows free.
            ops = [
                (op.u0 - s0, op.u1 - s0) for op in by_edge.get(idx, [])
                if not (op.kind == "window" and op.z0 - floor_z > height + 0.05)
            ]
            n_in = (-t[1], t[0])
            u_c = 0.6 + u_len * 0.5
            while u_c + u_len * 0.5 <= length_in - 0.6 and placed < max_count:
                if any(u_c + u_len * 0.5 + 0.25 > o0 and u_c - u_len * 0.5 - 0.25 < o1 for o0, o1 in ops):
                    u_c += 0.5
                    continue
                center = (a_in[0] + t[0] * u_c + n_in[0] * (depth * 0.5 + 0.03), a_in[1] + t[1] * u_c + n_in[1] * (depth * 0.5 + 0.03))
                rect = _rect(center, t, u_len * 0.5, depth * 0.5)
                front = (center[0] + n_in[0] * (depth * 0.5 + 0.55), center[1] + n_in[1] * (depth * 0.5 + 0.55))
                too_close = (
                    hypot(center[0] - door_in[0], center[1] - door_in[1]) < door_clear
                    or not room.buffer(0.02).contains(rect)
                    or any(f.footprint.buffer(0.95).intersects(rect) for f in furniture)
                    or (board is not None and Point(board["wall_xy"]).buffer(0.9).intersects(rect))
                )
                if not too_close:
                    checks = walk.reachable([f.footprint for f in furniture] + [rect], door_in, required_points + [front])
                    if all(checks):
                        furniture.append(_Furniture(unit["kind"], rect, front, _yaw_deg(front, center)))
                        _add_wall_unit(meshes, unit, center, t, n_in, u_len, depth, height, floor_z)
                        placed += 1
                        if unit.get("stand_spot", True):
                            stand_spots.append({"xy": front, "yaw": _yaw_deg(front, center), "role": unit["kind"]})
                        u_c += step
                        continue
                u_c += 0.5

    # Free-standing gondolas in large rooms (Kaufhaus)
    gondola_cfg = template.get("center_gondolas")
    if gondola_cfg:
        mrr = room.minimum_rotated_rectangle
        coords = list(mrr.exterior.coords)
        e0 = (coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
        e1 = (coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
        axis = e0 if hypot(*e0) >= hypot(*e1) else e1
        al = hypot(*axis)
        t = (axis[0] / al, axis[1] / al)
        n = (-t[1], t[0])
        cen = room.centroid
        g_len = float(gondola_cfg.get("length_m", 4.0))
        g_dep = float(gondola_cfg.get("depth_m", 0.9))
        g_h = float(gondola_cfg.get("height_m", 1.4))
        for k, off in enumerate(gondola_cfg.get("offsets_m", [-2.4, 2.4])):
            center = (cen.x + n[0] * off, cen.y + n[1] * off)
            rect = _rect(center, t, g_len * 0.5, g_dep * 0.5)
            front = (center[0] + n[0] * (g_dep * 0.5 + 0.55) * (1 if off >= 0 else -1),
                     center[1] + n[1] * (g_dep * 0.5 + 0.55) * (1 if off >= 0 else -1))
            if not clear_room.contains(rect) or any(f.footprint.buffer(1.0).intersects(rect) for f in furniture):
                continue
            if all(walk.reachable([f.footprint for f in furniture] + [rect], door_in, required_points + [front])):
                furniture.append(_Furniture("gondola", rect, front, _yaw_deg(front, center)))
                _add_block(furn_mesh, center, t, g_len * 0.5, g_dep * 0.5, floor_z, floor_z + 0.12)
                for lvl in (0.45, 0.9, g_h):
                    _add_block(furn_mesh, center, t, g_len * 0.5, g_dep * 0.5, floor_z + lvl - 0.03, floor_z + lvl)
                for lvl in (0.12, 0.48, 0.93):
                    _add_block(goods_mesh, center, t, g_len * 0.5 - 0.1, g_dep * 0.5 - 0.06, floor_z + lvl, floor_z + lvl + 0.26)
                _add_block(furn_mesh, (center[0], center[1]), t, g_len * 0.5, 0.03, floor_z, floor_z + g_h)
                stand_spots.append({"xy": front, "yaw": _yaw_deg(front, center), "role": "gondola"})

    max_spots = int(template.get("max_visible_citizens", 6))
    stand_spots = stand_spots[:max_spots]

    # Ceiling lights on a ~5 m grid
    lights = []
    minx, miny, maxx, maxy = room.bounds
    spacing = float(template.get("light_spacing_m", 5.0))
    inner = prep(room.buffer(-1.0))
    for y in np.arange(miny + spacing * 0.5, maxy, spacing):
        for x in np.arange(minx + spacing * 0.5, maxx, spacing):
            if inner.contains(Point(float(x), float(y))):
                lights.append((float(x), float(y)))
    if not lights:
        c = room.representative_point()
        lights = [(c.x, c.y)]
    max_lights = int(template.get("max_lights", 6))
    if len(lights) > max_lights:
        # evenly spread over the whole room instead of the first grid rows
        lights = [lights[round(i * (len(lights) - 1) / (max_lights - 1))] for i in range(max_lights)] if max_lights > 1 else lights[:1]
    for lx, ly in lights:
        _add_block(lamp_mesh, (lx, ly), (1.0, 0.0), 0.28, 0.28, ceil_z - 0.07, ceil_z - 0.01)

    # Door leaf in hinge-local coordinates (east, north, z above floor); swings inward by open_yaw_deg
    half = shell.door_width_m * 0.5
    hinge = (
        shell.door_outer_xy[0] - shell.tangent[0] * half + shell.inward[0] * (wt * 0.5),
        shell.door_outer_xy[1] - shell.tangent[1] * half + shell.inward[1] * (wt * 0.5),
    )
    leaf = {"vertices": [], "triangles": []}

    class _M:
        vertices = leaf["vertices"]
        triangles = leaf["triangles"]

    leaf_w = shell.door_width_m - 0.04
    _add_block(_M, (shell.tangent[0] * (leaf_w * 0.5 + 0.02), shell.tangent[1] * (leaf_w * 0.5 + 0.02)),
               shell.tangent, leaf_w * 0.5, 0.03, 0.0, shell.door_height_m - 0.02, add_bottom=True)
    # door handle on both faces
    hx = shell.tangent[0] * (leaf_w - 0.08)
    hy = shell.tangent[1] * (leaf_w - 0.08)
    _add_block(_M, (hx, hy), shell.tangent, 0.06, 0.07, 1.0, 1.06)

    walk_check = walk.reachable([f.footprint for f in furniture], door_in,
                                [s["xy"] for s in stand_spots] + ([counter.front_xy] if counter else []) + ([board["front"]] if board else []))
    entry = {
        "id": shell.id,
        "place_id": shell.cfg["place_id"],
        "building_id": shell.cfg["building_id"],
        "name": shell.cfg.get("name", ""),
        "room_type": shell.cfg.get("room_type", "shop"),
        "template": shell.cfg.get("template", ""),
        "layout_source": shell.cfg.get("layout_source", "assumed_sprint13_interior_layout"),
        "floor_z_m": floor_z,
        "ceiling_z_m": ceil_z,
        "room_polygon_m": [[round(x, 4), round(y, 4)] for x, y in inner_ring[:-1]],
        "room_area_m2": round(room.area, 2),
        "door": {
            "center_m": [round(shell.door_outer_xy[0] + shell.inward[0] * wt * 0.5, 4),
                         round(shell.door_outer_xy[1] + shell.inward[1] * wt * 0.5, 4), floor_z],
            "outer_center_m": [round(shell.door_outer_xy[0], 4), round(shell.door_outer_xy[1], 4), floor_z],
            "outside_m": [round(shell.door_outer_xy[0] + shell.outward[0] * 0.6, 4),
                          round(shell.door_outer_xy[1] + shell.outward[1] * 0.6, 4), round(shell.outside_ground_z, 4)],
            "inside_m": [round(door_in[0], 4), round(door_in[1], 4), floor_z],
            "hinge_m": [round(hinge[0], 4), round(hinge[1], 4), floor_z],
            "inward": [round(shell.inward[0], 6), round(shell.inward[1], 6)],
            "width_m": shell.door_width_m,
            "height_m": shell.door_height_m,
            "open_yaw_deg": -95.0,
            "leaf_mesh": {"color": [0.30, 0.18, 0.10], "vertices": [[round(c, 4) for c in v] for v in leaf["vertices"]], "triangles": leaf["triangles"]},
        },
        "counter_m": [round(counter.front_xy[0], 4), round(counter.front_xy[1], 4), floor_z] if counter else None,
        "notice_board_m": [round(board["front"][0], 4), round(board["front"][1], 4), floor_z] if board else None,
        "stand_spots": [
            {"position_m": [round(s["xy"][0], 4), round(s["xy"][1], 4), floor_z], "yaw_deg": s["yaw"], "role": s["role"]}
            for s in stand_spots
        ],
        "lights_m": [[round(x, 4), round(y, 4), round(ceil_z - 0.35, 4)] for x, y in lights],
        "openings": [
            {"edge": op.edge_idx, "kind": op.kind, "u0_m": round(op.u0, 4), "u1_m": round(op.u1, 4), "z0_m": round(op.z0, 4), "z1_m": round(op.z1, 4)}
            for op in shell.openings
        ],
        "furniture": [{"kind": f.kind, "footprint_m": [[round(x, 4), round(y, 4)] for x, y in list(f.footprint.exterior.coords)[:-1]]} for f in furniture],
        "walkable_from_door": all(walk_check),
    }
    return entry


def _add_wall_unit(meshes, unit, center, t, n_in, u_len, depth, height, floor_z):
    furn = meshes["InteriorFurniture"]
    goods = meshes["InteriorGoods"]
    kind = unit["kind"]
    if kind == "chair_row":
        count = int(unit.get("chairs", 4))
        pitch = u_len / count
        for k in range(count):
            off = -u_len * 0.5 + pitch * (k + 0.5)
            c = (center[0] + t[0] * off, center[1] + t[1] * off)
            _add_block(furn, c, t, 0.22, 0.22, floor_z + 0.42, floor_z + 0.47)
            back = (c[0] - n_in[0] * 0.2, c[1] - n_in[1] * 0.2)
            _add_block(furn, back, t, 0.22, 0.03, floor_z + 0.47, floor_z + 0.95)
            for sx in (-0.18, 0.18):
                for sy in (-0.18, 0.18):
                    leg = (c[0] + t[0] * sx + n_in[0] * sy, c[1] + t[1] * sx + n_in[1] * sy)
                    _add_block(furn, leg, t, 0.025, 0.025, floor_z, floor_z + 0.42)
        return
    # Shelf: back panel, side panels, boards and goods
    back = (center[0] - n_in[0] * (depth * 0.5 - 0.02), center[1] - n_in[1] * (depth * 0.5 - 0.02))
    _add_block(furn, back, t, u_len * 0.5, 0.02, floor_z, floor_z + height)
    for side in (-1.0, 1.0):
        sc = (center[0] + t[0] * side * (u_len * 0.5 - 0.02), center[1] + t[1] * side * (u_len * 0.5 - 0.02))
        _add_block(furn, sc, t, 0.02, depth * 0.5, floor_z, floor_z + height)
    levels = int(unit.get("levels", 4))
    for k in range(levels):
        z = floor_z + 0.1 + k * (height - 0.15) / levels
        _add_block(furn, center, t, u_len * 0.5 - 0.04, depth * 0.5, z, z + 0.03)
        _add_block(goods, center, t, u_len * 0.5 - 0.12, depth * 0.5 - 0.08, z + 0.03, z + 0.03 + min(0.3, (height - 0.15) / levels - 0.08))
    if unit.get("counter_top"):
        _add_block(furn, center, t, u_len * 0.5, depth * 0.5, floor_z, floor_z + 0.9)


def load_interior_shells(config: dict | None, scene_buildings_by_id: dict, base_z_fn, ground_z_fn, polygon_fn) -> dict[str, InteriorShell]:
    """Create InteriorShells for configured buildings (keyed by OSM building id)."""
    shells: dict[str, InteriorShell] = {}
    if not config:
        return shells
    assumptions = config.get("assumptions") or {}
    seen_places = set()
    for cfg in config.get("interiors", []):
        bid = cfg["building_id"]
        if bid not in scene_buildings_by_id:
            raise ValueError(f"interior {cfg['id']} references unknown building {bid}")
        if cfg["place_id"] in seen_places:
            raise ValueError(f"duplicate interior for place {cfg['place_id']}")
        seen_places.add(cfg["place_id"])
        polygon = polygon_fn(scene_buildings_by_id[bid])
        shells[bid] = InteriorShell(cfg, polygon, base_z_fn(bid), ground_z_fn, assumptions)
    return shells
