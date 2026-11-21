"""Build a directed drivable road graph from clipped OpenStreetMap ways."""

from collections import Counter, defaultdict
from math import dist, isfinite
import re

from shapely.geometry import LineString, Point, shape


DRIVABLE_HIGHWAYS = {
    "primary", "secondary", "tertiary", "residential",
    "living_street", "unclassified", "service",
}
STONE_SURFACES = {"cobblestone", "unhewn_cobblestone", "sett", "paving_stones", "pebblestone"}


def parse_speed_kmh(tags: dict) -> tuple[float, str]:
    raw = str(tags.get("maxspeed", "")).strip()
    if raw:
        lower = raw.lower()
        if lower in {"walk", "living_street"}:
            return 7.0, "osm_maxspeed"
        if lower == "de:urban":
            return 50.0, "osm_maxspeed"
        if lower == "de:rural":
            return 100.0, "osm_maxspeed"
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:km/h|kmh)?", lower)
        if match:
            value = float(match.group(1))
            if isfinite(value) and 0 < value <= 130:
                return value, "osm_maxspeed"
    if tags.get("surface") in STONE_SURFACES:
        return 20.0, "estimated_cobblestone_20kmh"
    return 30.0, "estimated_altstadt_30kmh"


def _coord_key(xy) -> tuple[float, float]:
    return (round(float(xy[0]), 4), round(float(xy[1]), 4))


def _strongly_connected_components(node_ids: list[str], adj: dict[str, list[str]]) -> list[set[str]]:
    """Iterative Tarjan's SCC algorithm for deterministic strongly connected components."""
    index_counter = 0
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    for start in sorted(node_ids):
        if start in indices:
            continue
        call_stack: list[tuple[str, int]] = [(start, 0)]
        indices[start] = lowlink[start] = index_counter
        index_counter += 1
        stack.append(start)
        on_stack.add(start)

        while call_stack:
            v, neighbor_idx = call_stack[-1]
            neighbors = adj.get(v, ())
            if neighbor_idx < len(neighbors):
                call_stack[-1] = (v, neighbor_idx + 1)
                w = neighbors[neighbor_idx]
                if w not in indices:
                    indices[w] = lowlink[w] = index_counter
                    index_counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, 0))
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])
            else:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])
                if lowlink[v] == indices[v]:
                    comp: set[str] = set()
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        comp.add(w)
                        if w == v:
                            break
                    components.append(comp)
    return components


