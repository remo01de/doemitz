"""Sprint 13: fortress gate passage, LoD2 eave fix, Rathausturm, distance-field-free city meshes and interiors."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from tools.geo_import.export import build as build_geo
from tools.mesh_generator.__main__ import build as build_meshes
from tools.mesh_generator.interiors import CAPSULE_RADIUS_M, _Walkable


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/manifests/doemitz-altstadt.json"
MANIFESTS = ROOT / "data/manifests"
RAW_DIR = ROOT / "data/raw/doemitz-altstadt"
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"
GATE_TUNNEL = "osm:way:120431987"


def _load(name):
    return json.loads((MANIFESTS / name).read_text(encoding="utf-8"))


class Sprint13Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.pkg = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))
        cls.interiors_cfg = _load("doemitz-altstadt-interiors.json")
        cls.buildings = {b["id"]: b for b in cls.scene["layers"]["buildings"]}
        cls.items = {b["id"]: b for b in cls.pkg["buildings"]["items"]}

    # --- Festungstor --------------------------------------------------------------------------------
    def test_fortress_gate_passage_is_built_at_approach_level(self):
        portals = {p["road_id"]: p for p in self.pkg["tunnel_portals"]}
        self.assertIn(GATE_TUNNEL, portals, "the fortress gate passage must be built")
        gate = portals[GATE_TUNNEL]
        self.assertEqual(gate["floor_sources"], ["tunnel_approach_min_dgm", "tunnel_approach_min_dgm"])
        self.assertLessEqual(gate["floor_slope_percent"], 6.0)
        self.assertGreaterEqual(gate["clear_height_m"], 3.0)
        ref = self.scene["terrain"]["reference_elevation_m"]
        for key in ("entry_point_3d_m", "exit_point_3d_m"):
            z_nhn = gate[key][2] - 0.08 + ref
            # rampart crest above the gate is 20-22 m NHN, courtyard and drawbridge are about 16.1-16.5 m NHN
            self.assertLess(z_nhn, 17.0, f"{key} lies on the rampart instead of the approach: {z_nhn:.2f} m NHN")
        not_built = {t["road_id"] for t in self.pkg["tunnels_not_built"]}
        self.assertNotIn(GATE_TUNNEL, not_built)

    def test_gate_approach_road_and_drawbridge_are_level(self):
        roads = {r["id"]: r for r in self.pkg["terrain"]["roads_elevation"]["roads"]}
        self.assertLessEqual(roads["osm:way:416256368"]["max_slope_percent"], 6.0)
        bridges = {b["id"]: b for b in self.pkg["bridges"]}
        self.assertLessEqual(bridges["bridge:osm:way:120431984"]["max_slope_percent"], 6.0)

    def test_fortress_escarp_wall_along_the_outline_with_gate_and_steg_openings(self):
        walls = {w["outline_id"]: w for w in self.pkg["fortress_walls"]}
        self.assertIn("osm:way:42318561", walls, "the fortress needs its brick escarp")
        wall = walls["osm:way:42318561"]
        gap_total = sum(g["width_m"] for g in wall["gaps"])
        self.assertAlmostEqual(wall["built_length_m"], wall["outline_length_m"] - gap_total, delta=0.5)
        labels = " ".join(g["label"] for g in wall["gaps"])
        self.assertIn("osm:way:416256368", labels)  # gate approach from the drawbridge
        self.assertIn("osm:way:416256369", labels)  # NW-Steg tunnel portal
        self.assertGreaterEqual(wall["height_m"][0], 2.5 - 1e-6)
        water = {w["id"]: w["water_level_m"] for w in self.pkg["terrain"]["water_levels"]}
        self.assertLess(wall["foot_z_m"][1], water["osm:relation:2215646"], "wall foot must reach below the moat water")
        self.assertEqual(len(wall["cheek_walls"]), 1)
        meshes = self.pkg["meshes"]
        for name in ("FortressWalls", "FortressCoping"):
            self.assertTrue(meshes[name]["collision"], name)
        self.assertEqual(meshes["FortressWalls"]["material"], "WallsBrick")
        refs = {r["id"] for r in _load("doemitz-altstadt-references.json")["references"]}
        for rid in wall["reference_ids"]:
            self.assertIn(rid, refs)

    # --- LoD2 eave height ---------------------------------------------------------------------------
    def test_wallstrasse_6_eave_from_main_roof(self):
        item = self.items["osm:way:198050053"]
        self.assertEqual(item["height_source"], "lod2")
        self.assertGreater(item["eave_height_m"], 7.5, "a 7.7 m² porch roof must not define the eave")
        self.assertLess(item["ridge_height_m"] - item["eave_height_m"], 5.0)

    def test_no_lod2_building_has_clamped_two_metre_eave_under_a_tall_roof(self):
        for item in self.pkg["buildings"]["items"]:
            if item["height_source"] != "lod2" or item["landmark_variant"]:
                continue
            if item["eave_height_m"] <= 2.01:
                self.assertLess(item["ridge_height_m"], 6.0, f"{item['id']} has a 2 m eave under a {item['ridge_height_m']} m ridge")

    # --- Rathausturm --------------------------------------------------------------------------------
    def test_rathausturm_landmark_rises_above_rathaus(self):
        tower = self.items["osm:way:97118216"]
        rathaus = self.items["osm:way:41020272"]
        self.assertEqual(tower["landmark_variant"], "rathausturm")
        self.assertGreater(tower["top_z_m"], rathaus["top_z_m"] + 5.0)
        lm = _load("doemitz-altstadt-landmarks.json")
        self.assertNotIn("tower_corner_local_m", lm["buildings"]["osm:way:41020272"])

    # --- Interiors ----------------------------------------------------------------------------------
    def test_interior_manifest_references_existing_buildings_and_places(self):
        places = {p["id"]: p for p in self.pkg["citizens"]["places"]}
        templates = self.interiors_cfg["templates"]
        ids = set()
        for cfg in self.interiors_cfg["interiors"]:
            self.assertNotIn(cfg["id"], ids)
            ids.add(cfg["id"])
            self.assertIn(cfg["building_id"], self.buildings)
            self.assertIn(cfg["place_id"], places)
            self.assertEqual(places[cfg["place_id"]]["building_id"], cfg["building_id"])
            self.assertIn(cfg["template"], templates)
        self.assertEqual(len(self.pkg["interiors"]), len(self.interiors_cfg["interiors"]))

    def test_door_opening_sits_at_the_entrance(self):
        places = {p["id"]: p for p in self.pkg["citizens"]["places"]}
        for entry in self.pkg["interiors"]:
            ent = places[entry["place_id"]]["entrance"]
            self.assertEqual(ent["source"], "interior_door")
            poly = Polygon(self.buildings[entry["building_id"]]["geometry"]["coordinates"][0])
            ring = LineString(poly.exterior.coords)
            p = Point(ent["position_m"][0], ent["position_m"][1])
            foot = ring.interpolate(ring.project(p))
            door = entry["door"]["outer_center_m"]
            self.assertLessEqual(foot.distance(Point(door[0], door[1])), 0.10, f"{entry['id']} door is not at its entrance")
            door_op = [o for o in entry["openings"] if o["kind"] == "door"]
            self.assertEqual(len(door_op), 1)
            self.assertAlmostEqual(door_op[0]["u1_m"] - door_op[0]["u0_m"], entry["door"]["width_m"], places=3)

    def test_interior_lies_inside_the_osm_footprint(self):
        for entry in self.pkg["interiors"]:
            footprint = Polygon(self.buildings[entry["building_id"]]["geometry"]["coordinates"][0])
            room = Polygon(entry["room_polygon_m"])
            self.assertTrue(room.is_valid)
            self.assertTrue(footprint.buffer(1e-6).contains(room), f"{entry['id']} leaves the footprint")
            self.assertGreaterEqual(entry["ceiling_z_m"] - entry["floor_z_m"], 2.5)
            for f in entry["furniture"]:
                self.assertTrue(room.buffer(0.03).contains(Polygon(f["footprint_m"])), f"{entry['id']} furniture outside room")

    def test_every_spot_counter_and_board_is_walkable_from_the_door(self):
        for entry in self.pkg["interiors"]:
            room = Polygon(entry["room_polygon_m"])
            furniture = [Polygon(f["footprint_m"]) for f in entry["furniture"]]
            # 0.9 m corridors: a capsule of 2 * 0.36 m plus margin must pass
            self.assertGreaterEqual(2 * CAPSULE_RADIUS_M, 0.7)
            targets = [s["position_m"][:2] for s in entry["stand_spots"]]
            if entry["counter_m"]:
                targets.append(entry["counter_m"][:2])
            if entry["notice_board_m"]:
                targets.append(entry["notice_board_m"][:2])
            ok = _Walkable(room).reachable(furniture, entry["door"]["inside_m"][:2], targets)
            self.assertTrue(all(ok), f"{entry['id']} unreachable targets: {[t for t, k in zip(targets, ok) if not k]}")
            self.assertTrue(entry["walkable_from_door"])
            self.assertLessEqual(len(entry["stand_spots"]), 6)
            self.assertIsNotNone(entry["counter_m"])

    def test_buergerbuero_has_notice_board_and_shops_have_shelves(self):
        by_place = {e["place_id"]: e for e in self.pkg["interiors"]}
        self.assertIsNotNone(by_place["poi:osm:way:41020272"]["notice_board_m"])
        for pid in ("place_kaufhaus", "poi:osm:node:1794647095"):
            kinds = [f["kind"] for f in by_place[pid]["furniture"]]
            self.assertGreaterEqual(sum(1 for k in kinds if "shelf" in k or k == "gondola"), 4)

    def test_interior_meshes_have_collision_and_glass_is_double_sided(self):
        meshes = self.pkg["meshes"]
        for name in ("InteriorFloor", "InteriorWalls", "InteriorCeiling", "InteriorFurniture", "WindowGlassClear"):
            self.assertIn(name, meshes)
            self.assertTrue(meshes[name]["collision"], name)
        glass = meshes["WindowGlassClear"]
        self.assertEqual(len(glass["triangles"]) % 4, 0, "every pane needs a front and a back face")

    def test_inner_and_outer_walls_share_window_openings(self):
        for entry in self.pkg["interiors"]:
            windows = [o for o in entry["openings"] if o["kind"] == "window"]
            self.assertGreaterEqual(len(windows), 3, f"{entry['id']} should look out through ground floor windows")
            for o in windows:
                self.assertGreater(o["z0_m"], entry["floor_z_m"])
                self.assertLess(o["z1_m"], entry["ceiling_z_m"])

    # --- Reproducibility ----------------------------------------------------------------------------
    def test_offline_build_byte_identical_with_interiors(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        streets = _load("doemitz-altstadt-streets.json")
        args = dict(
            landmarks_config=_load("doemitz-altstadt-landmarks.json"),
            references_manifest=_load("doemitz-altstadt-references.json"),
            interiors_config=self.interiors_cfg,
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for mode in ("flat", "dgm1"):
                out = root / mode
                build_geo(config, RAW_DIR, out, terrain_mode=mode)
                packages = []
                for _ in range(2):
                    pkg = build_meshes(
                        json.loads((out / "scene.json").read_text(encoding="utf-8")),
                        json.loads((out / "import-report.json").read_text(encoding="utf-8")),
                        streets.get("sidewalk_widths_m"), streets.get("vehicle"),
                        _load("doemitz-altstadt-citizens.json"), streets.get("default_sidewalk_widths_m"),
                        streets.get("traffic_network"), _load("doemitz-altstadt-economy.json"),
                        _load("doemitz-altstadt-tasks.json"), scene_dir=out, **args,
                    )
                    packages.append(json.dumps(pkg, sort_keys=True))
                self.assertEqual(packages[0], packages[1], f"not deterministic in {mode} mode")
                self.assertEqual(len(json.loads(packages[0])["interiors"]), 3)


if __name__ == "__main__":
    unittest.main()
