"""Unit tests for Sprint 9: building entrances and versioned economy manifest."""

from pathlib import Path
import json
import unittest

from tools.mesh_generator.economy import build_economy
from tools.mesh_generator.__main__ import build as build_meshes


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed/doemitz-altstadt"
MANIFEST_STREETS = ROOT / "data/manifests/doemitz-altstadt-streets.json"
MANIFEST_CITIZENS = ROOT / "data/manifests/doemitz-altstadt-citizens.json"
MANIFEST_ECONOMY = ROOT / "data/manifests/doemitz-altstadt-economy.json"


class EconomyValidationTests(unittest.TestCase):
    def test_valid_manifest_compiles_cleanly(self):
        places = [
            {"id": "place_shop_a", "kind": "shop"},
            {"id": "place_cafe_b", "kind": "gastronomy"},
        ]
        manifest = {
            "economy_seed": 123,
            "starting_money_cents": 5000,
            "starting_money_source": "assumed_test",
            "assortments": [
                {
                    "category": "shop",
                    "items": [
                        {"id": "item_a", "name": "Brot", "price_cents": 250, "price_source": "assumed"},
                    ],
                }
            ],
            "jobs": [
                {
                    "id": "job_a",
                    "place_id": "place_shop_a",
                    "title": "Aushilfe",
                    "shift_start_minute": 540,
                    "shift_end_minute": 780,
                    "hourly_wage_cents": 1400,
                    "work_days": [0, 1, 2],
                    "wage_source": "assumed",
                }
            ],
        }
        out = build_economy(manifest, places)
        self.assertEqual(out["starting_money_cents"], 5000)
        self.assertEqual(out["item_count"], 1)
        self.assertEqual(out["job_count"], 1)

    def test_rejects_invalid_prices_duplicate_ids_and_unknown_job_places(self):
        places = [{"id": "place_a", "kind": "shop"}]
        base = {
            "starting_money_cents": 1000,
            "starting_money_source": "assumed",
            "assortments": [
                {
                    "category": "shop",
                    "items": [{"id": "item_1", "name": "Test", "price_cents": 100, "price_source": "assumed"}],
                }
            ],
            "jobs": [],
        }

        bad_price = json.loads(json.dumps(base))
        bad_price["assortments"][0]["items"][0]["price_cents"] = 0
        with self.assertRaises(ValueError):
            build_economy(bad_price, places)

        dup_item = json.loads(json.dumps(base))
        dup_item["assortments"][0]["items"].append(
            {"id": "item_1", "name": "Dup", "price_cents": 200, "price_source": "assumed"}
        )
        with self.assertRaises(ValueError):
            build_economy(dup_item, places)

        bad_job = json.loads(json.dumps(base))
        bad_job["jobs"].append({
            "id": "job_bad",
            "place_id": "place_missing",
            "title": "Nope",
            "shift_start_minute": 540,
            "shift_end_minute": 720,
            "hourly_wage_cents": 1200,
            "work_days": [0],
            "wage_source": "assumed",
        })
        with self.assertRaises(ValueError):
            build_economy(bad_job, places)


class Sprint09AltstadtTests(unittest.TestCase):
    def test_every_place_has_unique_entrance_and_economy_matches_places(self):
        scene_path = PROCESSED / "scene.json"
        report_path = PROCESSED / "import-report.json"
        if not scene_path.exists() or not report_path.exists():
            self.skipTest("processed scene not present")

        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        streets = json.loads(MANIFEST_STREETS.read_text(encoding="utf-8"))
        citizens_cfg = json.loads(MANIFEST_CITIZENS.read_text(encoding="utf-8"))
        economy_cfg = json.loads(MANIFEST_ECONOMY.read_text(encoding="utf-8"))

        pkg = build_meshes(
            scene, report, streets.get("sidewalk_widths_m"), streets.get("vehicle"),
            citizens_cfg, streets.get("default_sidewalk_widths_m"), streets.get("traffic_network"),
            economy_cfg,
        )

        places = pkg["citizens"]["places"]
        entrance_ids = set()
        for place in places:
            ent = place.get("entrance")
            self.assertIsNotNone(ent, f"place {place['id']} missing entrance")
            self.assertEqual(ent["id"], f"entrance:{place['id']}")
            self.assertNotIn(ent["id"], entrance_ids)
            entrance_ids.add(ent["id"])
            self.assertIn(ent["source"], {"osm", "assumed_sidewalk_access"})
            self.assertEqual(len(ent["position_m"]), 3)

        econ = pkg["economy"]
        self.assertIsNotNone(econ)
        self.assertEqual(econ["starting_money_cents"], economy_cfg["starting_money_cents"])
        self.assertGreater(econ["item_count"], 10)
        self.assertGreaterEqual(econ["job_count"], 3)
        place_ids = {p["id"] for p in places}
        for job in econ["jobs"]:
            self.assertIn(job["place_id"], place_ids)
            self.assertGreater(job["hourly_wage_cents"], 0)
        item_ids = [item["id"] for grp in econ["assortments"] for item in grp["items"]]
        self.assertEqual(len(item_ids), len(set(item_ids)))
        for grp in econ["assortments"]:
            for item in grp["items"]:
                self.assertGreater(item["price_cents"], 0)


if __name__ == "__main__":
    unittest.main()