def build_road_graph(
    roads: list[dict],
    width_resolver,
    elevation_m: float,
    crossings: list[dict] | None = None,
) -> dict:
    """Construct a directed road graph from OSM road features in local meters."""
    parts: list[tuple[dict, int, list[tuple[float, float]], list[str | None]]] = []
    coord_uses: Counter[tuple[float, float]] = Counter()
    coord_ways: dict[tuple[float, float], set[str]] = defaultdict(set)
    coord_to_osm_node: dict[tuple[float, float], str] = {}

    for road in roads:
        tags = road["properties"]
        if tags.get("highway") not in DRIVABLE_HIGHWAYS:
            continue
        if tags.get("tunnel", "no") != "no":
            continue
        geom = shape(road["geometry"])
        raw_node_ids = road.get("node_ids")
        if geom.geom_type == "LineString":
            lines = [list(geom.coords)]
            line_nodes = [raw_node_ids if isinstance(raw_node_ids, list) else [None] * len(lines[0])]
        elif geom.geom_type == "MultiLineString":
            lines = [list(line.coords) for line in geom.geoms]
            if isinstance(raw_node_ids, list) and len(raw_node_ids) == len(lines):
                line_nodes = raw_node_ids
            else:
                line_nodes = [[None] * len(line) for line in lines]
        else:
            continue

        for part_index, (coords, nids) in enumerate(zip(lines, line_nodes)):
            if len(coords) < 2:
                continue
            if len(nids) != len(coords):
                nids = [None] * len(coords)
            clean_coords = [(float(p[0]), float(p[1])) for p in coords]
            parts.append((road, part_index, clean_coords, nids))
            for pt, nid in zip(clean_coords, nids):
                key = _coord_key(pt)
                coord_uses[key] += 1
                coord_ways[key].add(road["id"])
                if nid and key not in coord_to_osm_node:
                    coord_to_osm_node[key] = nid

    # Determine split/junction vertices: endpoints of any part or vertices shared by >=2 occurrences
    node_keys: set[tuple[float, float]] = set()
    for _, _, coords, _ in parts:
        node_keys.add(_coord_key(coords[0]))
        node_keys.add(_coord_key(coords[-1]))
        for pt in coords[1:-1]:
            key = _coord_key(pt)
            if coord_uses[key] > 1:
                node_keys.add(key)

    key_to_node_id: dict[tuple[float, float], str] = {}
    nodes_by_id: dict[str, dict] = {}
    for key in sorted(node_keys):
        osm_id = coord_to_osm_node.get(key)
        if osm_id:
            nid = osm_id
        else:
            nid = f"boundary:{int(round(key[0] * 1000))}_{int(round(key[1] * 1000))}"
        key_to_node_id[key] = nid
        nodes_by_id[nid] = {
            "id": nid,
            "osm_node_id": osm_id,
            "position_m": [key[0], key[1], round(float(elevation_m), 4)],
            "way_count": len(coord_ways[key]),
            "is_junction": len(coord_ways[key]) >= 2 or coord_uses[key] >= 3,
        }

    edges: list[dict] = []
    speed_sources: Counter[str] = Counter()
    for road, part_index, coords, _ in parts:
        tags = road["properties"]
        width_m, width_source = width_resolver(tags)
        speed_kmh, speed_source = parse_speed_kmh(tags)
        oneway_tag = str(tags.get("oneway", "no")).strip().lower()
        is_roundabout = tags.get("junction") == "roundabout"
        if oneway_tag in {"yes", "1", "true"} or is_roundabout:
            directions = [("fwd", False)]
            is_oneway = True
        elif oneway_tag == "-1":
            directions = [("rev", True)]
            is_oneway = True
        else:
            directions = [("fwd", False), ("rev", True)]
            is_oneway = False

        split_indices = [0]
        for i in range(1, len(coords) - 1):
            if _coord_key(coords[i]) in node_keys:
                split_indices.append(i)
        split_indices.append(len(coords) - 1)

        for seg_idx, (start_i, end_i) in enumerate(zip(split_indices, split_indices[1:])):
            sub_coords = coords[start_i:end_i + 1]
            length_m = sum(dist(a, b) for a, b in zip(sub_coords, sub_coords[1:]))
            if length_m < 0.05:
                continue
            start_node = key_to_node_id[_coord_key(sub_coords[0])]
            end_node = key_to_node_id[_coord_key(sub_coords[-1])]
            if start_node == end_node and len(sub_coords) < 3:
                continue
            for dir_label, reverse in directions:
                ordered = list(reversed(sub_coords)) if reverse else sub_coords
                u = end_node if reverse else start_node
                v = start_node if reverse else end_node
                edge_id = f"edge:{road['id']}:{part_index}:{seg_idx}:{dir_label}"
                speed_sources[speed_source] += 1
                edges.append({
                    "id": edge_id,
                    "way_id": road["id"],
                    "name": tags.get("name", ""),
                    "highway": tags["highway"],
                    "surface": tags.get("surface", ""),
                    "from_node": u,
                    "to_node": v,
                    "oneway": is_oneway,
                    "width_m": round(float(width_m), 3),
                    "width_source": width_source,
                    "speed_kmh": round(float(speed_kmh), 2),
                    "speed_source": speed_source,
                    "length_m": round(float(length_m), 4),
                    "dead_end": False,
                    "points_m": [
                        [round(p[0], 4), round(p[1], 4), round(float(elevation_m), 4)]
                        for p in ordered
                    ],
                })

    # Compute strongly connected components to identify main connected network vs dead ends
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adj[edge["from_node"]].append(edge["to_node"])
    for nid in adj:
        adj[nid].sort()

    sccs = _strongly_connected_components(list(nodes_by_id.keys()), adj)
    main_scc = max(sccs, key=len) if sccs else set()

    dead_end_count = 0
    for edge in edges:
        if edge["from_node"] not in main_scc or edge["to_node"] not in main_scc:
            edge["dead_end"] = True
            dead_end_count += 1

    # Update node degrees
    in_deg: Counter[str] = Counter(e["to_node"] for e in edges)
    out_deg: Counter[str] = Counter(e["from_node"] for e in edges)
    for nid, node in nodes_by_id.items():
        node["in_degree"] = in_deg[nid]
        node["out_degree"] = out_deg[nid]
        node["in_main_scc"] = nid in main_scc

    nodes_sorted = [nodes_by_id[nid] for nid in sorted(nodes_by_id)]
    edges_sorted = sorted(edges, key=lambda e: e["id"])

    # Attach OSM highway=crossing nodes to drivable road edges.
    crossings_out: list[dict] = []
    for edge in edges_sorted:
        edge["crossings"] = []
    if crossings:
        edge_lines = [
            (edge, LineString([(p[0], p[1]) for p in edge["points_m"]]))
            for edge in edges_sorted
        ]
        for crossing in sorted(crossings, key=lambda c: c["id"]):
            pos = crossing["position_m"]
            pt = Point(float(pos[0]), float(pos[1]))
            matched_edge_ids: list[str] = []
            pos_3d = [round(float(pos[0]), 4), round(float(pos[1]), 4), round(float(elevation_m), 4)]
            for edge, line in edge_lines:
                if line.distance(pt) <= 2.5:
                    along_m = round(float(line.project(pt)), 4)
                    edge["crossings"].append({
                        "id": crossing["id"],
                        "distance_m": along_m,
                        "position_m": pos_3d,
                    })
                    matched_edge_ids.append(edge["id"])
            if matched_edge_ids:
                crossings_out.append({
                    "id": crossing["id"],
                    "position_m": pos_3d,
                    "crossing": crossing.get("crossing", "unmarked"),
                    "markings": crossing.get("markings", ""),
                    "edge_ids": sorted(matched_edge_ids),
                })
        for edge in edges_sorted:
            edge["crossings"].sort(key=lambda c: (c["distance_m"], c["id"]))

    return {
        "schema_version": 1,
        "node_count": len(nodes_sorted),
        "edge_count": len(edges_sorted),
        "main_scc_node_count": len(main_scc),
        "main_scc_edge_count": len(edges_sorted) - dead_end_count,
        "dead_end_edge_count": dead_end_count,
        "crossing_count": len(crossings_out),
        "speed_sources": dict(sorted(speed_sources.items())),
        "nodes": nodes_sorted,
        "edges": edges_sorted,
        "crossings": crossings_out,
    }
