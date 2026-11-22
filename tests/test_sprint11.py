import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from shapely.geometry import Point, Polygon, box, shape

from tools.geo_import.export import build as geo_build, write_json
from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.__main__ import CURB_HEIGHT_M, ROAD_ELEVATION_M, build as mesh_build, road_width
from tools.mesh_generator.road_elevation import RoadElevationNetwork


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data/manifests/doemitz-altstadt.json"
LICENSE_PATH = ROOT / "data/manifests/doemitz-altstadt-dgm-license.json"
RAW_DIR = ROOT / "data/raw/doemitz-altstadt"
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"


def _interpolate_mesh_z_at_xy(meshes: dict, east_m: float, north_m: float) -> float | None:
    """Find the terrain tile triangle containing (east_m, north_m) and return its exact interpolated Z."""
    for name, mesh in meshes.items():
        if not name.startswith("Terrain"):
            continue
        verts = mesh["vertices"]
        tris = mesh["triangles"]
        for i0, i1, i2 in tris:
            x0, y0, z0 = verts[i0]
            x1, y1, z1 = verts[i1]
            x2, y2, z2 = verts[i2]
            if east_m < min(x0, x1, x2) - 1e-4 or east_m > max(x0, x1, x2) + 1e-4:
                continue
            if north_m < min(y0, y1, y2) - 1e-4 or north_m > max(y0, y1, y2) + 1e-4:
                continue
            det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(det) < 1e-9:
                continue
            l0 = ((y1 - y2) * (east_m - x2) + (x2 - x1) * (north_m - y2)) / det
            l1 = ((y2 - y0) * (east_m - x2) + (x0 - x2) * (north_m - y2)) / det
            l2 = 1.0 - l0 - l1
            if l0 >= -1e-5 and l1 >= -1e-5 and l2 >= -1e-5:
                return l0 * z0 + l1 * z1 + l2 * z2
    return None


