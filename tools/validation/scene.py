"""Check imported geometries and measure an OSM reference baseline."""

from math import dist

from pyproj import Geod
from shapely.geometry import Point, shape

from tools.geo_import.osm import node_ids


def validate(layers: dict) -> None:
    expected = {
        "roads": {"LineString", "MultiLineString"},
        "buildings": {"Polygon", "MultiPolygon"},
        "water": {"Polygon", "MultiPolygon"},
    }
    ids = set()
    for layer, allowed in expected.items():
        if not layers[layer]:
            raise ValueError(f"{layer}: empty layer")
        for feature in layers[layer]:
            feature_id = feature["id"]
            geometry = shape(feature["geometry"])
            if feature_id in ids:
                raise ValueError(f"{feature_id}: duplicate feature ID")
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in allowed:
                raise ValueError(f"{feature_id}: invalid {layer} geometry")
            ids.add(feature_id)


def reference_measurement(reference: dict, dataset, frame, roads: list) -> dict:
    way_id = reference["way_id"]
    first, second = reference["node_ids"]
    if not {first, second}.issubset(node_ids(dataset.ways[way_id])):
        raise ValueError("reference nodes no longer belong to the configured OSM way")
    start, end = dataset.nodes[first], dataset.nodes[second]
    local_start, local_end = frame.xy(*start), frame.xy(*end)
    feature = next((road for road in roads if road["id"] == f"osm:way:{way_id}"), None)
    if feature is None:
        raise ValueError("reference way is missing from the exported roads")
    road = shape(feature["geometry"])
    if any(road.distance(Point(point)) > 0.001 for point in (local_start, local_end)):
        raise ValueError("reference nodes are missing from the exported road geometry")
    _, _, geodesic_m = Geod(ellps="WGS84").inv(*start, *end)
    if geodesic_m <= 0:
        raise ValueError("reference baseline must have a positive length")
    projected_m = dist(local_start, local_end)
    error = abs(projected_m - geodesic_m) / geodesic_m
    if error > reference["maximum_relative_error"]:
        raise ValueError(f"reference error {error:.3%} exceeds the configured tolerance")
    return {
        **reference,
        "local_points_m": [local_start, local_end],
        "geodesic_m": round(geodesic_m, 4),
        "projected_m": round(projected_m, 4),
        "relative_error_percent": round(error * 100, 4),
    }
