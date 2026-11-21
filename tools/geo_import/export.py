"""Build clipped WGS84 feature collections and a local scene from the same extract."""

from hashlib import file_digest
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from shapely import make_valid, orient_polygons
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box, mapping, shape

from tools.geo_import import osm
from tools.geo_transform.local import LocalFrame
from tools.validation.scene import reference_measurement, validate


LAYERS = ("roads", "buildings", "water", "pois")
AREA_TAGS = ("building", "building:levels", "height", "name", "natural", "water", "waterway")
ROAD_TAGS = ("highway", "name", "bridge", "tunnel", "layer", "lanes", "width", "surface", "oneway", "maxspeed")
POI_TAGS = ("name", "shop", "amenity", "office", "tourism", "opening_hours", "building", "addr:street", "addr:housenumber")


def geometry_parts(geometry, geometry_type: str):
    if not geometry.is_empty:
        if geometry.geom_type == geometry_type:
            yield geometry
        elif hasattr(geometry, "geoms"):
            for part in geometry.geoms:
                yield from geometry_parts(part, geometry_type)


def clipped_geometry(geometry, bounds, is_area: bool):
    repaired = not geometry.is_valid
    if repaired:
        geometry = make_valid(geometry)
    clipped = geometry.intersection(bounds)
    parts = list(geometry_parts(clipped, "Polygon" if is_area else "LineString"))
    if not parts:
        return None, repaired
    if is_area:
        area = parts[0] if len(parts) == 1 else MultiPolygon(parts)
        return orient_polygons(area), repaired
    return (parts[0] if len(parts) == 1 else MultiLineString(parts)), repaired


def add_feature(layer, element_type, osm_id, attributes, geometry, bounds, layers, issues):
    feature_id = f"osm:{element_type}:{osm_id}"
    is_area = layer != "roads"
    geometry, repaired = clipped_geometry(geometry, bounds, is_area)
    if repaired:
        action = "repaired invalid source geometry" if geometry is not None else "no usable geometry after repair"
        issues.append({"id": feature_id, "reason": action})
    if geometry is None:
        return False
    keys = AREA_TAGS if is_area else ROAD_TAGS
    layers[layer].append(
        {
            "type": "Feature",
            "id": feature_id,
            "geometry": mapping(geometry),
            "properties": {key: attributes[key] for key in keys if key in attributes},
        }
    )
    return True


def add_poi_feature(element_type, osm_id, attributes, geometry, bounds, layers, issues):
    feature_id = f"poi:osm:{element_type}:{osm_id}"
    if geometry.geom_type == "Point":
        if not bounds.covers(geometry):
            return False
    else:
        geometry, repaired = clipped_geometry(geometry, bounds, True)
        if repaired:
            action = "repaired invalid source geometry" if geometry is not None else "no usable geometry after repair"
            issues.append({"id": feature_id, "reason": action})
        if geometry is None:
            return False
    props = {"osm_id": f"osm:{element_type}:{osm_id}"}
    for key in POI_TAGS:
        if key in attributes:
            props[key] = attributes[key]
    layers["pois"].append(
        {
            "type": "Feature",
            "id": feature_id,
            "geometry": mapping(geometry),
            "properties": props,
        }
    )
    return True


def extract(config: dict, raw_dir: Path):
    dataset = osm.Dataset()
    base = raw_dir / "map.osm"
    root = dataset.read(base)
    source_bounds = root.find("bounds")
    if source_bounds is not None:
        bbox = [float(source_bounds.attrib[key]) for key in ("minlon", "minlat", "maxlon", "maxlat")]
        if bbox != config["bounds_lonlat"]:
            raise ValueError("raw map bounds differ from the configured bounds")
    bounds = box(*config["bounds_lonlat"])
    layers = {layer: [] for layer in LAYERS}
    issues = []
    relation_outers = {layer: set() for layer in ("buildings", "water", "pois")}
    sources = [(base, osm.map_url(config))]
    relations = list(osm.area_relations(dataset))
    way_ids = sorted(dataset.ways)

    for relation_id, relation, _ in relations:
        supplement = raw_dir / f"relation-{relation_id}.osm"
        if supplement.is_file():
            dataset.read(supplement)
            sources.append((supplement, osm.relation_url(config, relation_id)))

    for relation_id, relation, attributes in relations:
        try:
            members_missing = osm.missing_members(dataset, relation)
        except ValueError as error:
            issues.append({"id": f"osm:relation:{relation_id}", "reason": str(error)})
            continue
        if members_missing:
            raise ValueError(f"relation {relation_id} has missing members; fetch a complete raw snapshot")
        layer = osm.area_layer(attributes)
        try:
            area = osm.multipolygon(dataset, relation)
        except ValueError as error:
            issues.append({"id": f"osm:relation:{relation_id}", "reason": str(error)})
            continue
        if add_feature(layer, "relation", relation_id, attributes, area, bounds, layers, issues):
            relation_outers[layer].update(
                way_id for way_id, role in osm.ring_members(relation) if role == "outer"
            )
        if osm.is_poi(attributes):
            if add_poi_feature("relation", relation_id, attributes, area, bounds, layers, issues):
                relation_outers["pois"].update(
                    way_id for way_id, role in osm.ring_members(relation) if role == "outer"
                )

    for way_id in way_ids:
        way = dataset.ways[way_id]
        attributes = osm.tags(way)
        layer = osm.area_layer(attributes)
        if layer and way_id not in relation_outers[layer]:
            coordinates = dataset.way_coordinates(way)
            if len(coordinates) >= 4 and coordinates[0] == coordinates[-1]:
                poly = Polygon(coordinates)
                add_feature(layer, "way", way_id, attributes, poly, bounds, layers, issues)
                if osm.is_poi(attributes) and way_id not in relation_outers["pois"]:
                    add_poi_feature("way", way_id, attributes, poly, bounds, layers, issues)
            else:
                issues.append({"id": f"osm:way:{way_id}", "reason": "unclosed area way"})
        elif not layer and attributes.get("highway") not in (None, "construction", "proposed"):
            if attributes.get("area") != "yes":
                coordinates = dataset.way_coordinates(way)
                if len(set(coordinates)) < 2:
                    issues.append({"id": f"osm:way:{way_id}", "reason": "degenerate road way"})
                    continue
                add_feature("roads", "way", way_id, attributes, LineString(coordinates), bounds, layers, issues)
        elif not layer and osm.is_poi(attributes) and way_id not in relation_outers["pois"]:
            coordinates = dataset.way_coordinates(way)
            if len(coordinates) >= 4 and coordinates[0] == coordinates[-1]:
                add_poi_feature("way", way_id, attributes, Polygon(coordinates), bounds, layers, issues)

    for node_id in sorted(dataset.node_tags):
        attributes = dataset.node_tags[node_id]
        if osm.is_poi(attributes) and node_id in dataset.nodes:
            lon, lat = dataset.nodes[node_id]
            add_poi_feature("node", node_id, attributes, Point(lon, lat), bounds, layers, issues)

    validate(layers)
    return dataset, bounds, layers, issues, sources


