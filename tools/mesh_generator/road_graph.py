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


def _eval_z(elevation_or_fn, east_m: float, north_m: float) -> float:
    return round(float(elevation_or_fn(east_m, north_m)), 4) if callable(elevation_or_fn) else round(float(elevation_or_fn), 4)


def _densify_edge_coords(coords: list[tuple[float, float]], max_step_m: float = 4.0) -> list[tuple[float, float]]:
    if len(coords) < 2:
        return coords
    out = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        seg = dist(a, b)
        if seg > max_step_m:
            steps = int(seg // max_step_m) + 1
            for i in range(1, steps):
                t = i / steps
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out


def _generate_parking_slots(geom, center: Point, capacity: int, elevation_m, max_slots: int = 12) -> list[list[float]]:
    """Generate deterministic, non-overlapping parking slot positions inside a polygon or around a point."""
    slot_count = max(1, min(capacity, max_slots))
    slots: list[list[float]] = []

    if geom.geom_type in {"Polygon", "MultiPolygon"} and geom.area >= 12.5:
        minx, miny, maxx, maxy = geom.bounds
        step = 4.2
        y = miny + 2.0
        while y <= maxy - 1.5 and len(slots) < slot_count:
            x = minx + 2.0
            while x <= maxx - 1.5 and len(slots) < slot_count:
                pt = Point(x, y)
                if geom.contains(pt):
                    slots.append([round(x, 4), round(y, 4), _eval_z(elevation_m, x, y)])
                x += step
            y += step
        if not slots:
            rp = geom.representative_point()
            slots.append([round(rp.x, 4), round(rp.y, 4), _eval_z(elevation_m, rp.x, rp.y)])
        return slots

    # Point parking fallback: compact deterministic 2x2 grid around the OSM point
    offsets = [(0.0, 0.0), (3.5, 0.0), (0.0, 3.5), (3.5, 3.5)]
    for idx in range(min(slot_count, len(offsets))):
        ox, oy = offsets[idx]
        sx, sy = center.x + ox, center.y + oy
        slots.append([round(sx, 4), round(sy, 4), _eval_z(elevation_m, sx, sy)])
    return slots


def build_road_graph(
    roads: list[dict],
    width_resolver,
    elevation_m,
    crossings: list[dict] | None = None,
    priority_signs: list[dict] | None = None,
    pois: list[dict] | None = None,
    parking_elevation_fn=None,
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
            "position_m": [key[0], key[1], _eval_z(elevation_m, key[0], key[1])],
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
                if callable(elevation_m):
                    ordered = _densify_edge_coords(ordered, max_step_m=4.0)
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
                    "is_bridge": str(tags.get("bridge", "no")).strip().lower() not in ("", "no", "false", "0"),
                    "width_m": round(float(width_m), 3),
                    "width_source": width_source,
                    "speed_kmh": round(float(speed_kmh), 2),
                    "speed_source": speed_source,
                    "length_m": round(float(length_m), 4),
                    "dead_end": False,
                    "points_m": [
                        [round(p[0], 4), round(p[1], 4), _eval_z(elevation_m, p[0], p[1])]
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
        edge["yield_rule"] = "none"
        edge["yield_sign_id"] = ""
        edge["yield_source"] = "assumed_right_before_left"

    edge_lines = [
        (edge, LineString([(p[0], p[1]) for p in edge["points_m"]]))
        for edge in edges_sorted
    ]
    if crossings:
        for crossing in sorted(crossings, key=lambda c: c["id"]):
            pos = crossing["position_m"]
            pt = Point(float(pos[0]), float(pos[1]))
            matched_edge_ids: list[str] = []
            pos_3d = [round(float(pos[0]), 4), round(float(pos[1]), 4), _eval_z(elevation_m, float(pos[0]), float(pos[1]))]
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

    # Attach OSM highway=give_way and highway=stop priority signs to directed road edges.
    priority_signs_out: list[dict] = []
    sign_priority_rank = {"stop": 2, "give_way": 1, "none": 0}
    if priority_signs:
        for sign in sorted(priority_signs, key=lambda s: s["id"]):
            sign_type = str(sign.get("sign", "")).strip().lower()
            if sign_type not in {"give_way", "stop"}:
                continue
            pos = sign["position_m"]
            pt = Point(float(pos[0]), float(pos[1]))
            direction = str(sign.get("direction", "")).strip().lower()

            candidates = []
            for edge, line in edge_lines:
                d = line.distance(pt)
                if d > 1.5:
                    continue
                is_fwd = edge["id"].endswith(":fwd")
                is_rev = edge["id"].endswith(":rev")
                if direction == "forward" and not is_fwd:
                    continue
                if direction == "backward" and not is_rev:
                    continue
                along_m = float(line.project(pt))
                dist_to_end = max(0.0, edge["length_m"] - along_m)
                candidates.append((d, dist_to_end, edge))

            matched_edge = None
            if candidates:
                # Prefer exact/closest match; if undirected on a two-way road, choose direction approaching its nearer junction
                candidates.sort(key=lambda item: (round(item[0], 3), item[1], item[2]["id"]))
                matched_edge = candidates[0][2]
                if sign_priority_rank[sign_type] > sign_priority_rank[matched_edge["yield_rule"]]:
                    matched_edge["yield_rule"] = sign_type
                    matched_edge["yield_sign_id"] = sign["id"]
                    matched_edge["yield_source"] = f"osm_{sign_type}"

            priority_signs_out.append({
                "id": sign["id"],
                "sign": sign_type,
                "direction": direction,
                "position_m": [round(float(pos[0]), 4), round(float(pos[1]), 4), _eval_z(elevation_m, float(pos[0]), float(pos[1]))],
                "edge_id": matched_edge["id"] if matched_edge else "",
                "to_node": matched_edge["to_node"] if matched_edge else "",
            })

    # Build junction report listing every junction with its rule and source.
    incoming_by_node: dict[str, list[dict]] = defaultdict(list)
    for edge in edges_sorted:
        incoming_by_node[edge["to_node"]].append(edge)

    junctions_report: list[dict] = []
    for node in nodes_sorted:
        nid = node["id"]
        inc = incoming_by_node.get(nid, [])
        if not node["is_junction"] and len(inc) < 2:
            continue
        sign_edges = [e for e in inc if e["yield_rule"] != "none"]
        if sign_edges:
            rule = "priority_sign"
            sources = sorted({e["yield_source"] for e in sign_edges})
            source = ",".join(sources)
        else:
            rule = "right_before_left"
            source = "assumed_right_before_left"
        junctions_report.append({
            "node_id": nid,
            "position_m": node["position_m"],
            "in_main_scc": node["in_main_scc"],
            "rule": rule,
            "source": source,
            "incoming_edges": [
                {
                    "edge_id": e["id"],
                    "name": e["name"],
                    "yield_rule": e["yield_rule"],
                    "yield_sign_id": e["yield_sign_id"],
                    "yield_source": e["yield_source"],
                }
                for e in inc
            ],
        })

    # Compile amenity=parking POIs with estimated capacity (area / 12.5 m²) and nearest main-SCC access edge.
    main_edge_lines = [(e, line) for e, line in edge_lines if not e["dead_end"]]
    parking_lots_out: list[dict] = []
    if pois and main_edge_lines:
        for poi in sorted(pois, key=lambda p: p["id"]):
            props = poi.get("properties") or {}
            if props.get("amenity") != "parking":
                continue
            geom = shape(poi["geometry"])
            center = geom.representative_point() if geom.geom_type != "Point" else geom
            area_m2 = round(float(geom.area), 2) if geom.geom_type in {"Polygon", "MultiPolygon"} else 0.0

            osm_cap = None
            raw_cap = str(props.get("capacity", "")).strip()
            if raw_cap.isdigit() and int(raw_cap) > 0:
                osm_cap = int(raw_cap)

            if osm_cap is not None:
                capacity = osm_cap
                capacity_source = "osm_capacity"
            elif area_m2 > 0.0:
                capacity = max(1, int(area_m2 // 12.5))
                capacity_source = "estimated_area_div_12_5_m2"
            else:
                capacity = 4
                capacity_source = "assumed_point_parking_4"

            best_edge, best_line = min(
                main_edge_lines,
                key=lambda item: (item[1].distance(center), item[0]["id"]),
            )
            access_along_m = round(float(best_line.project(center)), 4)
            access_along_m = max(1.0, min(best_edge["length_m"] - 1.0, access_along_m))
            osm_ref = props.get("osm_id") or poi["id"].removeprefix("poi:")
            lot_id = f"parking:{osm_ref}"
            name = str(props.get("name", "")).strip()
            if not name:
                street_hint = best_edge["name"] or osm_ref.rsplit(":", 1)[-1]
                name = f"Parkplatz {street_hint}"
            park_elev = parking_elevation_fn if parking_elevation_fn is not None else elevation_m
            slots_m = _generate_parking_slots(geom, center, capacity, park_elev)
            parking_lots_out.append({
                "id": lot_id,
                "osm_id": osm_ref,
                "name": name,
                "position_m": [round(center.x, 4), round(center.y, 4), _eval_z(park_elev, center.x, center.y)],
                "area_m2": area_m2,
                "capacity": capacity,
                "capacity_source": capacity_source,
                "access_edge_id": best_edge["id"],
                "access_distance_m": round(access_along_m, 4),
                "slots_m": slots_m,
            })

    return {
        "schema_version": 1,
        "node_count": len(nodes_sorted),
        "edge_count": len(edges_sorted),
        "main_scc_node_count": len(main_scc),
        "main_scc_edge_count": len(edges_sorted) - dead_end_count,
        "dead_end_edge_count": dead_end_count,
        "crossing_count": len(crossings_out),
        "priority_sign_count": len(priority_signs_out),
        "junction_count": len(junctions_report),
        "parking_lot_count": len(parking_lots_out),
        "speed_sources": dict(sorted(speed_sources.items())),
        "nodes": nodes_sorted,
        "edges": edges_sorted,
        "crossings": crossings_out,
        "priority_signs": priority_signs_out,
        "junctions": junctions_report,
        "parking_lots": parking_lots_out,
    }
