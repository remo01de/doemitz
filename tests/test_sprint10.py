"""Unit tests for Sprint 10: OSM entrances report, offline city map, tasks manifest, priority signs, and parking."""

from pathlib import Path
import json
import struct
import unittest

from shapely.geometry import LineString, mapping

from tools.mesh_generator.__main__ import ROAD_ELEVATION_M, build as build_meshes, road_width
from tools.mesh_generator.city_map import (
    MAP_ATTRIBUTION,
    compute_map_metadata,
    pixel_to_world,
    render_city_map,
    world_to_pixel,
)
from tools.mesh_generator.road_graph import build_road_graph
from tools.mesh_generator.tasks import build_tasks


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed/doemitz-altstadt"
MANIFEST_STREETS = ROOT / "data/manifests/doemitz-altstadt-streets.json"
MANIFEST_CITIZENS = ROOT / "data/manifests/doemitz-altstadt-citizens.json"
MANIFEST_ECONOMY = ROOT / "data/manifests/doemitz-altstadt-economy.json"
MANIFEST_TASKS = ROOT / "data/manifests/doemitz-altstadt-tasks.json"


class TasksValidationTests(unittest.TestCase):
    def test_valid_and_invalid_task_templates(self):
        places = [
            {"id": "place_a", "kind": "shop", "economy_category": "shop"},
            {"id": "place_b", "kind": "work", "economy_category": "work"},
        ]
        economy = {
            "assortments": [
                {"category": "shop", "items": [{"id": "item_bread", "name": "Brot", "price_cents": 300}]}
            ]
        }
        valid = {
            "task_seed": 42,
            "daily_min_tasks": 1,
            "daily_max_tasks": 2,
            "templates": [
                {
                    "id": "tpl_errand",
                    "type": "errand",
                    "title": "Paket",
                    "description": "Von A nach B",
                    "pickup_place_id": "place_a",
                    "delivery_place_id": "place_b",
                    "parcel_name": "Kiste",
                    "duration_minutes": 120,
                    "reward_cents": 800,
                    "reward_source": "assumed_test",
                },
                {
                    "id": "tpl_fetch",
                    "type": "fetch",
                    "title": "Brot holen",
                    "description": "Kauf Brot",
                    "requested_item_id": "item_bread",
                    "preferred_shop_place_id": "place_a",
                    "duration_minutes": 120,
                    "reward_cents": 600,
                    "reward_source": "assumed_test",
                },
            ],
        }
        compiled = build_tasks(valid, places, economy)
        self.assertEqual(compiled["template_count"], 2)
        self.assertEqual(compiled["errand_count"], 1)
        self.assertEqual(compiled["fetch_count"], 1)

        # Reject unknown item
        bad_item = json.loads(json.dumps(valid))
        bad_item["templates"][1]["requested_item_id"] = "item_missing"
        with self.assertRaises(ValueError):
            build_tasks(bad_item, places, economy)

        # Reject unknown place
        bad_place = json.loads(json.dumps(valid))
        bad_place["templates"][0]["delivery_place_id"] = "place_missing"
        with self.assertRaises(ValueError):
            build_tasks(bad_place, places, economy)

        # Reject duplicate template ID
        dup_id = json.loads(json.dumps(valid))
        dup_id["templates"][1]["id"] = "tpl_errand"
        with self.assertRaises(ValueError):
            build_tasks(dup_id, places, economy)


class PrioritySignsSyntheticTests(unittest.TestCase):
    def test_stop_and_give_way_assign_to_correct_edges_and_junction_report(self):
        roads = [
            {
                "id": "osm:way:10",
                "properties": {"highway": "residential", "name": "Nebenweg"},
                "geometry": mapping(LineString([(0, 0), (10, 0), (20, 0)])),
                "node_ids": ["osm:node:1", "osm:node:2", "osm:node:3"],
            },
            {
                "id": "osm:way:20",
                "properties": {"highway": "primary", "name": "Hauptstrasse"},
                "geometry": mapping(LineString([(20, -15), (20, 0), (20, 15)])),
                "node_ids": ["osm:node:4", "osm:node:3", "osm:node:5"],
            },
            {
                "id": "osm:way:30",
                "properties": {"highway": "residential", "name": "Rueckweg", "oneway": "yes"},
                "geometry": mapping(LineString([(20, 15), (0, 0)])),
                "node_ids": ["osm:node:5", "osm:node:1"],
            },
        ]
        signs = [
            {"id": "osm:node:2", "position_m": [16.0, 0.0], "sign": "stop", "direction": "forward"},
        ]
        graph = build_road_graph(roads, road_width, ROAD_ELEVATION_M, priority_signs=signs)
        edges_by_id = {e["id"]: e for e in graph["edges"]}
        self.assertEqual(edges_by_id["edge:osm:way:10:0:0:fwd"]["yield_rule"], "stop")
        self.assertEqual(edges_by_id["edge:osm:way:10:0:0:fwd"]["yield_source"], "osm_stop")
        self.assertEqual(edges_by_id["edge:osm:way:10:0:0:rev"]["yield_rule"], "none")

        junctions_by_id = {j["node_id"]: j for j in graph["junctions"]}
        self.assertIn("osm:node:3", junctions_by_id)
        self.assertEqual(junctions_by_id["osm:node:3"]["rule"], "priority_sign")
        self.assertEqual(junctions_by_id["osm:node:3"]["source"], "osm_stop")
        self.assertEqual(junctions_by_id["osm:node:1"]["rule"], "right_before_left")


