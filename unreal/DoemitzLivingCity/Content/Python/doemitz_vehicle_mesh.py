"""Build an original low-poly compact car in local meters, with north as forward."""

from math import cos, sin, tau


PAINT = (0.055, 0.34, 0.29)
GLASS = (0.025, 0.061, 0.076)
RUBBER = (0.022, 0.025, 0.027)
METAL = (0.42, 0.45, 0.43)
HEADLIGHT = (0.95, 0.83, 0.55)
TAILLIGHT = (0.6, 0.023, 0.013)


def compact_car(paint_color=PAINT):
    paint = tuple(paint_color) if paint_color is not None else PAINT
    vertices, triangles, vertex_colors = [], [], []

    def loft(rings, color):
        sides = len(rings[0])
        base = len(vertices)
        for ring in rings:
            vertices.extend(ring)
            vertex_colors.extend([color] * sides)
        for height in range(len(rings) - 1):
            bottom = base + height * sides
            top = bottom + sides
            for i in range(sides):
                j = (i + 1) % sides
                triangles.extend(((bottom + i, bottom + j, top + j), (bottom + i, top + j, top + i)))
        top = base + (len(rings) - 1) * sides
        for i in range(1, sides - 1):
            triangles.extend(((base, base + i + 1, base + i), (top, top + i, top + i + 1)))

    def panels(profiles, color, lateral=0):
        rings = []
        for low, high, half_width, height, bevel in profiles:
            rings.append([
                (east + lateral, north, height) for east, north in (
                    (-half_width + bevel, low), (half_width - bevel, low),
                    (half_width, low + bevel), (half_width, high - bevel),
                    (half_width - bevel, high), (-half_width + bevel, high),
                    (-half_width, high - bevel), (-half_width, low + bevel),
                )
            ])
        loft(rings, color)

    def wheel(north, profile, color):
        loft([
            [
                (east, north + radius * cos(tau * i / 16), 0.30 + radius * sin(tau * i / 16))
                for i in range(16)
            ]
            for east, radius in profile
        ], color)

    panels([
        (-1.78, 1.72, 0.73, 0.32, 0.13),
        (-1.88, 1.86, 0.85, 0.44, 0.16),
        (-1.84, 1.84, 0.84, 0.77, 0.15),
        (-1.70, 1.66, 0.77, 0.91, 0.13),
    ], paint)
    panels([
        (-1.44, 0.97, 0.72, 0.88, 0.12),
        (-1.05, 0.41, 0.63, 1.39, 0.12),
    ], GLASS)
    panels([
        (-1.07, 0.43, 0.65, 1.39, 0.12),
        (-0.99, 0.36, 0.60, 1.48, 0.12),
    ], paint)

    for side in (-1, 1):
        for north in (-1.14, 1.16):
            tire = sorted((side * east, radius) for east, radius in (
                (0.61, 0.26), (0.64, 0.30), (0.87, 0.30), (0.91, 0.26),
            ))
            wheel(north, tire, RUBBER)
            rim = sorted(((side * 0.908, 0.17), (side * 0.924, 0.15)))
            wheel(north, rim, METAL)
        panels([(0.46, 0.67, 0.085, 0.91, 0.032), (0.48, 0.65, 0.074, 1.00, 0.025)], paint, side * 0.80)
        panels([(1.78, 1.87, 0.17, 0.61, 0.023), (1.77, 1.86, 0.16, 0.73, 0.023)], HEADLIGHT, side * 0.53)
        panels([(-1.88, -1.81, 0.14, 0.59, 0.018), (-1.87, -1.79, 0.13, 0.74, 0.018)], TAILLIGHT, side * 0.59)
    panels([(1.845, 1.87, 0.22, 0.47, 0.01), (1.845, 1.87, 0.22, 0.58, 0.01)], RUBBER)
    panels([(-1.89, -1.865, 0.24, 0.47, 0.008), (-1.89, -1.865, 0.24, 0.57, 0.008)], METAL)

    return {
        "collision": False,
        "vertices": vertices,
        "triangles": triangles,
        "vertex_colors": vertex_colors,
    }
