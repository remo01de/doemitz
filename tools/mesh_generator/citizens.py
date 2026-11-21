"""Compile deterministic citizen places, opening hours, weekly schedules, and pedestrian routes from OSM data."""

from collections import Counter, defaultdict
from hashlib import sha256
import heapq
from math import ceil, hypot

from shapely import union_all
from shapely.geometry import LineString, Point, shape
from shapely.ops import nearest_points

from tools.mesh_generator.opening_hours import resolve_opening_hours


VALID_ACTIVITIES = {"Home", "Working", "Shopping", "Strolling"}
ROUTE_STEP_M = 4.5
CROSSING_DETOUR_MAX_M = 45.0

RESIDENTIAL_BUILDING_TYPES = {"residential", "apartments", "house", "detached", "terrace", "villa"}
NON_RESIDENTIAL_BUILDING_TYPES = {
    "garage", "garages", "shed", "roof", "hut", "church", "industrial",
    "commercial", "retail", "public", "civic", "construction", "grandstand",
}

GASTRONOMY_AMENITIES = {"cafe", "restaurant", "fast_food", "biergarten", "pub", "bar", "ice_cream"}
SHOP_AMENITIES = {"pharmacy", "marketplace"}
WORK_AMENITIES = {
    "bank", "doctors", "dentist", "clinic", "townhall", "post_office",
    "library", "school", "kindergarten", "community_centre", "social_facility",
    "police", "fire_station", "veterinary",
}
TOURISM_DESTINATIONS = {"hotel", "guest_house", "museum", "gallery", "attraction", "hostel"}

COAT_PALETTE = [
    [0.68, 0.22, 0.18],
    [0.16, 0.34, 0.56],
    [0.76, 0.55, 0.16],
    [0.22, 0.48, 0.30],
    [0.48, 0.24, 0.52],
    [0.24, 0.46, 0.50],
]

GERMAN_NAMES = [
    "Elena", "Frank", "Greta", "Hans", "Ines", "Jan", "Karin", "Lukas",
    "Marie", "Nils", "Olga", "Paul", "Petra", "Ralf", "Sabine", "Stefan",
    "Tanja", "Uwe", "Vera", "Walter", "Anja", "Bastian", "Claudia", "Dirk",
    "Eva", "Florian", "Gabi", "Heiko", "Iris", "Jonas",
]


