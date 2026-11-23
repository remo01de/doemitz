"""Sprint 14: city extended to the harbour and the Elde lock (water reaches, Schleuse Dömitz, Hafen, Speicher,
terrain budgets per area, streaming cells)."""

import json
from pathlib import Path
import unittest

from shapely.geometry import Point, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/manifests/doemitz-altstadt.json"
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"
LOCK_WATER = "osm:way:1315856502"
SPEICHER = "osm:way:42883863"
REF_NHN = 13.001


class Sprint14Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.pkg = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))

    def test_area_reaches_harbour_and_lock_with_unchanged_origin(self):
        self.assertEqual(self.config["bounds_lonlat"], [11.2428, 53.1372, 11.2630, 53.1455])
        self.assertEqual(self.config["origin_lonlat"], [11.2487, 53.14265], "origin must stay for saves and coordinates")
        self.assertAlmostEqual(self.config["dgm"]["reference_elevation_m"], REF_NHN)
        boundary = shape(self.scene["terrain"]["boundary"])
        for name, xy in (("Schleuse", (763.0, -280.0)), ("Hafen", (670.0, -520.0)), ("Speicher", (720.0, -557.0))):
            self.assertTrue(boundary.contains(Point(xy)), f"{name} must lie inside the extended area")
        layers = self.scene["layers"]
        self.assertGreaterEqual(len(layers["buildings"]), 770)
        works = {w["id"]: w["properties"] for w in layers["waterworks"]}
        self.assertEqual(works["osm:way:1315856503"]["waterway"], "lock_gate")
        self.assertEqual(works["osm:way:1315856504"]["waterway"], "lock_gate")
        self.assertEqual(works["osm:way:161040933"].get("lock"), "yes")
        self.assertGreaterEqual(len(layers["piers"]), 25)
        self.assertGreaterEqual(len(layers["moorings"]), 1)

    def test_lock_separates_upper_and_lower_water(self):
        levels = {w["id"]: w for w in self.pkg["terrain"]["water_levels"]}
        reaches = levels["osm:relation:285875"]["reaches"]
        nhn = sorted(r["water_level_nhn_m"] for r in reaches)
        self.assertAlmostEqual(nhn[0], 11.75, delta=0.2)
        self.assertAlmostEqual(nhn[-1], 14.70, delta=0.2)
        lock = self.pkg["locks"][0]
        self.assertEqual(lock["id"], LOCK_WATER)
        self.assertIn("Schleuse", lock["name"])
        self.assertAlmostEqual(lock["lift_m"], 2.95, delta=0.3)
        self.assertEqual(len(lock["gates"]), 2)
        self.assertTrue(all(g["leaves"] == 2 for g in lock["gates"]))
        self.assertGreater(lock["chamber_length_m"], 55.0)
        self.assertLess(lock["chamber_length_m"], 65.0)
        self.assertGreaterEqual(lock["wall_top_z_m"][0], lock["upper_level_m"] + 0.8)
        self.assertAlmostEqual(lock["walkway_z_m"], lock["wall_top_z_m"][1], delta=0.1)
        weir = self.pkg["weirs"][0]
        self.assertAlmostEqual(weir["drop_m"], lock["lift_m"], delta=0.1)
        meshes = self.pkg["meshes"]
        self.assertTrue(meshes["LockConcrete"]["collision"])
        self.assertTrue(meshes["LockRailing"]["collision"])
        self.assertFalse(meshes["LockSteel"]["collision"], "bollards, ladders and balance beams are decoration")

    def test_harbour_jetties_quays_and_boats(self):
        harbour = self.pkg["harbour"]
        self.assertGreaterEqual(harbour["jetties"], 20)
        self.assertGreaterEqual(harbour["groynes"], 1)
        self.assertGreaterEqual(len(harbour["quay_walls"]), 1)
        boats = self.pkg["props"]["instances"]["boats"]
        self.assertEqual(harbour["boats"], len(boats))
        self.assertGreaterEqual(len(boats), 10)
        water = [shape(w["geometry"]) for w in self.scene["layers"]["water"]]
        for x, y, z, _yaw, scale, variant in boats:
            self.assertTrue(any(w.contains(Point(x, y)) for w in water), f"boat at ({x}, {y}) is not on water")
            self.assertLess(z, 2.0, "boats float on the water level")
            self.assertIn(variant, (0, 1, 2))
            self.assertGreater(scale, 0.6)

    def test_speicher_uses_lod2_height_not_osm_60m(self):
        item = next(i for i in self.pkg["buildings"]["items"] if i["id"] == SPEICHER)
        self.assertEqual(item["landmark_variant"], "speicher")
        self.assertEqual(item["height_source"], "lod2")
        self.assertAlmostEqual(item["ridge_height_m"], 32.37, delta=0.05)
        self.assertLess(item["top_z_m"] - item["base_z_m"], 34.0)

    def test_terrain_error_budget_is_fine_in_the_altstadt_and_coarser_outside(self):
        report = self.pkg["terrain"]["mesh"]
        self.assertLessEqual(report["max_vertical_error_m"], 0.05 + 1e-6)
        self.assertLessEqual(report["outer_max_vertical_error_m"], 0.10 + 1e-6)
        self.assertGreater(report["fine_tiles"], 100)
        self.assertLessEqual(report["triangle_count"], self.config["dgm"]["terrain_max_triangles"])

    def test_city_meshes_are_split_into_streaming_cells(self):
        cells = self.pkg["cells"]
        self.assertEqual(cells["cell_size_m"], 256.0)
        self.assertGreaterEqual(cells["loading_range_m"], 512.0)
        self.assertEqual(cells["grid"], [6, 4])
        names = set(self.pkg["meshes"])
        self.assertTrue(any(n.startswith("WallsBrick__c") for n in names))
        self.assertIn("WallsBrick__lm", names, "landmark walls (church, fortress buildings, Speicher) stay loaded")
        self.assertNotIn("WallsBrick", names)
        for whole in ("Water", "FortressWalls", "LockConcrete", "Bridges"):
            self.assertIn(whole, names)
        for name, mesh in self.pkg["meshes"].items():
            if "__" in name:
                self.assertIn("cell", mesh)
                self.assertIn("material", mesh)

    def test_city_map_and_a_task_reach_the_harbour(self):
        city_map = self.pkg["city_map"]
        self.assertLessEqual(city_map["meters_per_pixel"], 0.5)
        templates = {t["id"]: t for t in self.pkg["tasks"]["templates"]}
        task = templates["task_tpl_errand_kaufhaus_hafenhotel"]
        places = {p["id"]: p for p in self.pkg["citizens"]["places"]}
        self.assertGreater(places[task["delivery_place_id"]]["access_m"][0], 500.0)


if __name__ == "__main__":
    unittest.main()
