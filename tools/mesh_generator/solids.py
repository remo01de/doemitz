"""Small solid-geometry helpers (local metres, east/north/up) for detailed fortress and bridge parts.

Quads are returned as 4-point lists whose winding makes the face visible from the side its normal points to,
with the same convention as architecture._add_quad: the front side is (p1 - p0) x (p3 - p0).
"""

from __future__ import annotations

from math import cos, hypot, pi, sin


def _normal(quad):
    (x0, y0, z0), (x1, y1, z1), _, (x3, y3, z3) = quad[0], quad[1], quad[2], quad[3]
    ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
    vx, vy, vz = x3 - x0, y3 - y0, z3 - z0
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def orient(quad, toward):
    """Return the quad (or triangle) wound so that its normal points along the 3D vector `toward`."""
    pts = list(quad)
    if len(pts) == 3:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
        ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
        vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    else:
        n = _normal(pts)
    if n[0] * toward[0] + n[1] * toward[1] + n[2] * toward[2] < 0:
        pts = pts[::-1]
    return pts


def _centroid(points):
    k = float(len(points))
    return (sum(p[0] for p in points) / k, sum(p[1] for p in points) / k, sum(p[2] for p in points) / k)


def box_faces(corners, faces="all"):
    """
    Six outward faces of a hexahedron given as 8 corners [b0, b1, b2, b3, t0, t1, t2, t3] (bottom ring, then
    the top ring above it in the same order). `faces` may exclude "bottom" / "top" via a set of names.
    """
    b = corners[:4]
    t = corners[4:]
    c = _centroid(corners)
    named = [("bottom", [b[0], b[1], b[2], b[3]]), ("top", [t[0], t[1], t[2], t[3]])]
    for i in range(4):
        j = (i + 1) % 4
        named.append((f"side{i}", [b[i], b[j], t[j], t[i]]))
    out = []
    for name, q in named:
        if faces != "all" and name not in faces:
            continue
        fc = _centroid(q)
        out.append(orient(q, (fc[0] - c[0], fc[1] - c[1], fc[2] - c[2])))
    return out


def frame_point(origin, u_dir, n_dir, u, n, z):
    """Point in a vertical wall frame: origin (x, y), tangent u_dir, horizontal normal n_dir, height z."""
    return (origin[0] + u_dir[0] * u + n_dir[0] * n, origin[1] + u_dir[1] * u + n_dir[1] * n, z)


def frame_box(origin, u_dir, n_dir, u0, u1, n0, n1, z0, z1, faces="all"):
    """Axis-aligned box in a wall frame (u along the wall, n out of the wall, z up)."""
    P = lambda u, n, z: frame_point(origin, u_dir, n_dir, u, n, z)  # noqa: E731
    corners = [P(u0, n0, z0), P(u1, n0, z0), P(u1, n1, z0), P(u0, n1, z0),
               P(u0, n0, z1), P(u1, n0, z1), P(u1, n1, z1), P(u0, n1, z1)]
    return box_faces(corners, faces)


def beam(p0, p1, width, height):
    """Rectangular beam between two 3D points (width horizontal, height in the vertical plane of the beam)."""
    ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    length = (ax * ax + ay * ay + az * az) ** 0.5 or 1.0
    ax, ay, az = ax / length, ay / length, az / length
    hx, hy = -ay, ax
    hl = hypot(hx, hy)
    if hl < 1e-6:
        hx, hy, hz = 1.0, 0.0, 0.0
    else:
        hx, hy, hz = hx / hl, hy / hl, 0.0
    # up' = a x h
    vx, vy, vz = ay * hz - az * hy, az * hx - ax * hz, ax * hy - ay * hx
    w, h = width * 0.5, height * 0.5

    def at(p, sw, sh):
        return (p[0] + hx * sw * w + vx * sh * h, p[1] + hy * sw * w + vy * sh * h, p[2] + hz * sw * w + vz * sh * h)

    corners = [at(p0, -1, -1), at(p0, 1, -1), at(p0, 1, 1), at(p0, -1, 1),
               at(p1, -1, -1), at(p1, 1, -1), at(p1, 1, 1), at(p1, -1, 1)]
    return box_faces(corners)


