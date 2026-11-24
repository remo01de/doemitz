"""Unit tests for Sprint 8: POI layer, opening hours, 30 citizens, and road crossings."""

from pathlib import Path
import json
import unittest

from tools.mesh_generator.opening_hours import is_open_at, parse_osm_opening_hours, resolve_opening_hours
from tools.mesh_generator.road_graph import build_road_graph
from tools.mesh_generator.__main__ import build as build_meshes


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed/doemitz-altstadt"
MANIFEST_STREETS = ROOT / "data/manifests/doemitz-altstadt-streets.json"
MANIFEST_CITIZENS = ROOT / "data/manifests/doemitz-altstadt-citizens.json"


class OpeningHoursTests(unittest.TestCase):
    def test_24_7_and_simple_ranges(self):
        oh = resolve_opening_hours("shop", "24/7")
        self.assertEqual(oh["source"], "osm")
        self.assertTrue(oh["always_open"])
        self.assertTrue(is_open_at(oh, 6, 120))

        apotheke = resolve_opening_hours("shop", "Mo-Fr 08:00-12:30, 14:00-18:00; Sa 09:00-12:00")
        self.assertEqual(apotheke["source"], "osm")
        self.assertTrue(is_open_at(apotheke, 0, 500))   # Mo 08:20
        self.assertFalse(is_open_at(apotheke, 0, 800))  # Mo 13:20 lunch break
        self.assertTrue(is_open_at(apotheke, 0, 900))   # Mo 15:00
        self.assertTrue(is_open_at(apotheke, 5, 600))   # Sa 10:00
        self.assertFalse(is_open_at(apotheke, 5, 780))  # Sa 13:00
        self.assertFalse(is_open_at(apotheke, 6, 600))  # Su closed

    def test_wraparound_and_off_overrides(self):
        cafe = resolve_opening_hours("gastronomy", "Mo-Fr 10:00-15:00,17:00-21:00; Tu off; We off; Sa,Su 10:00-21:00")
        self.assertTrue(is_open_at(cafe, 0, 720))   # Mo 12:00
        self.assertFalse(is_open_at(cafe, 1, 720))  # Tu off
        self.assertFalse(is_open_at(cafe, 2, 720))  # We off
        self.assertTrue(is_open_at(cafe, 6, 900))   # Su 15:00

        wrap = resolve_opening_hours("gastronomy", "Th-Mo,PH 12:00-17:00; Tu,We off")
        self.assertTrue(is_open_at(wrap, 3, 780))   # Th 13:00
        self.assertTrue(is_open_at(wrap, 6, 780))   # Su 13:00
        self.assertTrue(is_open_at(wrap, 0, 780))   # Mo 13:00
        self.assertFalse(is_open_at(wrap, 1, 780))  # Tu off

    def test_seasonal_and_assumed_defaults(self):
        ti = parse_osm_opening_hours(
            "Oct-May: Mo-Th 10:00-15:00; Fr 10:00-14:00; Jun-Sep: Mo-Th 10:00-16:00; Fr 10:00-15:00",
            reference_month=6,
        )
        self.assertIsNotNone(ti)
        self.assertEqual(ti[0], [[600, 960]])  # June -> 10:00-16:00
        self.assertEqual(ti[4], [[600, 900]])  # Fr 10:00-15:00

        assumed = resolve_opening_hours("shop", None)
        self.assertEqual(assumed["source"], "assumed_shop_default")
        self.assertTrue(is_open_at(assumed, 0, 600))
        self.assertFalse(is_open_at(assumed, 6, 600))  # Closed Sunday


class Sprint08PipelineTests(unittest.TestCase):
    def test_poi_layer_and_crossings_in_processed_scene(self):
        scene_path = PROCESSED / "scene.json"
        if not scene_path.exists():
            self.skipTest("processed scene.json not present")
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        pois = scene["layers"].get("pois", [])
        self.assertGreater(len(pois), 50)
        poi_ids = [p["id"] for p in pois]
        self.assertEqual(len(poi_ids), len(set(poi_ids)))
        self.assertTrue(all(pid.startswith("poi:osm:") for pid in poi_ids))

        crossings = scene.get("crossings", [])
        self.assertGreaterEqual(len(crossings), 4)

        graph = build_road_graph(scene["layers"]["roads"], lambda _: (6.0, "test"), 0.08, crossings)
        self.assertGreater(graph["crossing_count"], 0)
        edges_with_crossings = [e for e in graph["edges"] if e["crossings"]]
        self.assertGreater(len(edges_with_crossings), 0)

    def test_thirty_citizens_deterministic_and_weekly_schedules(self):
        scene_path = PROCESSED / "scene.json"
        report_path = PROCESSED / "import-report.json"
        if not scene_path.exists() or not report_path.exists():
            self.skipTest("processed scene not present")
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        streets = json.loads(MANIFEST_STREETS.read_text(encoding="utf-8"))
        citizens_cfg = json.loads(MANIFEST_CITIZENS.read_text(encoding="utf-8"))

        pkg1 = build_meshes(
            scene, report, streets.get("sidewalk_widths_m"), streets.get("vehicle"),
            citizens_cfg, streets.get("default_sidewalk_widths_m"), streets.get("traffic_network"),
        )
        pkg2 = build_meshes(
            scene, report, streets.get("sidewalk_widths_m"), streets.get("vehicle"),
            citizens_cfg, streets.get("default_sidewalk_widths_m"), streets.get("traffic_network"),
        )
        self.assertEqual(pkg1["citizens"], pkg2["citizens"])
        cit = pkg1["citizens"]
        self.assertEqual(len(cit["citizens"]), citizens_cfg["population"]["target_count"])
        ids = {c["id"] for c in cit["citizens"]}
        for legacy in ("citizen_anna_01", "citizen_bernd_02", "citizen_clara_03", "citizen_dieter_04"):
            self.assertIn(legacy, ids)
        for c in cit["citizens"]:
            self.assertTrue(c["schedule"])
            self.assertTrue(c["saturday_schedule"])
            self.assertTrue(c["sunday_schedule"])
        self.assertGreater(cit["opening_hours_sources"].get("osm", 0), 0)
        self.assertGreater(cit["routes_using_crossings"], 0)


if __name__ == "__main__":
    unittest.main()
