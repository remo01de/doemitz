"""Build prototype meshes (in local meters) for HISM instanced Altstadt props and vegetation."""

from math import cos, sin, tau


LAMP_METAL = (0.11, 0.12, 0.13)
LANTERN_GLOW = (1.00, 0.84, 0.48)
TIMBER = (0.28, 0.16, 0.09)
TERRACOTTA = (0.74, 0.31, 0.21)
TRUNK = (0.26, 0.17, 0.11)
FOLIAGE_VARIANTS = (
    (0.24, 0.54, 0.16),
    (0.15, 0.42, 0.14),
    (0.10, 0.30, 0.11),
)


def _add_cylinder(verts, tris, cols, cx, cy, z0, z1, r0, r1, color, sides=8):
    base = len(verts)
    for i in range(sides):
        a = tau * i / sides
        verts.append((cx + r0 * cos(a), cy + r0 * sin(a), z0))
        if cols is not None:
            cols.append(color)
    for i in range(sides):
        a = tau * i / sides
        verts.append((cx + r1 * cos(a), cy + r1 * sin(a), z1))
        if cols is not None:
            cols.append(color)
    top = base + sides
    for i in range(sides):
        j = (i + 1) % sides
        tris.extend(((base + i, base + j, top + j), (base + i, top + j, top + i)))
    for i in range(1, sides - 1):
        tris.extend(((base, base + i + 1, base + i), (top, top + i, top + i + 1)))


def _add_box(verts, tris, cols, cx, cy, z0, z1, hx, hy, color):
    corners = (
        (cx - hx, cy - hy),
        (cx + hx, cy - hy),
        (cx + hx, cy + hy),
        (cx - hx, cy + hy),
    )
    base = len(verts)
    for x, y in corners:
        verts.append((x, y, z0))
        if cols is not None:
            cols.append(color)
    for x, y in corners:
        verts.append((x, y, z1))
        if cols is not None:
            cols.append(color)
    for i in range(4):
        j = (i + 1) % 4
        tris.extend(((base + i, base + j, base + 4 + j), (base + i, base + 4 + j, base + 4 + i)))
    tris.extend((
        (base + 4, base + 5, base + 6), (base + 4, base + 6, base + 7),
        (base + 0, base + 2, base + 1), (base + 0, base + 3, base + 2),
    ))


def _add_canopy_blob(verts, tris, cols, cx, cy, cz, rx, ry, rz, color, sides=6):
    rings = (
        (cz - rz, 0.15),
        (cz - rz * 0.30, 0.90),
        (cz + rz * 0.35, 0.95),
        (cz + rz, 0.15),
    )
    base = len(verts)
    for z, scale in rings:
        for i in range(sides):
            a = tau * i / sides
            verts.append((cx + rx * scale * cos(a), cy + ry * scale * sin(a), z))
            if cols is not None:
                cols.append(color)
    for r in range(len(rings) - 1):
        b0 = base + r * sides
        b1 = b0 + sides
        for i in range(sides):
            j = (i + 1) % sides
            tris.extend(((b0 + i, b0 + j, b1 + j), (b0 + i, b1 + j, b1 + i)))
    top = base + (len(rings) - 1) * sides
    for i in range(1, sides - 1):
        tris.extend(((base, base + i + 1, base + i), (top, top + i, top + i + 1)))


def street_lamp_metal():
    verts, tris = [], []
    _add_cylinder(verts, tris, None, 0.0, 0.0, 0.0, 0.45, 0.16, 0.11, None, 8)
    _add_cylinder(verts, tris, None, 0.0, 0.0, 0.45, 3.45, 0.08, 0.055, None, 8)
    _add_cylinder(verts, tris, None, 0.0, 0.0, 3.45, 3.55, 0.14, 0.18, None, 6)
    _add_cylinder(verts, tris, None, 0.0, 0.0, 3.98, 4.22, 0.24, 0.04, None, 6)
    return {"collision": False, "color": LAMP_METAL, "vertices": verts, "triangles": tris}


def street_lamp_glow():
    verts, tris = [], []
    _add_cylinder(verts, tris, None, 0.0, 0.0, 3.55, 3.98, 0.15, 0.19, None, 6)
    return {"collision": False, "color": LANTERN_GLOW, "vertices": verts, "triangles": tris}


def street_bench():
    verts, tris, cols = [], [], []
    _add_box(verts, tris, cols, 0.0, -0.65, 0.0, 0.44, 0.24, 0.06, LAMP_METAL)
    _add_box(verts, tris, cols, 0.0, 0.65, 0.0, 0.44, 0.24, 0.06, LAMP_METAL)
    _add_box(verts, tris, cols, 0.0, 0.0, 0.42, 0.49, 0.26, 0.80, TIMBER)
    _add_box(verts, tris, cols, -0.22, 0.0, 0.56, 0.86, 0.05, 0.80, TIMBER)
    return {"collision": False, "vertices": verts, "triangles": tris, "vertex_colors": cols}


def street_planter():
    verts, tris, cols = [], [], []
    _add_cylinder(verts, tris, cols, 0.0, 0.0, 0.0, 0.46, 0.22, 0.28, TERRACOTTA, 8)
    _add_canopy_blob(verts, tris, cols, 0.0, 0.0, 0.66, 0.34, 0.34, 0.30, FOLIAGE_VARIANTS[0], 6)
    return {"collision": False, "vertices": verts, "triangles": tris, "vertex_colors": cols}


def street_bollard():
    verts, tris = [], []
    _add_cylinder(verts, tris, None, 0.0, 0.0, 0.0, 0.82, 0.075, 0.06, None, 7)
    _add_cylinder(verts, tris, None, 0.0, 0.0, 0.82, 0.90, 0.08, 0.02, None, 7)
    return {"collision": False, "color": LAMP_METAL, "vertices": verts, "triangles": tris}


def stylized_tree(variant_index):
    color = FOLIAGE_VARIANTS[variant_index % len(FOLIAGE_VARIANTS)]
    verts, tris, cols = [], [], []
    trunk_h = 3.2
    canopy_r = 2.7
    _add_cylinder(verts, tris, cols, 0.0, 0.0, 0.0, trunk_h, 0.28, 0.18, TRUNK, 7)
    _add_canopy_blob(verts, tris, cols, 0.0, 0.0, trunk_h + canopy_r * 0.62, canopy_r, canopy_r * 0.95, canopy_r * 0.85, color, 6)
    _add_canopy_blob(verts, tris, cols, canopy_r * 0.42, canopy_r * 0.18, trunk_h + canopy_r * 0.42, canopy_r * 0.72, canopy_r * 0.72, canopy_r * 0.62, color, 6)
    return {"collision": False, "vertices": verts, "triangles": tris, "vertex_colors": cols}


def stylized_bush(variant_index):
    color = FOLIAGE_VARIANTS[variant_index % len(FOLIAGE_VARIANTS)]
    verts, tris, cols = [], [], []
    r = 1.45
    _add_canopy_blob(verts, tris, cols, 0.0, 0.0, r * 0.65, r, r * 0.92, r * 0.72, color, 6)
    return {"collision": False, "vertices": verts, "triangles": tris, "vertex_colors": cols}