def disc(center, normal, radius, sides=12):
    """Flat polygon facing `normal` (horizontal normal assumed), as triangles."""
    nx, ny = normal
    ux, uy = -ny, nx
    pts = [(center[0] + ux * radius * cos(2 * pi * k / sides), center[1] + uy * radius * cos(2 * pi * k / sides),
            center[2] + radius * sin(2 * pi * k / sides)) for k in range(sides)]
    tris = []
    for k in range(sides):
        tris.append(orient([center, pts[k], pts[(k + 1) % sides]], (nx, ny, 0.0)))
    return tris


def ring_quads(center, normal, r_in, r_out, sides=12):
    nx, ny = normal
    ux, uy = -ny, nx
    out = []
    for k in range(sides):
        a0, a1 = 2 * pi * k / sides, 2 * pi * (k + 1) / sides
        q = []
        for r, a in ((r_in, a0), (r_out, a0), (r_out, a1), (r_in, a1)):
            q.append((center[0] + ux * r * cos(a), center[1] + uy * r * cos(a), center[2] + r * sin(a)))
        out.append(orient(q, (nx, ny, 0.0)))
    return out


def arch_curve(half_w, spring_z, rise, segments=10):
    """(u, z) points of a semi-elliptical arch from u=-half_w to u=+half_w (spring to crown to spring)."""
    return [(-half_w * cos(pi * k / segments), spring_z + rise * sin(pi * k / segments)) for k in range(segments + 1)]


def arched_face(origin, u_dir, n_dir, n, u0, u1, z_bottom, top_fn, arch, facing):
    """
    Wall face between u0..u1 at offset n, from z_bottom (outside the arch) or the arch curve (inside it) up to
    top_fn(u), built as vertical strips so any piecewise-linear top profile and the arch are followed exactly.
    """
    au = [p[0] for p in arch]
    breaks = sorted({u0, u1, *[u for u in au if u0 < u < u1], *getattr(top_fn, "breaks", [])})
    breaks = [u for u in breaks if u0 <= u <= u1]

    def bottom(u):
        if au[0] - 1e-9 <= u <= au[-1] + 1e-9:
            for (ua, za), (ub, zb) in zip(arch, arch[1:]):
                if ua - 1e-9 <= u <= ub + 1e-9:
                    t = 0.0 if ub - ua < 1e-9 else (u - ua) / (ub - ua)
                    return za + t * (zb - za)
        return z_bottom

    quads = []
    for ua, ub in zip(breaks, breaks[1:]):
        if ub - ua < 1e-6:
            continue
        um = 0.5 * (ua + ub)
        inside = au[0] < um < au[-1]
        za0 = bottom(ua) if inside else z_bottom
        zb0 = bottom(ub) if inside else z_bottom
        za1, zb1 = top_fn(ua), top_fn(ub)
        if za1 - za0 < 1e-4 and zb1 - zb0 < 1e-4:
            continue
        q = [frame_point(origin, u_dir, n_dir, ua, n, za0), frame_point(origin, u_dir, n_dir, ub, n, zb0),
             frame_point(origin, u_dir, n_dir, ub, n, zb1), frame_point(origin, u_dir, n_dir, ua, n, za1)]
        quads.append(orient(q, facing))
    return quads


class Profile:
    """Piecewise-linear top line z(u) with its break points (for arched_face strips)."""

    def __init__(self, points):
        self.points = sorted(points)
        self.breaks = [p[0] for p in self.points]

    def __call__(self, u):
        pts = self.points
        if u <= pts[0][0]:
            return pts[0][1]
        for (ua, za), (ub, zb) in zip(pts, pts[1:]):
            if u <= ub:
                t = 0.0 if ub - ua < 1e-9 else (u - ua) / (ub - ua)
                return za + t * (zb - za)
        return pts[-1][1]