class Sprint10AltstadtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene_path = PROCESSED / "scene.json"
        cls.report_path = PROCESSED / "import-report.json"
        if not cls.scene_path.exists() or not cls.report_path.exists():
            raise unittest.SkipTest("processed Altstadt scene not present")
        cls.scene = json.loads(cls.scene_path.read_text(encoding="utf-8"))
        cls.report = json.loads(cls.report_path.read_text(encoding="utf-8"))
        cls.streets = json.loads(MANIFEST_STREETS.read_text(encoding="utf-8"))
        cls.citizens_cfg = json.loads(MANIFEST_CITIZENS.read_text(encoding="utf-8"))
        cls.economy_cfg = json.loads(MANIFEST_ECONOMY.read_text(encoding="utf-8"))
        cls.tasks_cfg = json.loads(MANIFEST_TASKS.read_text(encoding="utf-8"))
        cls.pkg = build_meshes(
            cls.scene,
            cls.report,
            cls.streets.get("sidewalk_widths_m"),
            cls.streets.get("vehicle"),
            cls.citizens_cfg,
            cls.streets.get("default_sidewalk_widths_m"),
            cls.streets.get("traffic_network"),
            cls.economy_cfg,
            cls.tasks_cfg,
        )

    def test_osm_entrances_all_accounted_for_and_place_buildings_use_osm_entrance(self):
        osm_entrances = self.scene.get("entrances", [])
        self.assertEqual(len(osm_entrances), 9)  # Sprint 14: one more OSM entrance in the harbour extension
        report = self.pkg["citizens"]["osm_entrances_report"]
        self.assertEqual(len(report), len(osm_entrances))

        valid_reasons = {
            "used_by_place",
            "secondary_entrance_same_building",
            "building_without_place",
            "no_building_within_3m",
        }
        place_buildings = {p["building_id"] for p in self.pkg["citizens"]["places"] if p["building_id"]}
        used_buildings = set()
        for entry in report:
            self.assertIn(entry["status"], {"used", "unused"})
            self.assertIn(entry["reason"], valid_reasons)
            if entry["status"] == "used":
                self.assertEqual(entry["reason"], "used_by_place")
                self.assertTrue(entry["used_by_place_id"])
                used_buildings.add(entry["nearest_building_id"])

        # Every OSM entrance on a building that hosts a place must be used (or secondary on a building that already uses one)
        for entry in report:
            bid = entry["nearest_building_id"]
            dist_m = entry["nearest_building_distance_m"]
            if bid in place_buildings and dist_m is not None and dist_m <= 3.0:
                self.assertIn(
                    entry["reason"],
                    {"used_by_place", "secondary_entrance_same_building"},
                    f"OSM entrance {entry['osm_node_id']} on place building {bid} was unexpectedly dropped",
                )
                self.assertIn(bid, used_buildings)

    def test_city_map_deterministic_and_known_osm_nodes_map_accurately(self):
        png1, meta1 = render_city_map(self.scene, road_width, size_px=512)
        png2, meta2 = render_city_map(self.scene, road_width, size_px=512)
        self.assertEqual(png1, png2, "city map PNG must be byte-identical across runs")
        self.assertEqual(meta1, meta2)
        self.assertTrue(png1.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png1[16:24])
        self.assertEqual((width, height), (512, 512))
        self.assertIn(MAP_ATTRIBUTION, meta1["attribution"])

        # Check full 2048x2048 metadata mapping against known OSM reference nodes (Goethestrasse)
        full_meta = compute_map_metadata(self.pkg["bounds_m"], size_px=2048)
        v_min_e, v_min_n, v_max_e, v_max_n = full_meta["view_bounds_m"]
        for ref_east, ref_north in self.pkg["reference_points_m"]:
            px, py = world_to_pixel(ref_east, ref_north, full_meta)
            size = float(full_meta["width_px"])  # Sprint 14: 4096 px for the extended area (<= 0.5 m/px)
            expected_px = (ref_east - v_min_e) / (v_max_e - v_min_e) * size
            expected_py = (v_max_n - ref_north) / (v_max_n - v_min_n) * size
            self.assertAlmostEqual(px, expected_px, delta=1.0)
            self.assertAlmostEqual(py, expected_py, delta=1.0)
            self.assertTrue(0.0 <= px <= size and 0.0 <= py <= size)
            back_e, back_n = pixel_to_world(px, py, full_meta)
            self.assertAlmostEqual(back_e, ref_east, delta=1e-4)
            self.assertAlmostEqual(back_n, ref_north, delta=1e-4)

        # Check generated 4096x4096 city-map.png on disk if present (Sprint 14)
        disk_png = PROCESSED / "city-map.png"
        if disk_png.exists():
            raw = disk_png.read_bytes()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
            w, h = struct.unpack(">II", raw[16:24])
            self.assertEqual((w, h), (4096, 4096))

    def test_tasks_manifest_compiled_with_valid_places_and_items(self):
        tasks = self.pkg["tasks"]
        self.assertIsNotNone(tasks)
        self.assertGreaterEqual(tasks["template_count"], 8)
        self.assertEqual(tasks["daily_min_tasks"], 3)
        self.assertEqual(tasks["daily_max_tasks"], 5)

        place_ids = {p["id"] for p in self.pkg["citizens"]["places"]}
        item_ids = {
            it["id"]
            for grp in self.pkg["economy"]["assortments"]
            for it in grp["items"]
        }
        seen = set()
        for tpl in tasks["templates"]:
            self.assertNotIn(tpl["id"], seen)
            seen.add(tpl["id"])
            self.assertGreater(tpl["reward_cents"], 0)
            self.assertTrue(tpl["reward_source"])
            if tpl["type"] == "errand":
                self.assertIn(tpl["pickup_place_id"], place_ids)
                self.assertIn(tpl["delivery_place_id"], place_ids)
                self.assertNotEqual(tpl["pickup_place_id"], tpl["delivery_place_id"])
            else:
                self.assertEqual(tpl["type"], "fetch")
                self.assertIn(tpl["requested_item_id"], item_ids)
                self.assertIn(tpl["preferred_shop_place_id"], place_ids)

    def test_priority_signs_and_parking_lots_in_altstadt_road_graph(self):
        rg = self.pkg["road-graph"]
        self.assertEqual(rg["priority_sign_count"], 6)
        edges_by_id = {e["id"]: e for e in rg["edges"]}

        # Real give_way sign on An der Bleiche approaching Torstrasse (osm:node:36552454)
        self.assertEqual(edges_by_id["edge:osm:way:157877525:0:0:fwd"]["yield_rule"], "give_way")
        self.assertEqual(edges_by_id["edge:osm:way:178018735:0:1:rev"]["yield_rule"], "none")
        # Real give_way sign on Promenade approaching Torstrasse (osm:node:36552456)
        self.assertEqual(edges_by_id["edge:osm:way:29732847:0:0:rev"]["yield_rule"], "give_way")
        # Real give_way sign on Goethestrasse approaching Slüterplatz (osm:node:277309016)
        self.assertEqual(edges_by_id["edge:osm:way:25642325:0:2:fwd"]["yield_rule"], "give_way")
        # Right-before-left junction from Sprint 7 stays right_before_left
        junctions_by_id = {j["node_id"]: j for j in rg["junctions"]}
        self.assertEqual(junctions_by_id["osm:node:277309010"]["rule"], "right_before_left")
        self.assertEqual(junctions_by_id["osm:node:36552454"]["rule"], "priority_sign")

        # Parking lots: all amenity=parking features mapped to drivable main-SCC edges
        lots = rg["parking_lots"]
        self.assertGreaterEqual(len(lots), 9)
        lot_ids = set()
        for lot in lots:
            self.assertNotIn(lot["id"], lot_ids)
            lot_ids.add(lot["id"])
            self.assertGreaterEqual(lot["capacity"], 1)
            self.assertTrue(lot["capacity_source"])
            self.assertGreaterEqual(len(lot["slots_m"]), 1)
            acc = edges_by_id.get(lot["access_edge_id"])
            self.assertIsNotNone(acc, f"parking {lot['id']} access edge missing")
            self.assertFalse(acc["dead_end"], f"parking {lot['id']} access edge {acc['id']} is dead_end")

        # 8 vehicles in traffic_network
        self.assertEqual(len(self.pkg["traffic_network"]["vehicles"]), 8)


if __name__ == "__main__":
    unittest.main()
