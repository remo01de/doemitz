import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.geo_import.export import build as build_geo
from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.__main__ import build as build_meshes
from tools.mesh_generator.__main__ import road_width
from tools.mesh_generator.road_elevation import RoadElevationNetwork


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/manifests/doemitz-altstadt.json"
LOD2_LICENSE = ROOT / "data/manifests/doemitz-altstadt-lod2-license.json"
LANDMARKS_MANIFEST = ROOT / "data/manifests/doemitz-altstadt-landmarks.json"
REFERENCES_MANIFEST = ROOT / "data/manifests/doemitz-altstadt-references.json"
STREETS_MANIFEST = ROOT / "data/manifests/doemitz-altstadt-streets.json"
CITIZENS_MANIFEST = ROOT / "data/manifests/doemitz-altstadt-citizens.json"
ECONOMY_MANIFEST = ROOT / "data/manifests/doemitz-altstadt-economy.json"
TASKS_MANIFEST = ROOT / "data/manifests/doemitz-altstadt-tasks.json"
RAW_DIR = ROOT / "data/raw/doemitz-altstadt"
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"


class Sprint12Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.report = json.loads((PROCESSED_DIR / "import-report.json").read_text(encoding="utf-8"))
        cls.pkg = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))
        cls.landmarks_cfg = json.loads(LANDMARKS_MANIFEST.read_text(encoding="utf-8"))
        cls.refs_cfg = json.loads(REFERENCES_MANIFEST.read_text(encoding="utf-8"))

    def test_pedestrian_bridges_without_incline_max_6_percent_and_tunnel_abutment(self):
        bridges = self.pkg["bridges"]
        by_id = {b["id"]: b for b in bridges}
        self.assertIn("bridge:osm:way:120432334", by_id)

        nw = by_id["bridge:osm:way:120432334"]
        sources = [ab["source"] for ab in nw["abutments"]]
        self.assertIn("tunnel_portal_dgm", sources, f"NW-Steg must connect to tunnel portal: {nw['abutments']}")
        self.assertNotIn("assumed_max_dgm_3m_radius", sources)
        self.assertEqual(nw["warnings"], [])
        self.assertLessEqual(nw["max_slope_percent"], 6.0)

        # Every pedestrian bridge without OSM incline tag must have <= 6% longitudinal slope
        for b in bridges:
            if b["highway"] in {"path", "footway", "cycleway"} and not b.get("incline"):
                self.assertLessEqual(
                    b["max_slope_percent"],
                    6.0,
                    f"Pedestrian bridge {b['id']} ({b['name']}) exceeds 6% slope: {b['max_slope_percent']}%",
                )

    def test_disconnected_3m_fallback_warns_above_1m_delta(self):
        # Synthetic terrain with a 3 m cliff at one end of an unconnected bridge
        import numpy as np

        grid = np.zeros((20, 40), dtype=np.float32)
        grid[:, 25:] = 3.0
        elev = ElevationModel(
            kind="dgm1",
            reference_elevation_m=10.0,
            flat_elevation_m=0.0,
            grid=grid,
            origin_east_m=0.0,
            origin_north_m=0.0,
            spacing_m=1.0,
        )
        roads = [
            {
                "id": "osm:way:1001",
                "properties": {"highway": "path"},
                "geometry": {"type": "LineString", "coordinates": [[2.0, 10.0], [10.0, 10.0]]},
            },
            {
                "id": "osm:way:1002",
                "properties": {"highway": "path", "bridge": "yes"},
                "geometry": {"type": "LineString", "coordinates": [[10.0, 10.0], [26.0, 10.0]]},
            },
        ]
        net = RoadElevationNetwork(elev, roads, road_width, 0.08, 0.12)
        self.assertEqual(len(net.bridges), 1)
        br = net.bridges[0]
        self.assertEqual(br.abutments[1].source, "assumed_max_dgm_3m_radius")
        self.assertTrue(br.warnings, "Expected warning when 3m fallback sits > 1m above opposite abutment")

    def test_lod2_license_manifest_and_import_report_metadata(self):
        lic = json.loads(LOD2_LICENSE.read_text(encoding="utf-8"))
        self.assertEqual(lic["license_id"], "cc-by/4.0")
        self.assertEqual(lic["status"], "imported")
        self.assertIn("GeoBasis-DE/M-V", lic["attribution_required"])
        self.assertTrue(lic["atom_url"].startswith("https://"))

        lod2_rep = self.report.get("lod2")
        self.assertIsNotNone(lod2_rep)
        self.assertEqual(lod2_rep["license_id"], "cc-by/4.0")
        self.assertGreaterEqual(lod2_rep["matched_osm_buildings"], 550)
        lod2_files = self.report.get("lod2_raw_files") or []
        self.assertGreaterEqual(len(lod2_files), 1)
        for rf in lod2_files:
            self.assertEqual(len(rf["sha256"]), 64)
            self.assertTrue(rf["url"].startswith("https://"))
            self.assertGreaterEqual(int(rf["delivery_year"]), 2025)

    def test_lod2_matching_above_threshold_and_no_double_assignment(self):
        threshold = float(self.pkg["lod2"]["overlap_threshold"])
        items = self.pkg["buildings"]["items"]
        self.assertEqual(len(items), 645)

        seen_lod2_ids = set()
        valid_sources = {"lod2", "osm_height", "osm_levels", "reference_photo_estimate", "assumed_default"}
        matched_count = 0
        for item in items:
            self.assertIn(item["height_source"], valid_sources)
            if item["lod2_id"] is not None:
                matched_count += 1
                self.assertGreaterEqual(
                    item["lod2_overlap_ratio"],
                    threshold,
                    f"{item['id']} matched {item['lod2_id']} below threshold {threshold}",
                )
                self.assertNotIn(
                    item["lod2_id"],
                    seen_lod2_ids,
                    f"LoD2 building {item['lod2_id']} assigned more than once!",
                )
                seen_lod2_ids.add(item["lod2_id"])

        self.assertEqual(matched_count, self.pkg["buildings"]["lod2_matched"])
        self.assertGreaterEqual(matched_count, 550)

    def test_johanneskirche_tower_is_tallest_building_in_extract(self):
        items = self.pkg["buildings"]["items"]
        church = next(b for b in items if b["id"] == "osm:way:42551672")
        self.assertEqual(church["landmark_variant"], "johanneskirche")
        self.assertGreaterEqual(church["ridge_height_m"], 38.0)

        for other in items:
            if other["id"] == church["id"]:
                continue
            self.assertGreater(
                church["ridge_height_m"],
                other["ridge_height_m"],
                f"Church ({church['ridge_height_m']}m) must be taller than {other['id']} ({other['ridge_height_m']}m)",
            )
            self.assertGreater(
                church["top_z_m"],
                other["top_z_m"],
                f"Church top_z ({church['top_z_m']}m) must exceed {other['id']} ({other['top_z_m']}m)",
            )

    def test_landmarks_bridge_details_tunnel_portal_and_rathaus_entrance(self):
        lm = self.pkg["landmarks"]
        self.assertEqual(lm["building_count"], 9)
        self.assertEqual(lm["buildings"]["osm:way:42551672"], "johanneskirche")
        self.assertEqual(lm["buildings"]["osm:way:41020272"], "rathaus")
        for fid in ("osm:way:96029976", "osm:way:1360590722", "osm:way:96029971", "osm:way:1360590724", "osm:way:96029975", "osm:way:96029967"):
            self.assertIn(fid, lm["buildings"])

        self.assertEqual(lm["bridge_details"]["bridge:osm:way:29732766"], "stone_arches_piers")
        self.assertEqual(lm["bridge_details"]["bridge:osm:way:94526517"], "stone_vault_arch")

        # Verify Rathaus entrance is placed at the real front door on Rathausplatz
        rathaus_place = next(p for p in self.pkg["citizens"]["places"] if p["id"] == "poi:osm:way:41020272")
        ent = rathaus_place["entrance"]
        self.assertEqual(ent["source"], "landmark_reference_door")
        real_door = self.landmarks_cfg["buildings"]["osm:way:41020272"]["real_entrance_local_m"]
        dx = ent["position_m"][0] - real_door[0]
        dy = ent["position_m"][1] - real_door[1]
        self.assertLessEqual((dx * dx + dy * dy) ** 0.5, 1.5)

        # Verify NW-Steg tunnel portal matches NW-Steg eastern abutment with 0 cm step
        portals = self.pkg.get("tunnel_portals") or []
        nw_portal = next(p for p in portals if p["road_id"] == "osm:way:416256369")
        nw_bridge = next(b for b in self.pkg["bridges"] if b["id"] == "bridge:osm:way:120432334")
        east_ab = next(ab for ab in nw_bridge["abutments"] if ab["source"] == "tunnel_portal_dgm")
        self.assertAlmostEqual(nw_portal["entry_point_3d_m"][2], east_ab["position_m"][2], places=3)

    def test_references_manifest_has_url_author_and_license(self):
        refs = self.refs_cfg.get("references") or []
        self.assertGreaterEqual(len(refs), 6)
        seen_ids = set()
        for ref in refs:
            self.assertTrue(ref.get("id") and ref["id"] not in seen_ids)
            seen_ids.add(ref["id"])
            self.assertTrue(ref.get("url", "").startswith("https://"), f"Missing URL in {ref}")
            self.assertTrue(bool(ref.get("author", "").strip()), f"Missing author in {ref}")
            self.assertTrue(bool(ref.get("license", "").strip()), f"Missing license in {ref}")
            self.assertTrue(ref.get("license_url", "").startswith("http"), f"Missing license_url in {ref}")
            self.assertTrue(bool(ref.get("landmark", "").strip()), f"Missing landmark in {ref}")
            self.assertTrue(isinstance(ref.get("osm_ids"), list) and len(ref["osm_ids"]) >= 1)

    def test_offline_build_byte_identical_with_lod2_and_landmarks(self):
        streets = json.loads(STREETS_MANIFEST.read_text(encoding="utf-8"))
        citizens = json.loads(CITIZENS_MANIFEST.read_text(encoding="utf-8"))
        economy = json.loads(ECONOMY_MANIFEST.read_text(encoding="utf-8"))
        tasks = json.loads(TASKS_MANIFEST.read_text(encoding="utf-8"))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for mode in ("flat", "dgm1"):
                out_a = root / f"{mode}_a"
                out_b = root / f"{mode}_b"
                build_geo(self.config, RAW_DIR, out_a, terrain_mode=mode)
                build_geo(self.config, RAW_DIR, out_b, terrain_mode=mode)
                self.assertEqual((out_a / "scene.json").read_bytes(), (out_b / "scene.json").read_bytes())

                pkg_a = build_meshes(
                    json.loads((out_a / "scene.json").read_text(encoding="utf-8")),
                    json.loads((out_a / "import-report.json").read_text(encoding="utf-8")),
                    streets.get("sidewalk_widths_m"),
                    streets.get("vehicle"),
                    citizens,
                    streets.get("default_sidewalk_widths_m"),
                    streets.get("traffic_network"),
                    economy,
                    tasks,
                    scene_dir=out_a,
                    landmarks_config=self.landmarks_cfg,
                    references_manifest=self.refs_cfg,
                )
                pkg_b = build_meshes(
                    json.loads((out_b / "scene.json").read_text(encoding="utf-8")),
                    json.loads((out_b / "import-report.json").read_text(encoding="utf-8")),
                    streets.get("sidewalk_widths_m"),
                    streets.get("vehicle"),
                    citizens,
                    streets.get("default_sidewalk_widths_m"),
                    streets.get("traffic_network"),
                    economy,
                    tasks,
                    scene_dir=out_b,
                    landmarks_config=self.landmarks_cfg,
                    references_manifest=self.refs_cfg,
                )
                self.assertEqual(
                    json.dumps(pkg_a, sort_keys=True),
                    json.dumps(pkg_b, sort_keys=True),
                    f"Mesh build not deterministic in {mode} mode",
                )


if __name__ == "__main__":
    unittest.main()