def write_json(path: Path, document: dict) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8", newline="\n") as stream:
        temporary = Path(stream.name)
        try:
            json.dump(document, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
            stream.close()
            temporary.replace(path)
        finally:
            stream.close()
            temporary.unlink(missing_ok=True)


def build(config: dict, raw_dir: Path, output_dir: Path) -> None:
    dataset, bounds, layers, issues, sources = extract(config, raw_dir)
    frame = LocalFrame(config["projected_crs"], config["origin_lonlat"])
    local_layers = {
        layer: [
            {**feature, "geometry": mapping(frame.geometry(shape(feature["geometry"])))}
            for feature in features
        ]
        for layer, features in layers.items()
    }
    node_id_by_local = {}
    for feature in local_layers["roads"]:
        way_id = int(feature["id"].rsplit(":", 1)[1])
        way = dataset.ways.get(way_id)
        if way is None:
            continue
        for nid in osm.node_ids(way):
            if nid in dataset.nodes:
                east, north = frame.xy(*dataset.nodes[nid])
                node_id_by_local.setdefault((round(east, 4), round(north, 4)), f"osm:node:{nid}")
    for feature in local_layers["roads"]:
        geom = feature["geometry"]
        if geom["type"] == "LineString":
            feature["node_ids"] = [
                node_id_by_local.get((round(pt[0], 4), round(pt[1], 4)))
                for pt in geom["coordinates"]
            ]
        elif geom["type"] == "MultiLineString":
            feature["node_ids"] = [
                [node_id_by_local.get((round(pt[0], 4), round(pt[1], 4))) for pt in line]
                for line in geom["coordinates"]
            ]
    validate(local_layers)
    crossings = []
    for node_id in sorted(dataset.node_tags):
        ntags = dataset.node_tags[node_id]
        if ntags.get("highway") == "crossing" and node_id in dataset.nodes:
            lon, lat = dataset.nodes[node_id]
            if bounds.covers(Point(lon, lat)):
                east, north = frame.xy(lon, lat)
                crossings.append({
                    "id": f"osm:node:{node_id}",
                    "position_m": [round(east, 4), round(north, 4)],
                    "crossing": ntags.get("crossing", "unmarked"),
                    "markings": ntags.get("crossing:markings", ""),
                })
    reference = reference_measurement(config["reference"], dataset, frame, local_layers["roads"])
    source = config["source"]
    scene = {
        "schema_version": 1,
        "id": config["id"],
        "coordinates": {
            "projected_crs": config["projected_crs"],
            "origin_lonlat": config["origin_lonlat"],
            "origin_easting_northing_m": [frame.easting, frame.northing],
            "local_axes": ["east", "north"],
            "unit": "meter",
        },
        "terrain": {"kind": "flat_placeholder", "elevation_m": 0, "boundary": mapping(frame.geometry(bounds))},
        "attribution": source["attribution"],
        "attribution_url": source["attribution_url"],
        "license": source["license"],
        "license_url": source["license_url"],
        "layers": local_layers,
        "crossings": crossings,
    }
    counts = {layer: len(features) for layer, features in layers.items()}
    files = []
    for path, url in sources:
        with path.open("rb") as stream:
            files.append({"name": path.name, "url": url, "sha256": file_digest(stream, "sha256").hexdigest()})
    report = {
        "id": config["id"],
        "source": source,
        "bounds_lonlat": config["bounds_lonlat"],
        "raw_files": files,
        "counts": counts,
        "geometry_issues": issues,
        "reference": reference,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for layer, features in layers.items():
        write_json(output_dir / f"{layer}.geojson", {"type": "FeatureCollection", "features": features})
    write_json(output_dir / "scene.json", scene)
    write_json(output_dir / "import-report.json", report)
    print(f"Features: {counts}. Geometry issues: {len(issues)}.")
    print(
        f"Reference: {reference['projected_m']:.4f} m projected, "
        f"{reference['geodesic_m']:.4f} m geodesic ({reference['relative_error_percent']:.4f}% difference)."
    )
    print(f"Export: {output_dir}")
