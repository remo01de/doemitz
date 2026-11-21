import json
from pathlib import Path
import unittest

from shapely.geometry import LineString, mapping

from tools.mesh_generator.__main__ import ROAD_ELEVATION_M, road_width
from tools.mesh_generator.road_graph import build_road_graph, parse_speed_kmh


ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "data/processed/doemitz-altstadt/scene.json"


class RoadGraphTest(unittest.TestCase):
    def test_speed_parsing_and_assumptions(self):
        self.assertEqual(parse_speed_kmh({"maxspeed": "50"}), (50.0, "osm_maxspeed"))
        self.assertEqual(parse_speed_kmh({"maxspeed": "30 km/h"}), (30.0, "osm_maxspeed"))
        self.assertEqual(parse_speed_kmh({"surface": "cobblestone"}), (20.0, "estimated_cobblestone_20kmh"))
        self.assertEqual(parse_speed_kmh({"surface": "sett"}), (20.0, "estimated_cobblestone_20kmh"))
        self.assertEqual(parse_speed_kmh({"highway": "residential"}), (30.0, "estimated_altstadt_30kmh"))

    def test_directed_graph_marks_dead_ends_and_keeps_osm_node_ids(self):
        roads = [
            {
                "id": "osm:way:1",
                "properties": {"highway": "residential", "oneway": "yes", "maxspeed": "30"},
                "geometry": mapping(LineString([(0, 0), (10, 0)])),
                "node_ids": ["osm:node:101", "osm:node:102"],
            },
            {
                "id": "osm:way:2",
                "properties": {"highway": "residential", "oneway": "yes", "surface": "sett"},
                "geometry": mapping(LineString([(10, 0), (10, 10)])),
                "node_ids": ["osm:node:102", "osm:node:103"],
            },
            {
                "id": "osm:way:3",
                "properties": {"highway": "residential", "oneway": "yes"},
                "geometry": mapping(LineString([(10, 10), (0, 0)])),
                "node_ids": ["osm:node:103", "osm:node:101"],
            },
            {
                "id": "osm:way:4",
                "properties": {"highway": "service", "oneway": "yes"},
                "geometry": mapping(LineString([(10, 0), (20, 0)])),
                "node_ids": ["osm:node:102", "osm:node:104"],
            },
        ]
        graph = build_road_graph(roads, road_width, ROAD_ELEVATION_M)
        self.assertEqual(graph["node_count"], 4)
        self.assertEqual(graph["edge_count"], 4)
        self.assertEqual(graph["main_scc_edge_count"], 3)
        self.assertEqual(graph["dead_end_edge_count"], 1)

        by_way = {e["way_id"]: e for e in graph["edges"]}
        self.assertFalse(by_way["osm:way:1"]["dead_end"])
        self.assertEqual(by_way["osm:way:1"]["speed_kmh"], 30.0)
        self.assertEqual(by_way["osm:way:1"]["speed_source"], "osm_maxspeed")
        self.assertEqual(by_way["osm:way:2"]["speed_kmh"], 20.0)
        self.assertEqual(by_way["osm:way:2"]["speed_source"], "estimated_cobblestone_20kmh")
        self.assertTrue(by_way["osm:way:4"]["dead_end"])

        nodes_by_id = {n["id"]: n for n in graph["nodes"]}
        self.assertTrue(nodes_by_id["osm:node:102"]["is_junction"])
        self.assertEqual(nodes_by_id["osm:node:102"]["osm_node_id"], "osm:node:102")

    def test_altstadt_road_graph_strong_connectivity_and_dead_ends(self):
        if not SCENE_PATH.exists():
            self.skipTest("processed Altstadt scene.json not present")
        scene = json.loads(SCENE_PATH.read_text(encoding="utf-8"))
        graph = build_road_graph(scene["layers"]["roads"], road_width, ROAD_ELEVATION_M)

        self.assertGreater(graph["main_scc_edge_count"], 50)
        self.assertEqual(
            graph["edge_count"],
            graph["main_scc_edge_count"] + graph["dead_end_edge_count"],
        )

        # Verify every junction node carries an OSM node ID
        junctions = [n for n in graph["nodes"] if n["is_junction"]]
        self.assertGreater(len(junctions), 20)
        for j in junctions:
            self.assertIsNotNone(j["osm_node_id"], f"Junction {j['id']} missing OSM node ID")
            self.assertTrue(j["id"].startswith("osm:node:"))

        # Verify all non-dead-end edges form a single strongly connected component
        main_edges = [e for e in graph["edges"] if not e["dead_end"]]
        self.assertEqual(len(main_edges), graph["main_scc_edge_count"])
        main_nodes = {e["from_node"] for e in main_edges} | {e["to_node"] for e in main_edges}

        fwd_adj = {n: [] for n in main_nodes}
        rev_adj = {n: [] for n in main_nodes}
        for e in main_edges:
            fwd_adj[e["from_node"]].append(e["to_node"])
            rev_adj[e["to_node"]].append(e["from_node"])

        def reachable(start, adj):
            visited = {start}
            stack = [start]
            while stack:
                cur = stack.pop()
                for nxt in adj[cur]:
                    if nxt not in visited:
                        visited.add(nxt)
                        stack.append(nxt)
            return visited

        seed = next(iter(sorted(main_nodes)))
        self.assertEqual(reachable(seed, fwd_adj), main_nodes, "Main road network is not forward-connected")
        self.assertEqual(reachable(seed, rev_adj), main_nodes, "Main road network is not reverse-connected")

        # Verify edge invariants
        edge_ids = [e["id"] for e in graph["edges"]]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))
        for e in graph["edges"]:
            self.assertGreater(e["width_m"], 0.0)
            self.assertGreater(e["speed_kmh"], 0.0)
            self.assertGreater(e["length_m"], 0.0)
            self.assertGreaterEqual(len(e["points_m"]), 2)
            self.assertIn("oneway", e)
            self.assertIn("speed_source", e)
