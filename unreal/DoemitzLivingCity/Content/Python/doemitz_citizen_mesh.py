"""Build an original stylized low-poly citizen figure in local meters, with north as forward."""

from math import cos, sin, tau


SKIN = (0.78, 0.58, 0.44)
HAIR = (0.16, 0.11, 0.08)
TROUSERS = (0.15, 0.17, 0.22)
SHOES = (0.09, 0.08, 0.07)


def stylized_citizen(coat_color):
    vertices, triangles, vertex_colors = [], [], []

    def loft(rings, color):
        sides = len(rings[0])
        base = len(vertices)
        for ring in rings:
            vertices.extend(ring)
            vertex_colors.extend([color] * sides)
        for level in range(len(rings) - 1):
            bottom = base + level * sides
            top = bottom + sides
            for i in range(sides):
                j = (i + 1) % sides
                triangles.extend(((bottom + i, bottom + j, top + j), (bottom + i, top + j, top + i)))
        top = base + (len(rings) - 1) * sides
        for i in range(1, sides - 1):
            triangles.extend(((base, base + i + 1, base + i), (top, top + i, top + i + 1)))

    def cylinder(cx, cy, z0, z1, rx0, ry0, rx1, ry1, color, sides=10):
        ring0 = [
            (cx + rx0 * cos(tau * i / sides), cy + ry0 * sin(tau * i / sides), z0)
            for i in range(sides)
        ]
        ring1 = [
            (cx + rx1 * cos(tau * i / sides), cy + ry1 * sin(tau * i / sides), z1)
            for i in range(sides)
        ]
        loft([ring0, ring1], color)

    # Legs and shoes (left/right along east axis)
    for side in (-1, 1):
        cx = side * 0.11
        cylinder(cx, 0.02, 0.00, 0.08, 0.065, 0.10, 0.060, 0.09, SHOES, 8)
        cylinder(cx, 0.00, 0.08, 0.82, 0.065, 0.070, 0.082, 0.085, TROUSERS, 8)

    # Torso / stylized coat
    loft([
        [(0.22 * cos(tau * i / 12), 0.14 * sin(tau * i / 12), 0.78) for i in range(12)],
        [(0.21 * cos(tau * i / 12), 0.13 * sin(tau * i / 12), 1.08) for i in range(12)],
        [(0.24 * cos(tau * i / 12), 0.14 * sin(tau * i / 12), 1.38) for i in range(12)],
        [(0.12 * cos(tau * i / 12), 0.10 * sin(tau * i / 12), 1.44) for i in range(12)],
    ], tuple(coat_color))

    # Arms
    for side in (-1, 1):
        cx = side * 0.25
        cylinder(cx, 0.00, 0.88, 1.36, 0.048, 0.048, 0.058, 0.058, tuple(coat_color), 8)
        cylinder(cx, 0.01, 0.80, 0.88, 0.042, 0.042, 0.046, 0.046, SKIN, 8)

    # Neck and head
    cylinder(0.0, 0.0, 1.42, 1.50, 0.055, 0.055, 0.055, 0.055, SKIN, 8)
    loft([
        [(0.075 * cos(tau * i / 12), 0.080 * sin(tau * i / 12), 1.50) for i in range(12)],
        [(0.105 * cos(tau * i / 12), 0.115 * sin(tau * i / 12), 1.60) for i in range(12)],
        [(0.100 * cos(tau * i / 12), 0.110 * sin(tau * i / 12), 1.69) for i in range(12)],
        [(0.065 * cos(tau * i / 12), 0.075 * sin(tau * i / 12), 1.74) for i in range(12)],
    ], SKIN)

    # Hair cap
    loft([
        [(0.108 * cos(tau * i / 12), -0.01 + 0.116 * sin(tau * i / 12), 1.66) for i in range(12)],
        [(0.095 * cos(tau * i / 12), -0.01 + 0.105 * sin(tau * i / 12), 1.74) for i in range(12)],
        [(0.045 * cos(tau * i / 12), -0.01 + 0.050 * sin(tau * i / 12), 1.77) for i in range(12)],
    ], HAIR)

    return {
        "collision": False,
        "vertices": vertices,
        "triangles": triangles,
        "vertex_colors": vertex_colors,
    }
