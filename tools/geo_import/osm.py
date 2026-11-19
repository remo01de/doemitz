"""Read a small OpenStreetMap extract and its multipolygon dependencies."""

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from shapely import line_merge
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon


@dataclass
class Dataset:
    nodes: dict[int, tuple[float, float]] = field(default_factory=dict)
    ways: dict[int, ET.Element] = field(default_factory=dict)
    relations: dict[int, ET.Element] = field(default_factory=dict)

    def read(self, path: Path) -> ET.Element:
        root = ET.parse(path).getroot()
        if root.tag != "osm" or root.get("version") != "0.6":
            raise ValueError(f"{path}: expected OSM XML 0.6")
        for node in root.findall("node"):
            self.nodes.setdefault(
                int(node.attrib["id"]),
                (float(node.attrib["lon"]), float(node.attrib["lat"])),
            )
        for element in root.findall("way"):
            self.ways.setdefault(int(element.attrib["id"]), element)
        for element in root.findall("relation"):
            self.relations.setdefault(int(element.attrib["id"]), element)
        return root

    def way_coordinates(self, way: ET.Element) -> list[tuple[float, float]]:
        return [self.nodes[node_id] for node_id in node_ids(way)]


def node_ids(way: ET.Element) -> list[int]:
    return [int(node.attrib["ref"]) for node in way.findall("nd")]


def tags(element: ET.Element) -> dict[str, str]:
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def area_layer(attributes: dict[str, str]) -> str | None:
    if attributes.get("building") not in (None, "no"):
        return "buildings"
    if attributes.get("natural") == "water" or attributes.get("waterway") == "riverbank":
        return "water"
    return None


def area_relations(dataset: Dataset):
    for relation_id, relation in sorted(dataset.relations.items()):
        attributes = tags(relation)
        if attributes.get("type") == "multipolygon" and area_layer(attributes):
            yield relation_id, relation, attributes


def ring_members(relation: ET.Element):
    for member in relation.findall("member"):
        role = member.attrib["role"] or "outer"
        if role not in ("outer", "inner"):
            continue
        if member.attrib["type"] != "way":
            raise ValueError(f"unsupported {role} member type {member.attrib['type']}")
        yield int(member.attrib["ref"]), role


def missing_members(dataset: Dataset, relation: ET.Element) -> list[int]:
    return [
        way_id
        for way_id, _ in ring_members(relation)
        if way_id not in dataset.ways
        or any(node_id not in dataset.nodes for node_id in node_ids(dataset.ways[way_id]))
    ]


def multipolygon(dataset: Dataset, relation: ET.Element):
    lines = {"outer": [], "inner": []}
    for way_id, role in ring_members(relation):
        lines[role].append(LineString(dataset.way_coordinates(dataset.ways[way_id])))

    rings = {}
    for role, parts in lines.items():
        merged = line_merge(MultiLineString(parts))
        rings[role] = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        if not all(ring.is_closed and len(ring.coords) >= 4 for ring in rings[role]):
            raise ValueError(f"one or more {role} rings could not be closed")
    if not rings["outer"]:
        raise ValueError("no outer ring")

    shells = [Polygon(ring) for ring in rings["outer"]]
    holes = [[] for _ in shells]
    for ring in rings["inner"]:
        candidates = [index for index, shell in enumerate(shells) if shell.covers(Polygon(ring))]
        if not candidates:
            raise ValueError("inner ring lies outside all outer rings")
        index = min(candidates, key=lambda candidate: shells[candidate].area)
        holes[index].append(ring.coords)
    return MultiPolygon(
        [Polygon(shell.exterior.coords, holes[index]) for index, shell in enumerate(shells)]
    )


def map_url(config: dict) -> str:
    bbox = ",".join(str(bound) for bound in config["bounds_lonlat"])
    return f"{config['source']['api_base']}/map?bbox={bbox}"


def relation_url(config: dict, relation_id: int) -> str:
    return f"{config['source']['api_base']}/relation/{relation_id}/full"


def download(url: str, path: Path) -> None:
    print(f"OSM: {url}")
    request = Request(url, headers={"User-Agent": "Doemitz-Living-City/0.1 (local geodata import)"})
    with urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())


def fetch_snapshot(config: dict, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"snapshot already exists: {destination}; use a new --raw-dir")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as scratch:
        stage = Path(scratch) / "snapshot"
        stage.mkdir()
        base = stage / "map.osm"
        download(map_url(config), base)
        dataset = Dataset()
        dataset.read(base)
        for relation_id, relation, _ in list(area_relations(dataset)):
            try:
                missing = missing_members(dataset, relation)
            except ValueError:
                # The build records unsupported relation structures with their source IDs.
                continue
            if missing:
                supplement = stage / f"relation-{relation_id}.osm"
                download(relation_url(config, relation_id), supplement)
                dataset.read(supplement)
                if missing_members(dataset, relation):
                    raise ValueError(f"relation {relation_id} is still incomplete after download")
        stage.rename(destination)