class Sprint11TerrainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.license_manifest = json.loads(LICENSE_PATH.read_text(encoding="utf-8"))
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.report = json.loads((PROCESSED_DIR / "import-report.json").read_text(encoding="utf-8"))
        cls.package = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))
        cls.elevation = ElevationModel.from_scene(cls.scene, PROCESSED_DIR)

    def test_license_manifest_and_import_report_metadata(self):
        # Exactly one license (no ambiguity with Datenlizenz Deutschland)
        self.assertEqual(self.license_manifest["status"], "imported")
        self.assertEqual(self.license_manifest["license_id"], "cc-by/4.0")
        self.assertNotIn("Datenlizenz", self.license_manifest["license"])
        self.assertIn("CC BY 4.0", self.license_manifest["license"])
        self.assertRegex(self.license_manifest["attribution_required"], r"^© GeoBasis-DE/M-V 20\d\d$")

        self.assertEqual(self.scene["terrain"]["kind"], "dgm1")
        self.assertEqual(self.report["terrain_mode"], "dgm1")
        dgm_files = self.report.get("dgm_raw_files") or []
        self.assertGreaterEqual(len(dgm_files), 1)
        for item in dgm_files:
            self.assertTrue(item["url"].startswith("https://"))
            self.assertTrue(item["tile_name"].endswith("_xyz.zip"))
            self.assertIsInstance(item["delivery_year"], int)
            self.assertEqual(len(item["sha256"]), 64)

    def test_terrain_mesh_budget_and_three_known_points_within_5cm(self):
        tm = self.package["terrain"]["mesh"]
        self.assertEqual(tm["kind"], "dgm1")
        self.assertGreater(tm["tile_count"], 1)
        # Budget from the versioned manifest (Sprint 13: 155.000, wall-line clipping along the fortress escarp)
        self.assertLessEqual(tm["triangle_count"], tm["max_triangles_budget"])
        self.assertLessEqual(tm["max_triangles_budget"], 155000)
        self.assertLessEqual(tm["max_vertical_error_m"], 0.05)

        # Three known open-ground points across Dömitz Altstadt:
        # 1. Rathausplatz (open ground just north-west of Rathaus)
        # 2. Festungswall (bastion rampart crest)
        # 3. Elbufer (lowland bank in the south-west)
        known_points = {
            "Rathausplatz": (-75.0, -223.0),
            "Festungswall": (-244.0, 40.0),
            "Elbufer": (-380.0, -320.0),
        }
        heights = {}
        for label, (east_m, north_m) in known_points.items():
            dgm_z = self.elevation.sample(east_m, north_m)
            mesh_z = _interpolate_mesh_z_at_xy(self.package["meshes"], east_m, north_m)
            self.assertIsNotNone(mesh_z, f"No terrain triangle found at {label} ({east_m}, {north_m})")
            self.assertLessEqual(
                abs(mesh_z - dgm_z),
                0.05,
                f"{label}: mesh_z={mesh_z:.4f} m vs dgm_z={dgm_z:.4f} m exceeds +-5 cm",
            )
            heights[label] = mesh_z

        # Topographic sanity: Elbufer < Rathausplatz < Festungswall
        self.assertLess(heights["Elbufer"], heights["Rathausplatz"])
        self.assertLess(heights["Rathausplatz"], heights["Festungswall"])
        self.assertGreater(heights["Festungswall"] - heights["Elbufer"], 6.0)

    def test_curb_height_is_12cm_plus_minus_1cm_everywhere(self):
        roads = self.scene["layers"]["roads"]
        smoothing_window_m = float(
            (self.scene["terrain"].get("assumptions") or {}).get("road_smoothing_window_m", 12.0)
        )
        road_net = RoadElevationNetwork(
            self.elevation, roads, road_width, ROAD_ELEVATION_M, CURB_HEIGHT_M,
            smoothing_window_m=smoothing_window_m,
        )
        sw_mesh = self.package["meshes"]["Sidewalks"]
        # Top sidewalk vertices are stored via Mesh.add_surface (vertex index lookup before add_draped_walls).
        # Every top-surface triangle has all 3 vertices at sidewalk_surface_z; check every top-face vertex.
        verts = sw_mesh["vertices"]
        checked = 0
        for i0, i1, i2 in sw_mesh["triangles"]:
            v0, v1, v2 = verts[i0], verts[i1], verts[i2]
            # Top sidewalk faces have positive 2D projected area; vertical curb wall faces have ~0 2D area
            area2 = abs((v1[0] - v0[0]) * (v2[1] - v0[1]) - (v1[1] - v0[1]) * (v2[0] - v0[0]))
            if area2 < 1e-6:
                continue
            for vx, vy, vz in (v0, v1, v2):
                road_z = road_net.road_surface_z(vx, vy)
                curb = vz - road_z
                self.assertAlmostEqual(
                    curb,
                    0.12,
                    delta=0.01,
                    msg=f"Curb height {curb:.4f} m at ({vx:.2f}, {vy:.2f}) outside 12 cm +-1 cm",
                )
                checked += 1
        self.assertGreater(checked, 1000)

    def test_no_building_plinth_floats_above_terrain(self):
        # Every building's walls must start at <= lowest terrain elevation under its footprint.
        for feature in self.scene["layers"]["buildings"]:
            geom = shape(feature["geometry"])
            polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
            b_min_z = min(self.elevation.polygon_min_max(p)[0] for p in polys)
            b_max_z = max(self.elevation.polygon_min_max(p)[1] for p in polys)
            # Check all exterior vertices against b_min_z
            for p in polys:
                for x, y in p.exterior.coords:
                    tz = self.elevation.sample(x, y)
                    self.assertLessEqual(
                        b_min_z,
                        tz + 0.005,
                        f"Building {feature['id']} base {b_min_z:.4f} floats above corner terrain {tz:.4f}",
                    )
            self.assertGreaterEqual(b_max_z, b_min_z)

        # Also check actual exported vertical wall edges never float above local terrain at their XY.
        # Sprint 13: wall strips above door/window openings start higher, so the lowest wall vertex per XY counts.
        lowest_by_xy = {}
        for mesh_name, mesh in self.package["meshes"].items():
            if not mesh_name.startswith("Walls"):
                continue
            verts = mesh["vertices"]
            for i0, i1, i2 in mesh["triangles"]:
                tri = (verts[i0], verts[i1], verts[i2])
                # Vertical wall triangles have two vertices sharing (x, y) with different Z (bottom vs eave)
                for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[0], tri[2])):
                    if abs(a[0] - b[0]) < 1e-4 and abs(a[1] - b[1]) < 1e-4 and abs(a[2] - b[2]) > 0.5:
                        key = (round(a[0], 3), round(a[1], 3))
                        lowest_by_xy[key] = min(lowest_by_xy.get(key, 1e9), a[2], b[2])
        for (x, y), z_bot in lowest_by_xy.items():
            self.assertLessEqual(z_bot, self.elevation.sample(x, y) + 0.02)
        self.assertGreater(len(lowest_by_xy), 1000)

    def test_road_slopes_and_water_levels_in_report(self):
        re_info = self.package["terrain"]["roads_elevation"]
        self.assertGreaterEqual(re_info["smoothing_window_m"], 10.0)
        self.assertGreater(re_info["road_count"], 100)
        self.assertGreater(re_info["max_slope_overall_percent"], 0.0)
        for entry in re_info["roads"]:
            self.assertIn("max_slope_percent", entry)
            self.assertGreaterEqual(entry["max_slope_percent"], 0.0)

        water_levels = self.package["terrain"]["water_levels"]
        self.assertEqual(len(water_levels), len(self.scene["layers"]["water"]))
        for w in water_levels:
            self.assertLess(
                w["water_level_m"],
                w["bank_min_m"],
                f"Waterbody {w['id']} level {w['water_level_m']} not strictly below bank_min {w['bank_min_m']}",
            )
            self.assertTrue(w["source"].startswith("assumed_"))

    def test_city_map_hillshading_and_geobasis_attribution(self):
        cm = self.package["city_map"]
        self.assertTrue(cm["hillshading"])
        self.assertIn("OpenStreetMap", cm["attribution"])
        self.assertIn("© GeoBasis-DE/M-V", cm["attribution"])
        self.assertIn("© GeoBasis-DE/M-V", self.package["terrain_attribution"])

    def test_offline_build_byte_identical_in_flat_and_dgm1_modes(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 1. Flat mode byte-identity (geo_import + mesh_generator)
            flat_a = tmp_path / "flat_a"
            flat_b = tmp_path / "flat_b"
            geo_build(self.config, RAW_DIR, flat_a, terrain_mode="flat")
            geo_build(self.config, RAW_DIR, flat_b, terrain_mode="flat")
            self.assertEqual((flat_a / "scene.json").read_bytes(), (flat_b / "scene.json").read_bytes())
            self.assertEqual((flat_a / "import-report.json").read_bytes(), (flat_b / "import-report.json").read_bytes())

            scene_a = json.loads((flat_a / "scene.json").read_text(encoding="utf-8"))
            report_a = json.loads((flat_a / "import-report.json").read_text(encoding="utf-8"))
            self.assertEqual(scene_a["terrain"]["kind"], "flat_placeholder")
            pkg_flat_1 = mesh_build(scene_a, report_a, map_output_png=flat_a / "map.png", scene_dir=flat_a)
            pkg_flat_2 = mesh_build(scene_a, report_a, map_output_png=flat_b / "map.png", scene_dir=flat_b)
            write_json(flat_a / "pkg.json", pkg_flat_1)
            write_json(flat_b / "pkg.json", pkg_flat_2)
            self.assertEqual((flat_a / "pkg.json").read_bytes(), (flat_b / "pkg.json").read_bytes())
            self.assertEqual((flat_a / "map.png").read_bytes(), (flat_b / "map.png").read_bytes())

            # 2. DGM1 mode byte-identity (geo_import grid + scene + deterministic TIN on synthetic slope)
            dgm_a = tmp_path / "dgm_a"
            dgm_b = tmp_path / "dgm_b"
            geo_build(self.config, RAW_DIR, dgm_a, terrain_mode="dgm1")
            geo_build(self.config, RAW_DIR, dgm_b, terrain_mode="dgm1")
            self.assertEqual((dgm_a / "scene.json").read_bytes(), (dgm_b / "scene.json").read_bytes())
            self.assertEqual((dgm_a / "terrain-grid.bin").read_bytes(), (dgm_b / "terrain-grid.bin").read_bytes())
            self.assertEqual((dgm_a / "scene.json").read_bytes(), (PROCESSED_DIR / "scene.json").read_bytes())
            self.assertEqual((dgm_a / "terrain-grid.bin").read_bytes(), (PROCESSED_DIR / "terrain-grid.bin").read_bytes())


if __name__ == "__main__":
    unittest.main()
