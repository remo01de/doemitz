"""Sprint 16: World Partition HLOD & 450 m streaming, procedural horizon skirt & fog,
async SaveGame streaming, 2 walk-in harbour interiors (Hotel & Restaurant),
harbour jobs & tasks, 45 citizens, 12 vehicles, ECVF_SetByCode, and lower lock gate sliver fix."""

import json
from pathlib import Path
import unittest

from shapely.geometry import Point, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"
CPP_ROOT = ROOT / "unreal/DoemitzLivingCity/Source/DoemitzLivingCity"
IMPORT_PY = ROOT / "unreal/DoemitzLivingCity/Content/Python/import_altstadt.py"

HOTEL_PLACE_ID = "poi:osm:node:387219809"
RESTAURANT_PLACE_ID = "poi:osm:node:1125977013"
HOTEL_BUILDING_ID = "osm:way:1355844634"
RESTAURANT_BUILDING_ID = "osm:way:1355844633"


class Sprint16Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.pkg = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))

    def test_m1_streaming_450m_and_hlod_metadata(self):
        cells = self.pkg["cells"]
        self.assertEqual(cells["cell_size_m"], 256.0)
        self.assertEqual(cells["loading_range_m"], 450.0)
        self.assertTrue(cells.get("hlod_enabled"))
        self.assertEqual(cells.get("hlod_cell_size_m"), 512.0)
        self.assertGreaterEqual(cells.get("hlod_loading_range_m", 0.0), 1400.0)

    def test_m2_horizon_skirt_mesh_and_report(self):
        skirt_rep = self.pkg["terrain"]["mesh"].get("horizon_skirt")
        self.assertIsNotNone(skirt_rep, "terrain.mesh must document horizon_skirt")
        self.assertGreaterEqual(skirt_rep["width_m"], 2000.0)
        self.assertEqual(skirt_rep["source"], "assumed_sprint16_horizon_skirt")
        self.assertIn("TerrainHorizonSkirt", self.pkg["meshes"])
        skirt = self.pkg["meshes"]["TerrainHorizonSkirt"]
        self.assertFalse(skirt["collision"], "horizon skirt must be non-colliding")
        self.assertEqual(skirt["material"], "Terrain")
        self.assertGreaterEqual(len(skirt["triangles"]), 200)
        # All skirt vertices must lie on or outside the playable bounds (never inside the city interior)
        min_e, min_n, max_e, max_n = self.pkg["bounds_m"]
        inner_box = Polygon([
            (min_e + 0.5, min_n + 0.5),
            (max_e - 0.5, min_n + 0.5),
            (max_e - 0.5, max_n - 0.5),
            (min_e + 0.5, max_n - 0.5),
        ])
        for vx, vy, _vz in skirt["vertices"]:
            self.assertFalse(inner_box.contains(Point(vx, vy)), f"horizon skirt vertex ({vx}, {vy}) inside bounds")

    def test_m3_five_walkin_interiors_including_hotel_and_restaurant(self):
        interiors = {e["id"]: e for e in self.pkg["interiors"]}
        self.assertEqual(len(interiors), 5)
        for iid, pid, bid in (
            ("interior:hotel_doemitzer_hafen", HOTEL_PLACE_ID, HOTEL_BUILDING_ID),
            ("interior:hafen_restaurant", RESTAURANT_PLACE_ID, RESTAURANT_BUILDING_ID),
        ):
            self.assertIn(iid, interiors)
            entry = interiors[iid]
            self.assertEqual(entry["place_id"], pid)
            self.assertEqual(entry["building_id"], bid)
            self.assertTrue(entry["walkable_from_door"])
            self.assertGreaterEqual(entry["ceiling_z_m"] - entry["floor_z_m"], 2.8)
            self.assertGreaterEqual(len(entry["furniture"]), 6)
            self.assertGreaterEqual(len(entry["lights_m"]), 4)
            self.assertIsNotNone(entry["counter_m"])
            wins = [o for o in entry["openings"] if o["kind"] == "window"]
            self.assertGreaterEqual(len(wins), 5)

    def test_m3_harbour_jobs_tasks_45_citizens_and_12_vehicles(self):
        # 45 citizens, 0 disconnected routes, active workers in harbour hotel & restaurant
        cit = self.pkg["citizens"]
        self.assertEqual(len(cit["citizens"]), 45)
        self.assertEqual(cit["disconnected_route_count"], 0)
        names = [c["name"] for c in cit["citizens"]]
        self.assertGreaterEqual(len(set(names)), 40)
        hotel_workers = [c["id"] for c in cit["citizens"] if c["work_place_id"] == HOTEL_PLACE_ID]
        rest_workers = [c["id"] for c in cit["citizens"] if c["work_place_id"] == RESTAURANT_PLACE_ID]
        self.assertGreaterEqual(len(hotel_workers), 2, "Hotel Dömitzer Hafen needs at least 2 workers")
        self.assertGreaterEqual(len(rest_workers), 2, "Dömitzer Hafen Restaurant needs at least 2 workers")

        # 12 vehicles including harbour spawn edges (east > 500 m)
        vehicles = self.pkg["traffic_network"]["vehicles"]
        self.assertEqual(len(vehicles), 12)
        edges_by_id = {e["id"]: e for e in self.pkg["road-graph"]["edges"]}
        harbour_vehicles = 0
        for v in vehicles:
            edge = edges_by_id[v["start_edge_id"]]
            self.assertFalse(edge["dead_end"])
            if max(p[0] for p in edge["points_m"]) > 500.0:
                harbour_vehicles += 1
        self.assertGreaterEqual(harbour_vehicles, 3, "At least 3 vehicles should spawn in the eastern/harbour district")

        # Harbour jobs & tasks
        jobs_by_id = {j["id"]: j for j in self.pkg["economy"]["jobs"]}
        self.assertIn("job_hafenhotel_rezeption", jobs_by_id)
        self.assertIn("job_hafenrestaurant_service", jobs_by_id)
        self.assertEqual(jobs_by_id["job_hafenhotel_rezeption"]["place_id"], HOTEL_PLACE_ID)
        self.assertEqual(jobs_by_id["job_hafenrestaurant_service"]["place_id"], RESTAURANT_PLACE_ID)

        tasks_by_id = {t["id"]: t for t in self.pkg["tasks"]["templates"]}
        for tid in (
            "task_tpl_errand_hafenrestaurant_hotel",
            "task_tpl_errand_touristeninfo_hafenhotel",
            "task_tpl_errand_apotheke_hafenrestaurant",
            "task_tpl_fetch_fischbroetchen_hafen",
            "task_tpl_fetch_hafenfuehrer",
        ):
            self.assertIn(tid, tasks_by_id)

    def test_m4_lock_lower_gate_east_corner_sliver_removed(self):
        # Previously a terrain triangle at (754.1, -306.97) poked out at z=-0.63 m right beside the lower gate water line.
        # Verify no terrain triangle whose centroid lies inside the water near the east lower gate rises above water (-1.20 m).
        waters = [shape(w["geometry"]).buffer(-0.08) for w in self.scene["layers"]["water"]]
        for mname, mdata in self.pkg["meshes"].items():
            if not mname.startswith("Terrain_"):
                continue
            verts = mdata["vertices"]
            for tri in mdata["triangles"]:
                pts = [verts[i] for i in tri]
                cx = sum(p[0] for p in pts) / 3.0
                cy = sum(p[1] for p in pts) / 3.0
                if 750.0 <= cx <= 760.0 and -312.0 <= cy <= -300.0:
                    if any(w.contains(Point(cx, cy)) for w in waters):
                        self.assertLessEqual(
                            max(p[2] for p in pts),
                            -1.20,
                            f"Lower lock gate water-side terrain sliver in {mname} at ({cx:.2f}, {cy:.2f}), z={[round(p[2], 2) for p in pts]}",
                        )

    def test_m2_and_m4_cpp_guards(self):
        gfx_cpp = (CPP_ROOT / "Private/Settings/DoemitzGraphicsSettings.cpp").read_text(encoding="utf-8")
        self.assertIn("ECVF_SetByCode", gfx_cpp)
        self.assertNotIn("ECVF_SetByGameSetting", gfx_cpp)

        save_h = (CPP_ROOT / "Public/Simulation/DoemitzSaveSubsystem.h").read_text(encoding="utf-8")
        save_cpp = (CPP_ROOT / "Private/Simulation/DoemitzSaveSubsystem.cpp").read_text(encoding="utf-8")
        self.assertIn("UTickableWorldSubsystem", save_h)
        self.assertIn("IsPendingStreamingRestore", save_h)
        self.assertIn("IsStreamingCompleted", save_cpp)

        world_h = (CPP_ROOT / "Public/World/DoemitzWorldTools.h").read_text(encoding="utf-8")
        self.assertIn("ConfigureHLODSetup", world_h)
        self.assertIn("GetStreamingActorCounts", world_h)

        dn_h = (CPP_ROOT / "Public/World/DoemitzDayNightController.h").read_text(encoding="utf-8")
        self.assertIn("AExponentialHeightFog", dn_h)


if __name__ == "__main__":
    unittest.main()
