"""Deterministic offline top-down stylized map renderer (PNG + pixel-to-meter metadata)."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import struct
import zlib

import numpy as np
from shapely.geometry import Polygon, shape

from tools.geo_import.export import geometry_parts


DEFAULT_MAP_SIZE_PX = 2048
MAP_ATTRIBUTION = "Kartendaten © OpenStreetMap contributors, ODbL 1.0"

# Stylized top-down palette matching the game world (RGB 0..255)
COLOR_BG = (48, 86, 36)
COLOR_TERRAIN = (68, 114, 48)
COLOR_WATER = (26, 98, 124)
COLOR_WATER_EDGE = (18, 72, 94)
COLOR_PARKING = (104, 112, 120)
COLOR_SIDEWALK = (166, 148, 124)
COLOR_PATH = (128, 112, 86)
COLOR_ROAD = (76, 78, 84)
COLOR_PAVING = (118, 102, 88)
COLOR_BUILDING_OUTLINE = (54, 42, 34)
BUILDING_ROOF_COLORS = (
    (176, 74, 52),   # Terracotta
    (144, 78, 54),   # Clay
    (74, 82, 96),    # Slate
)
STONE_SURFACES = {"cobblestone", "unhewn_cobblestone", "sett", "paving_stones", "pebblestone"}
PATH_CLASSES = {"footway", "cycleway", "path", "steps"}


def compute_map_metadata(bounds_m: tuple[float, float, float, float], size_px: int = DEFAULT_MAP_SIZE_PX) -> dict:
    """Compute square aspect-preserving pixel-to-meter mapping (East -> +X, North -> -Y)."""
    min_e, min_n, max_e, max_n = (float(v) for v in bounds_m)
    span_e = max(1.0, max_e - min_e)
    span_n = max(1.0, max_n - min_n)
    span = max(span_e, span_n) * 1.02
    center_e = 0.5 * (min_e + max_e)
    center_n = 0.5 * (min_n + max_n)
    half = 0.5 * span
    view_min_e = center_e - half
    view_max_e = center_e + half
    view_min_n = center_n - half
    view_max_n = center_n + half
    meters_per_pixel = span / float(size_px)
    return {
        "schema_version": 1,
        "image_file": "city-map.png",
        "width_px": int(size_px),
        "height_px": int(size_px),
        "bounds_m": [round(min_e, 4), round(min_n, 4), round(max_e, 4), round(max_n, 4)],
        "view_bounds_m": [
            round(view_min_e, 6),
            round(view_min_n, 6),
            round(view_max_e, 6),
            round(view_max_n, 6),
        ],
        "meters_per_pixel": round(meters_per_pixel, 8),
        "pixels_per_meter": round(float(size_px) / span, 8),
        "origin_px_axis": "top_left_x_east_y_south",
        "attribution": MAP_ATTRIBUTION,
    }


def world_to_pixel(east_m: float, north_m: float, meta: dict) -> tuple[float, float]:
    """Project local meters (east, north) to map image pixel coordinates (px, py)."""
    v_min_e, v_min_n, v_max_e, v_max_n = meta["view_bounds_m"]
    w = float(meta["width_px"])
    h = float(meta["height_px"])
    px = ((float(east_m) - v_min_e) / (v_max_e - v_min_e)) * w
    py = ((v_max_n - float(north_m)) / (v_max_n - v_min_n)) * h
    return px, py


def pixel_to_world(px: float, py: float, meta: dict) -> tuple[float, float]:
    """Unproject map image pixel coordinates (px, py) back to local meters (east, north)."""
    v_min_e, v_min_n, v_max_e, v_max_n = meta["view_bounds_m"]
    w = float(meta["width_px"])
    h = float(meta["height_px"])
    east_m = v_min_e + (float(px) / w) * (v_max_e - v_min_e)
    north_m = v_max_n - (float(py) / h) * (v_max_n - v_min_n)
    return east_m, north_m


def _rasterize_polygon(
    canvas: np.ndarray,
    polygon: Polygon,
    color: tuple[int, int, int],
    meta: dict,
    outline_color: tuple[int, int, int] | None = None,
) -> None:
    """Fast deterministic scanline polygon fill (with holes) onto an (H, W, 3) uint8 numpy image."""
    h, w, _ = canvas.shape
    v_min_e, v_min_n, v_max_e, v_max_n = meta["view_bounds_m"]
    sx = w / (v_max_e - v_min_e)
    sy = h / (v_max_n - v_min_n)

    min_e, min_n, max_e, max_n = polygon.bounds
    y0 = max(0, int(np.floor((v_max_n - max_n) * sy)))
    y1 = min(h, int(np.ceil((v_max_n - min_n) * sy)) + 1)
    x0 = max(0, int(np.floor((min_e - v_min_e) * sx)))
    x1 = min(w, int(np.ceil((max_e - v_min_e) * sx)) + 1)
    if y0 >= y1 or x0 >= x1:
        return

    box_h = y1 - y0
    box_w = x1 - x0
    parity = np.zeros((box_h, box_w), dtype=np.bool_)
    scan_ys = np.arange(y0, y1, dtype=np.float64) + 0.5

    rings = [polygon.exterior, *polygon.interiors]
    for ring in rings:
        coords = np.asarray(ring.coords, dtype=np.float64)
        if coords.shape[0] < 3:
            continue
        px = (coords[:, 0] - v_min_e) * sx
        py = (v_max_n - coords[:, 1]) * sy

        x_a = px[:-1]
        y_a = py[:-1]
        x_b = px[1:]
        y_b = py[1:]

        # Process each non-horizontal edge using vectorized scanline slice
        dy = y_b - y_a
        valid = np.abs(dy) > 1e-9
        for xa, ya, xb, yb, d in zip(x_a[valid], y_a[valid], x_b[valid], y_b[valid], dy[valid]):
            ey_lo = min(ya, yb)
            ey_hi = max(ya, yb)
            row_start = max(y0, int(np.ceil(ey_lo - 0.5)))
            row_end = min(y1, int(np.ceil(ey_hi - 0.5)))
            if row_start >= row_end:
                continue
            ys = scan_ys[row_start - y0 : row_end - y0]
            xs = xa + (ys - ya) * ((xb - xa) / d)
            ix = np.clip(np.ceil(xs - 0.5).astype(np.int64) - x0, 0, box_w)
            rows = np.arange(row_start - y0, row_end - y0)
            in_bounds = ix < box_w
            if np.any(in_bounds):
                np.logical_xor.at(parity, (rows[in_bounds], ix[in_bounds]), True)

    mask = np.logical_xor.accumulate(parity, axis=1)
    if not np.any(mask):
        return

    sub = canvas[y0:y1, x0:x1]
    sub[mask] = color

    if outline_color is not None and box_h >= 3 and box_w >= 3:
        # 1-pixel interior border of the filled polygon
        eroded = mask.copy()
        eroded[0, :] = False
        eroded[-1, :] = False
        eroded[:, 0] = False
        eroded[:, -1] = False
        eroded[1:-1, 1:-1] &= mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
        border = mask & ~eroded
        sub[border] = outline_color


def encode_png_rgb(image: np.ndarray) -> bytes:
    """Encode an (H, W, 3) uint8 RGB array into a deterministic PNG byte stream."""
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("expected (H, W, 3) uint8 RGB image")
    height, width, _ = image.shape
    raw_rows = bytearray()
    for row_idx in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
        raw_rows.extend(image[row_idx].tobytes())
    compressed = zlib.compress(bytes(raw_rows), level=9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _compute_hillshade_factor(elevation, meta: dict) -> np.ndarray | None:
    """Compute subtle deterministic NW Lambertian hillshading factor centered around 1.0."""
    if elevation is None or elevation.is_flat:
        return None
    w = int(meta["width_px"])
    h = int(meta["height_px"])
    v_min_e, v_min_n, v_max_e, v_max_n = meta["view_bounds_m"]
    xs = v_min_e + ((np.arange(w, dtype=np.float64) + 0.5) / w) * (v_max_e - v_min_e)
    ys = v_max_n - ((np.arange(h, dtype=np.float64) + 0.5) / h) * (v_max_n - v_min_n)
    ee, nn = np.meshgrid(xs, ys)
    z = elevation.sample_array(ee, nn)
    step_e = (v_max_e - v_min_e) / w
    step_n = (v_max_n - v_min_n) / h
    # Gradient: dZ/dEast (axis 1), dZ/dNorth (-axis 0 because row 0 is north)
    dz_de = np.gradient(z, step_e, axis=1)
    dz_dn = -np.gradient(z, step_n, axis=0)
    # Exaggerate relief gently (2.2x) so 10 m Festungswall & Elbtal edges read crisply on map
    exag = 2.2
    nx = -dz_de * exag
    ny = -dz_dn * exag
    nz = np.ones_like(z)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    nx *= inv_len
    ny *= inv_len
    nz *= inv_len
    # Classic cartographic NW light: azimuth 315 deg (-east, +north), altitude 45 deg
    lx, ly, lz = -0.5, 0.5, 0.70710678
    dot = nx * lx + ny * ly + nz * lz
    # Flat surface dot == lz (0.7071); center shading at 1.0 with subtle +-16% modulation
    return np.clip(1.0 + (dot - lz) * 0.42, 0.80, 1.18)


def render_city_map(
    scene: dict,
    road_width_fn,
    sidewalks: list[Polygon] | None = None,
    size_px: int = DEFAULT_MAP_SIZE_PX,
    output_png: Path | None = None,
    elevation=None,
) -> tuple[bytes, dict]:
    """Render deterministic stylized top-down PNG map from scene.json and return (png_bytes, metadata)."""
    bounds_poly = shape(scene["terrain"]["boundary"])
    meta = compute_map_metadata(bounds_poly.bounds, size_px=size_px)
    terrain_attr = scene.get("terrain", {}).get("attribution")
    if terrain_attr:
        meta["attribution"] = f"{MAP_ATTRIBUTION} | Höhendaten {terrain_attr}"
        meta["terrain_attribution"] = terrain_attr
    meta["hillshading"] = bool(elevation is not None and not elevation.is_flat)

    canvas = np.empty((size_px, size_px, 3), dtype=np.uint8)
    canvas[:, :] = COLOR_BG

    # 1. Terrain boundary
    for poly in geometry_parts(bounds_poly, "Polygon"):
        _rasterize_polygon(canvas, poly, COLOR_TERRAIN, meta)

    # Apply subtle hillshading onto terrain and background before water/buildings
    shade = _compute_hillshade_factor(elevation, meta)
    if shade is not None:
        shaded = np.clip(canvas.astype(np.float32) * shade[:, :, None].astype(np.float32), 0.0, 255.0)
        canvas[:, :] = np.rint(shaded).astype(np.uint8)

    # 2. Water polygons
    for feature in scene["layers"].get("water", []):
        for poly in geometry_parts(shape(feature["geometry"]), "Polygon"):
            _rasterize_polygon(canvas, poly, COLOR_WATER, meta, outline_color=COLOR_WATER_EDGE)

    # 3. Parking surface polygons (amenity=parking)
    for poi in scene["layers"].get("pois", []):
        props = poi.get("properties") or {}
        if props.get("amenity") == "parking":
            geom = shape(poi["geometry"])
            for poly in geometry_parts(geom, "Polygon"):
                _rasterize_polygon(canvas, poly, COLOR_PARKING, meta)

    # 4. Sidewalks
    for sw in sidewalks or []:
        for poly in geometry_parts(sw, "Polygon"):
            _rasterize_polygon(canvas, poly, COLOR_SIDEWALK, meta)

    # 5. Roads in layered order: Paths -> Roads -> Paving (matching game look)
    road_buckets: dict[str, list[Polygon]] = {"Paths": [], "Roads": [], "Paving": []}
    for road in scene["layers"].get("roads", []):
        tags = road["properties"]
        if tags.get("tunnel", "no") != "no":
            continue
        highway = tags["highway"]
        width_m, _ = road_width_fn(tags)
        geom = shape(road["geometry"]).buffer(max(width_m * 0.5, 0.9), quad_segs=3)
        bucket = "Roads"
        if tags.get("surface") in STONE_SURFACES:
            bucket = "Paving"
        elif highway in PATH_CLASSES:
            bucket = "Paths"
        for poly in geometry_parts(geom, "Polygon"):
            road_buckets[bucket].append(poly)

    for bucket, color in (("Paths", COLOR_PATH), ("Roads", COLOR_ROAD), ("Paving", COLOR_PAVING)):
        for poly in road_buckets[bucket]:
            _rasterize_polygon(canvas, poly, color, meta)

    # 6. Buildings (colored by deterministic roof palette + crisp dark outline)
    for feature in scene["layers"].get("buildings", []):
        osm_id = int(feature["id"].rsplit(":", 1)[1])
        roof_color = BUILDING_ROOF_COLORS[osm_id % len(BUILDING_ROOF_COLORS)]
        for poly in geometry_parts(shape(feature["geometry"]), "Polygon"):
            _rasterize_polygon(canvas, poly, roof_color, meta, outline_color=COLOR_BUILDING_OUTLINE)

    png_bytes = encode_png_rgb(canvas)
    meta["image_sha256"] = sha256(png_bytes).hexdigest()

    if output_png is not None:
        output_png.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_png.with_suffix(".png.tmp")
        tmp.write_bytes(png_bytes)
        tmp.replace(output_png)

    return png_bytes, meta