def _det_int(seed: int, key: str, salt: str) -> int:
    digest = sha256(f"{seed}:{key}:{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _side_sign(line, point):
    along = line.project(point)
    before = line.interpolate(max(0.0, along - 0.5))
    after = line.interpolate(min(line.length, along + 0.5))
    cross = (after.x - before.x) * (point.y - before.y) - (after.y - before.y) * (point.x - before.x)
    return 1.0 if cross >= 0.0 else -1.0


def _offset_point(line, distance_m, lateral_m):
    clamped = max(0.0, min(line.length, distance_m))
    center = line.interpolate(clamped)
    before = line.interpolate(max(0.0, clamped - 0.5))
    after = line.interpolate(min(line.length, clamped + 0.5))
    dx = after.x - before.x
    dy = after.y - before.y
    norm = hypot(dx, dy)
    if norm <= 1e-9:
        return center
    return Point(center.x - (dy / norm) * lateral_m, center.y + (dx / norm) * lateral_m)


def _classify_poi(props: dict) -> str | None:
    if props.get("shop") not in (None, "", "no"):
        return "shop"
    if props.get("office") not in (None, "", "no"):
        return "work"
    amenity = props.get("amenity", "")
    if amenity in GASTRONOMY_AMENITIES:
        return "gastronomy"
    if amenity in SHOP_AMENITIES:
        return "shop"
    if amenity in WORK_AMENITIES:
        return "work"
    tourism = props.get("tourism", "")
    if tourism in TOURISM_DESTINATIONS:
        return "tourism"
    if tourism == "information" and props.get("opening_hours"):
        return "tourism"
    return None


def _poi_display_name(props: dict, kind: str, fallback_id: str) -> str:
    if props.get("name"):
        return str(props["name"])
    for tag_key in ("shop", "amenity", "office", "tourism"):
        if props.get(tag_key):
            return f"{str(props[tag_key]).replace('_', ' ').title()} ({fallback_id.rsplit(':', 1)[-1]})"
    return f"{kind.title()} ({fallback_id.rsplit(':', 1)[-1]})"


def _build_pedestrian_graph(roads_by_id: dict, crossings: list[dict] | None):
    """Build an undirected walkable road graph (nodes, adjacency) for multi-street Altstadt routing."""
    nodes: dict[tuple[float, float], int] = {}
    coords_by_idx: list[tuple[float, float]] = []
    adj: dict[int, list[tuple[int, float]]] = defaultdict(list)

    def get_node(x: float, y: float) -> int:
        key = (round(float(x), 3), round(float(y), 3))
        idx = nodes.get(key)
        if idx is None:
            idx = len(coords_by_idx)
            nodes[key] = idx
            coords_by_idx.append(key)
        return idx

    road_lines: list[tuple[str, LineString, float]] = []
    for road_id in sorted(roads_by_id):
        road, width_m = roads_by_id[road_id]
        if road["properties"].get("tunnel", "no") != "no":
            continue
        geom = shape(road["geometry"])
        lines = [geom] if geom.geom_type == "LineString" else list(geom.geoms) if geom.geom_type == "MultiLineString" else []
        for line in lines:
            pts = list(line.coords)
            if len(pts) < 2:
                continue
            road_lines.append((road_id, line, width_m))
            for a, b in zip(pts, pts[1:]):
                u = get_node(a[0], a[1])
                v = get_node(b[0], b[1])
                if u == v:
                    continue
                d = hypot(b[0] - a[0], b[1] - a[1])
                if d > 1e-4:
                    adj[u].append((v, d))
                    adj[v].append((u, d))

    # Connect nearby crossing nodes into the pedestrian graph so routes can snap through them cleanly.
    crossing_nodes: list[tuple[str, int, tuple[float, float]]] = []
    for crossing in sorted(crossings or [], key=lambda c: c["id"]):
        cx, cy = float(crossing["position_m"][0]), float(crossing["position_m"][1])
        c_idx = get_node(cx, cy)
        crossing_nodes.append((crossing["id"], c_idx, (cx, cy)))
        # Link to the 2 closest existing road graph nodes within 25 m
        nearest = sorted(
            (
                (hypot(nx - cx, ny - cy), n_idx)
                for n_idx, (nx, ny) in enumerate(coords_by_idx)
                if n_idx != c_idx
            ),
            key=lambda item: (item[0], item[1]),
        )[:2]
        for dist_m, n_idx in nearest:
            if dist_m <= 25.0:
                adj[c_idx].append((n_idx, dist_m))
                adj[n_idx].append((c_idx, dist_m))

    return coords_by_idx, adj, road_lines, crossing_nodes


def _nearest_graph_node(pt: Point, coords_by_idx: list[tuple[float, float]]) -> int:
    best_idx = 0
    best_d = float("inf")
    px, py = pt.x, pt.y
    for idx, (nx, ny) in enumerate(coords_by_idx):
        d = hypot(nx - px, ny - py)
        if d < best_d:
            best_d = d
            best_idx = idx
    return best_idx


def _dijkstra_path(start_idx: int, end_idx: int, adj: dict[int, list[tuple[int, float]]]) -> list[int]:
    if start_idx == end_idx:
        return [start_idx]
    dist_map: dict[int, float] = {start_idx: 0.0}
    prev: dict[int, int] = {}
    heap: list[tuple[float, int]] = [(0.0, start_idx)]
    while heap:
        cur_d, u = heapq.heappop(heap)
        if cur_d > dist_map.get(u, float("inf")):
            continue
        if u == end_idx:
            break
        for v, w in adj.get(u, ()):
            nd = cur_d + w
            if nd < dist_map.get(v, float("inf")):
                dist_map[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if end_idx not in prev:
        return [start_idx, end_idx]
    path = [end_idx]
    cur = end_idx
    while cur != start_idx:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path


def _nearest_crossing(pt: Point, crossing_pts: list[tuple[str, Point]], max_dist_m: float) -> tuple[str, Point] | None:
    best = None
    best_d = max_dist_m
    for cid, cpt in crossing_pts:
        d = pt.distance(cpt)
        if d <= best_d:
            best_d = d
            best = (cid, cpt)
    return best


def _pilot_route_points(
    start_place, end_place, road_line, lateral_offset_m, sidewalk_area,
    road_elevation_m, sidewalk_elevation_m, obstacles, crossing_pts,
):
    start_along = start_place["along_m"]
    end_along = end_place["along_m"]
    start_side = start_place["side"]
    end_side = end_place["side"]

    points = [start_place["access_m"]]
    uses_crossing = False
    span = abs(end_along - start_along)
    steps = max(2, ceil(span / ROUTE_STEP_M))

    def append_point(pt, prefer_sidewalk=True):
        if prefer_sidewalk and not sidewalk_area.is_empty and sidewalk_area.contains(pt):
            z = sidewalk_elevation_m
        elif not obstacles.is_empty and obstacles.contains(pt):
            _, safe = nearest_points(pt, sidewalk_area if not sidewalk_area.is_empty else road_line)
            pt = safe
            z = sidewalk_elevation_m if not sidewalk_area.is_empty and sidewalk_area.covers(pt) else road_elevation_m
        else:
            z = road_elevation_m
        coord = [round(pt.x, 4), round(pt.y, 4), round(z, 4)]
        if coord != points[-1]:
            points.append(coord)

    crossing_target = None
    if start_side != end_side and crossing_pts:
        mid_nominal = road_line.interpolate(end_along)
        crossing_target = _nearest_crossing(mid_nominal, crossing_pts, CROSSING_DETOUR_MAX_M)

    for step in range(1, steps):
        fraction = step / steps
        along = start_along + (end_along - start_along) * fraction
        candidate = _offset_point(road_line, along, start_side * lateral_offset_m)
        if not sidewalk_area.is_empty and not sidewalk_area.contains(candidate):
            _, nearest_sw = nearest_points(candidate, sidewalk_area)
            if candidate.distance(nearest_sw) <= 1.2:
                candidate = nearest_sw
        append_point(candidate, prefer_sidewalk=True)

    if start_side != end_side:
        if crossing_target is not None:
            _, cpt = crossing_target
            append_point(cpt, prefer_sidewalk=False)
            uses_crossing = True
        else:
            mid = road_line.interpolate(end_along)
            append_point(mid, prefer_sidewalk=False)

    if end_place["access_m"] != points[-1]:
        points.append(end_place["access_m"])

    return points, uses_crossing


def _graph_route_points(
    start_place, end_place, coords_by_idx, adj, sidewalk_area,
    road_elevation_m, sidewalk_elevation_m, obstacles, crossing_pts,
):
    start_pt = Point(start_place["access_m"][0], start_place["access_m"][1])
    end_pt = Point(end_place["access_m"][0], end_place["access_m"][1])
    start_node = _nearest_graph_node(start_pt, coords_by_idx)
    end_node = _nearest_graph_node(end_pt, coords_by_idx)
    node_path = _dijkstra_path(start_node, end_node, adj)

    raw_pts = [start_pt] + [Point(coords_by_idx[idx]) for idx in node_path] + [end_pt]
    # Check if any crossing lies near the middle of the path (or near start/end road transitions)
    uses_crossing = False
    if crossing_pts and len(raw_pts) >= 3:
        crossing_ids_seen = set()
        enhanced: list[tuple[Point, bool]] = [(raw_pts[0], True)]
        for pt in raw_pts[1:-1]:
            near = _nearest_crossing(pt, crossing_pts, 18.0)
            if near is not None and near[0] not in crossing_ids_seen:
                crossing_ids_seen.add(near[0])
                enhanced.append((near[1], False))
                uses_crossing = True
            else:
                enhanced.append((pt, True))
        enhanced.append((raw_pts[-1], True))
    else:
        enhanced = [(pt, True) for pt in raw_pts]

    points = [start_place["access_m"]]
    for (p0, pref0), (p1, pref1) in zip(enhanced, enhanced[1:]):
        seg_len = p0.distance(p1)
        if seg_len <= 0.1:
            continue
        sub_steps = max(1, ceil(seg_len / ROUTE_STEP_M))
        for step in range(1, sub_steps + 1):
            frac = step / sub_steps
            pt = Point(p0.x + (p1.x - p0.x) * frac, p0.y + (p1.y - p0.y) * frac)
            prefer_sw = pref1 if step == sub_steps else (pref0 and pref1)
            if prefer_sw and not sidewalk_area.is_empty:
                if not sidewalk_area.contains(pt):
                    _, sw_pt = nearest_points(pt, sidewalk_area)
                    if pt.distance(sw_pt) <= 2.2:
                        pt = sw_pt
            if not obstacles.is_empty and obstacles.contains(pt):
                _, safe = nearest_points(pt, sidewalk_area if not sidewalk_area.is_empty else LineString([p0, p1]))
                if not obstacles.contains(safe):
                    pt = safe
            z = sidewalk_elevation_m if (prefer_sw and not sidewalk_area.is_empty and sidewalk_area.covers(pt)) else road_elevation_m
            coord = [round(pt.x, 4), round(pt.y, 4), round(z, 4)]
            if coord != points[-1]:
                points.append(coord)

    if end_place["access_m"] != points[-1]:
        points.append(end_place["access_m"])
    return points, uses_crossing


def _validate_schedule(citizen_id: str, schedule: list[dict], places_by_id: dict) -> list[dict]:
    if not schedule or schedule[0]["start_minute"] != 0:
        raise ValueError(f"citizen {citizen_id} schedule must start at minute 0")
    last_minute = -1
    schedule_out = []
    for step in schedule:
        minute = int(step["start_minute"])
        activity = step["activity"]
        place_id = step["place_id"]
        if not (0 <= minute < 1440) or minute <= last_minute:
            raise ValueError(f"citizen {citizen_id} schedule minutes must strictly increase in [0, 1440)")
        if activity not in VALID_ACTIVITIES:
            raise ValueError(f"citizen {citizen_id} has unsupported activity {activity!r}")
        if place_id not in places_by_id:
            raise ValueError(f"citizen {citizen_id} schedule references unknown place {place_id}")
        last_minute = minute
        schedule_out.append({
            "start_minute": minute,
            "activity": activity,
            "place_id": place_id,
        })
    return schedule_out


def build_citizens(
    config, roads, buildings, sidewalks, obstacles, road_elevation_m, sidewalk_elevation_m,
    pois=None, crossings=None, entrances=None,
):
    """Validate citizen manifest, expand population from OSM POIs/buildings, and compile routes."""
    clock = config.get("clock", {})
    start_minute = float(clock.get("start_minute", 470))
    time_scale = float(clock.get("time_scale", 60.0))
    if not 0.0 <= start_minute < 1440.0 or not 0.0 < time_scale <= 3600.0:
        raise ValueError("invalid citizen simulation clock configuration")

    pilot_road_id = config["pilot_road_id"]
    if pilot_road_id not in roads:
        raise ValueError(f"pilot road {pilot_road_id} not found in scene")
    pilot_road, pilot_width_m = roads[pilot_road_id]
    road_line = shape(pilot_road["geometry"])

    sidewalk_union = union_all(sidewalks) if sidewalks else union_all([])
    sidewalk_interior = union_all([polygon.buffer(-0.35) for polygon in sidewalks]) if sidewalks else union_all([])
    walkable_access = sidewalk_interior if not sidewalk_interior.is_empty else sidewalk_union

    all_road_union = union_all([
        shape(road["geometry"])
        for road, _ in roads.values()
        if road["properties"].get("tunnel", "no") == "no"
    ])

    buildings_by_id = {feature["id"]: shape(feature["geometry"]) for feature in buildings}
    building_features_by_id = {feature["id"]: feature for feature in buildings}
    pois_list = list(pois or [])
    poi_by_osm_id = {
        p["properties"].get("osm_id"): p
        for p in pois_list
        if p["properties"].get("osm_id")
    }

    def compute_access(geom):
        if not walkable_access.is_empty:
            _, sw_pt = nearest_points(geom, walkable_access)
            if geom.distance(sw_pt) <= 18.0:
                return sw_pt, sidewalk_elevation_m
        _, rd_pt = nearest_points(geom, all_road_union if not all_road_union.is_empty else road_line)
        return rd_pt, road_elevation_m

    places_out = []
    places_by_id = {}
    opening_hours_sources = Counter()
    osm_opening_hours_places = []
    entrance_sources = Counter()

    entrance_priority = {"main": 0, "yes": 1, "home": 1, "shop": 1, "staircase": 2, "service": 3}
    osm_entrances = [
        (
            e["id"],
            Point(float(e["position_m"][0]), float(e["position_m"][1])),
            str(e.get("entrance", "yes")),
            entrance_priority.get(str(e.get("entrance", "yes")).lower(), 2),
        )
        for e in sorted(entrances or [], key=lambda item: item["id"])
    ]

    def resolve_entrance(place_id, building_id, geom, access_pt, access_elevation):
        ref_geom = buildings_by_id.get(building_id, geom)
        candidates = []
        for eid, ept, etype, prio in osm_entrances:
            d = ref_geom.distance(ept)
            if d <= 3.0:
                candidates.append((prio, d, eid, ept, etype))
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1], item[2]))
            _, _, eid, ept, etype = candidates[0]
            z = sidewalk_elevation_m if (not walkable_access.is_empty and walkable_access.distance(ept) <= 3.0) else road_elevation_m
            entrance_sources["osm"] += 1
            return {
                "id": f"entrance:{place_id}",
                "position_m": [round(ept.x, 4), round(ept.y, 4), round(z, 4)],
                "source": "osm",
                "osm_node_id": eid,
                "entrance_type": etype,
            }
        entrance_sources["assumed_sidewalk_access"] += 1
        return {
            "id": f"entrance:{place_id}",
            "position_m": [round(access_pt.x, 4), round(access_pt.y, 4), round(access_elevation, 4)],
            "source": "assumed_sidewalk_access",
            "osm_node_id": "",
            "entrance_type": "assumed",
        }

    def register_place(place_id, name, building_id, kind, geom, osm_oh=None, on_pilot=False, economy_category=None):
        if place_id in places_by_id:
            return places_by_id[place_id]
        if on_pilot:
            if walkable_access.is_empty:
                _, access_pt = nearest_points(geom, road_line)
                elevation = road_elevation_m
            else:
                _, access_pt = nearest_points(geom, walkable_access)
                elevation = sidewalk_elevation_m
            along_m = road_line.project(access_pt)
            side = _side_sign(road_line, access_pt)
        else:
            access_pt, elevation = compute_access(geom)
            along_m = None
            side = None

        oh = resolve_opening_hours(kind, osm_oh)
        opening_hours_sources[oh["source"]] += 1
        if oh["source"] == "osm":
            osm_opening_hours_places.append({"id": place_id, "name": name, "raw": oh["raw"]})

        entrance = resolve_entrance(place_id, building_id, geom, access_pt, elevation)
        compiled = {
            "id": place_id,
            "name": name,
            "building_id": building_id,
            "kind": kind,
            "economy_category": economy_category or kind,
            "along_m": round(along_m, 4) if along_m is not None else None,
            "side": side,
            "on_pilot": on_pilot,
            "access_m": [round(access_pt.x, 4), round(access_pt.y, 4), round(elevation, 4)],
            "entrance": entrance,
            "opening_hours": oh,
        }
        places_out.append(compiled)
        places_by_id[place_id] = compiled
        return compiled

    # 1. Register manifest places first (preserve exact Sprint 3-7 IDs).
    manifest_building_ids = set()
    for entry in config["places"]:
        place_id = entry["id"]
        building_id = entry["building_id"]
        if not place_id or place_id in places_by_id:
            raise ValueError(f"duplicate or empty place id: {place_id!r}")
        if building_id not in buildings_by_id:
            raise ValueError(f"place {place_id} references unknown building {building_id}")
        manifest_building_ids.add(building_id)
        matching_poi = poi_by_osm_id.get(building_id)
        osm_oh = entry.get("opening_hours") or (matching_poi["properties"].get("opening_hours") if matching_poi else None)
        register_place(
            place_id, entry["name"], building_id, entry["kind"],
            buildings_by_id[building_id], osm_oh=osm_oh, on_pilot=True,
        )

    # 2. Register usable OSM POIs as work / shop / gastronomy / tourism places.
    work_poi_ids = []
    shop_poi_ids = []
    stroll_poi_ids = []
    poi_building_ids = set(manifest_building_ids)

    for poi in sorted(pois_list, key=lambda item: item["id"]):
        props = poi["properties"]
        kind = _classify_poi(props)
        if kind is None:
            continue
        poi_geom = shape(poi["geometry"])
        osm_id = props.get("osm_id", "")
        building_id = osm_id if osm_id in buildings_by_id else ""
        if building_id in manifest_building_ids:
            continue
        if not building_id:
            # Find containing or nearest building within 12 m for reference
            nearest_b_id = ""
            nearest_b_d = 12.0
            for bid, bgeom in buildings_by_id.items():
                d = bgeom.distance(poi_geom)
                if d < nearest_b_d:
                    nearest_b_d = d
                    nearest_b_id = bid
                    if d == 0.0:
                        break
            building_id = nearest_b_id
        if building_id:
            poi_building_ids.add(building_id)

        place_id = poi["id"]
        display_name = _poi_display_name(props, kind, place_id)
        econ_cat = "pharmacy" if props.get("amenity") == "pharmacy" else kind
        compiled = register_place(
            place_id, display_name, building_id, kind,
            poi_geom, osm_oh=props.get("opening_hours"), on_pilot=False, economy_category=econ_cat,
        )
        if kind in {"work", "shop", "gastronomy", "tourism"}:
            work_poi_ids.append(compiled["id"])
        if kind in {"shop", "gastronomy"}:
            shop_poi_ids.append(compiled["id"])
        if kind in {"tourism", "gastronomy", "shop"}:
            stroll_poi_ids.append(compiled["id"])

    # Include manifest work/shop places in the pools too
    if "place_amtsverwaltung" in places_by_id:
        work_poi_ids.append("place_amtsverwaltung")
    if "place_kaufhaus" in places_by_id:
        work_poi_ids.append("place_kaufhaus")
        shop_poi_ids.append("place_kaufhaus")
        stroll_poi_ids.append("place_kaufhaus")
    work_poi_ids = sorted(set(work_poi_ids))
    shop_poi_ids = sorted(set(shop_poi_ids)) or work_poi_ids
    stroll_poi_ids = sorted(set(stroll_poi_ids)) or work_poi_ids

    # 3. Compile manifest citizens (preserving their exact IDs) + optional weekend schedules.
    citizens_out = []
    seen_citizens = set()
    needed_pairs = set()

    def register_citizen(entry):
        citizen_id = entry["id"]
        if not citizen_id or citizen_id in seen_citizens:
            raise ValueError(f"duplicate or empty citizen id: {citizen_id!r}")
        seen_citizens.add(citizen_id)
        home_id = entry["home_place_id"]
        work_id = entry["work_place_id"]
        if home_id not in places_by_id or work_id not in places_by_id:
            raise ValueError(f"citizen {citizen_id} references unknown home or work place")
        speed_mps = float(entry["walk_speed_mps"])
        if not 0.5 <= speed_mps <= 3.0:
            raise ValueError(f"citizen {citizen_id} has invalid walk_speed_mps: {speed_mps}")
        coat = entry["coat_color"]
        if len(coat) != 3 or not all(0.0 <= float(c) <= 1.0 for c in coat):
            raise ValueError(f"citizen {citizen_id} has invalid coat_color")

        weekday_sched = _validate_schedule(citizen_id, entry["schedule"], places_by_id)
        sat_sched = _validate_schedule(citizen_id, entry.get("saturday_schedule") or entry["schedule"], places_by_id)
        sun_sched = _validate_schedule(citizen_id, entry.get("sunday_schedule") or entry["schedule"], places_by_id)

        # Collect all route pairs needed across weekday, Saturday, Sunday (plus skip-shopping pairs)
        for sched in (weekday_sched, sat_sched, sun_sched):
            for index, current in enumerate(sched):
                nxt = sched[(index + 1) % len(sched)]
                if current["place_id"] != nxt["place_id"]:
                    needed_pairs.add((current["place_id"], nxt["place_id"]))
                # If next is Shopping and might be closed, citizen skips to index + 2
                if nxt["activity"] == "Shopping" and len(sched) >= 3:
                    after_shop = sched[(index + 2) % len(sched)]
                    if current["place_id"] != after_shop["place_id"]:
                        needed_pairs.add((current["place_id"], after_shop["place_id"]))
                if current["place_id"] != home_id:
                    needed_pairs.add((current["place_id"], home_id))

        citizens_out.append({
            "id": citizen_id,
            "name": entry["name"],
            "home_place_id": home_id,
            "work_place_id": work_id,
            "walk_speed_mps": round(speed_mps, 3),
            "coat_color": [float(c) for c in coat],
            "schedule": weekday_sched,
            "saturday_schedule": sat_sched,
            "sunday_schedule": sun_sched,
        })

    for entry in config["citizens"]:
        register_citizen(entry)

    # 4. Deterministically generate additional citizens up to population.target_count from OSM residential buildings & POIs.
    pop_cfg = config.get("population") or {}
    target_count = int(pop_cfg.get("target_count", len(citizens_out)))
    pop_seed = int(pop_cfg.get("seed", 202608))

    if target_count > len(citizens_out) and pois_list and work_poi_ids:
        explicit_res = []
        fallback_res = []
        for feature in sorted(buildings, key=lambda b: b["id"]):
            bid = feature["id"]
            if bid in poi_building_ids:
                continue
            btype = str(feature["properties"].get("building", "yes")).lower()
            if btype in NON_RESIDENTIAL_BUILDING_TYPES:
                continue
            bgeom = buildings_by_id[bid]
            if bgeom.area < 35.0:
                continue
            if not all_road_union.is_empty and bgeom.distance(all_road_union) > 25.0:
                continue
            if btype in RESIDENTIAL_BUILDING_TYPES:
                explicit_res.append(bid)
            elif btype == "yes":
                fallback_res.append(bid)

        residential_pool = explicit_res + fallback_res
        if residential_pool:
            extra_needed = target_count - len(citizens_out)
            for idx in range(extra_needed):
                num = len(citizens_out) + 1
                cid = f"altstadt_citizen_{num:02d}"
                # Pick residential building deterministically (prefer explicit residential buildings first)
                if idx < len(explicit_res):
                    home_bid = explicit_res[_det_int(pop_seed, cid, "home_explicit") % len(explicit_res)]
                else:
                    home_bid = residential_pool[_det_int(pop_seed, cid, "home") % len(residential_pool)]

                home_place_id = f"home:{home_bid}"
                if home_place_id not in places_by_id:
                    bprops = building_features_by_id[home_bid]["properties"]
                    bname = bprops.get("name") or f"Wohnhaus {home_bid.rsplit(':', 1)[-1]}"
                    register_place(home_place_id, bname, home_bid, "home", buildings_by_id[home_bid], on_pilot=False)

                work_id = work_poi_ids[_det_int(pop_seed, cid, "work") % len(work_poi_ids)]
                shop_id = shop_poi_ids[_det_int(pop_seed, cid, "shop") % len(shop_poi_ids)]
                stroll_id = stroll_poi_ids[_det_int(pop_seed, cid, "stroll") % len(stroll_poi_ids)]

                # Stagger start times deterministically so the town comes alive organically
                morning_offset = (_det_int(pop_seed, cid, "morning") % 12) * 5  # 0..55 min
                lunch_offset = (_det_int(pop_seed, cid, "lunch") % 9) * 10     # 0..80 min
                evening_offset = (_det_int(pop_seed, cid, "evening") % 10) * 10
                walk_speed = 1.15 + ((_det_int(pop_seed, cid, "speed") % 8) * 0.05)
                coat_color = COAT_PALETTE[_det_int(pop_seed, cid, "coat") % len(COAT_PALETTE)]
                name = GERMAN_NAMES[idx % len(GERMAN_NAMES)]

                weekday_sched = [
                    {"start_minute": 0, "activity": "Home", "place_id": home_place_id},
                    {"start_minute": 450 + morning_offset, "activity": "Working", "place_id": work_id},
                    {"start_minute": 720 + lunch_offset, "activity": "Shopping", "place_id": shop_id},
                    {"start_minute": 810 + lunch_offset, "activity": "Working", "place_id": work_id},
                    {"start_minute": 1000 + evening_offset, "activity": "Home", "place_id": home_place_id},
                ]
                sat_sched = [
                    {"start_minute": 0, "activity": "Home", "place_id": home_place_id},
                    {"start_minute": 540 + morning_offset, "activity": "Shopping", "place_id": shop_id},
                    {"start_minute": 660 + lunch_offset, "activity": "Strolling", "place_id": stroll_id},
                    {"start_minute": 900 + evening_offset, "activity": "Home", "place_id": home_place_id},
                ]
                sun_sched = [
                    {"start_minute": 0, "activity": "Home", "place_id": home_place_id},
                    {"start_minute": 600 + morning_offset, "activity": "Strolling", "place_id": stroll_id},
                    {"start_minute": 870 + evening_offset, "activity": "Home", "place_id": home_place_id},
                ]

                register_citizen({
                    "id": cid,
                    "name": name,
                    "home_place_id": home_place_id,
                    "work_place_id": work_id,
                    "walk_speed_mps": walk_speed,
                    "coat_color": coat_color,
                    "schedule": weekday_sched,
                    "saturday_schedule": sat_sched,
                    "sunday_schedule": sun_sched,
                })

    # 5. Compile OSM entrance report explaining usage of every OSM entrance=* node.
    used_osm_entrance_by_node: dict[str, str] = {}
    places_by_building: dict[str, list[str]] = defaultdict(list)
    for place in places_out:
        bid = place.get("building_id") or ""
        if bid:
            places_by_building[bid].append(place["id"])
        ent = place.get("entrance") or {}
        if ent.get("source") == "osm" and ent.get("osm_node_id"):
            used_osm_entrance_by_node[ent["osm_node_id"]] = place["id"]

    osm_entrances_report = []
    for eid, ept, etype, _ in osm_entrances:
        nearest_bid = ""
        nearest_dist = float("inf")
        for bid, bgeom in sorted(buildings_by_id.items()):
            d = bgeom.distance(ept)
            if d < nearest_dist:
                nearest_dist = d
                nearest_bid = bid
                if d == 0.0:
                    break
        used_by = used_osm_entrance_by_node.get(eid, "")
        if used_by:
            status = "used"
            reason = "used_by_place"
        elif nearest_dist > 3.0 or not nearest_bid:
            status = "unused"
            reason = "no_building_within_3m"
        elif places_by_building.get(nearest_bid):
            status = "unused"
            reason = "secondary_entrance_same_building"
        else:
            status = "unused"
            reason = "building_without_place"
        osm_entrances_report.append({
            "osm_node_id": eid,
            "entrance_type": etype,
            "position_m": [round(ept.x, 4), round(ept.y, 4)],
            "status": status,
            "used_by_place_id": used_by,
            "nearest_building_id": nearest_bid,
            "nearest_building_distance_m": round(nearest_dist, 2) if nearest_dist < float("inf") else None,
            "reason": reason,
        })

    # 6. Compile pedestrian routes (pilot sidewalk routing + multi-street Altstadt graph + crossing awareness).
    coords_by_idx, adj, _, _ = _build_pedestrian_graph(roads, crossings)
    crossing_pts = [
        (c["id"], Point(float(c["position_m"][0]), float(c["position_m"][1])))
        for c in sorted(crossings or [], key=lambda item: item["id"])
    ]
    lateral_offset_m = pilot_width_m / 2.0 + 0.8
    routes_out = []
    routes_using_crossings = 0
    for start_id, end_id in sorted(needed_pairs):
        sp = places_by_id[start_id]
        ep = places_by_id[end_id]
        if sp["on_pilot"] and ep["on_pilot"]:
            pts, used_crossing = _pilot_route_points(
                sp, ep, road_line, lateral_offset_m, walkable_access,
                road_elevation_m, sidewalk_elevation_m, obstacles, crossing_pts,
            )
        else:
            pts, used_crossing = _graph_route_points(
                sp, ep, coords_by_idx, adj, walkable_access,
                road_elevation_m, sidewalk_elevation_m, obstacles, crossing_pts,
            )
        if used_crossing:
            routes_using_crossings += 1
        routes_out.append({
            "from_place_id": start_id,
            "to_place_id": end_id,
            "uses_crossing": used_crossing,
            "points_m": pts,
        })

    return {
        "pilot_road_id": pilot_road_id,
        "population_seed": pop_seed,
        "clock": {
            "start_minute": start_minute,
            "time_scale": time_scale,
        },
        "opening_hours_sources": dict(sorted(opening_hours_sources.items())),
        "osm_opening_hours_places": osm_opening_hours_places,
        "entrance_sources": dict(sorted(entrance_sources.items())),
        "osm_entrances_report": osm_entrances_report,
        "routes_using_crossings": routes_using_crossings,
        "places": [
            {k: v for k, v in place.items() if k not in {"along_m", "side", "on_pilot"}}
            for place in places_out
        ],
        "citizens": citizens_out,
        "routes": routes_out,
    }
