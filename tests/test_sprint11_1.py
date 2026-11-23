"""Unit tests for Sprint 11.1: bridges on their own linear elevation, SM_Bridges, clearance, and prop exclusion."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from shapely.geometry import LineString, Point, shape

from tools.geo_import.export import build as geo_build, write_json
from tools.geo_transform.terrain import ElevationModel
from tools.mesh_generator.__main__ import CURB_HEIGHT_M, ROAD_ELEVATION_M, build as mesh_build, road_width
from tools.mesh_generator.bridges import BRIDGE_DECK_THICKNESS_M
from tools.mesh_generator.road_elevation import RoadElevationNetwork, is_bridge_road


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data/manifests/doemitz-altstadt.json"
RAW_DIR = ROOT / "data/raw/doemitz-altstadt"
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"


class Sprint11_1BridgesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.report = json.loads((PROCESSED_DIR / "import-report.json").read_text(encoding="utf-8"))
        cls.package = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))
        cls.elevation = ElevationModel.from_scene(cls.scene, PROCESSED_DIR)
        assumptions = cls.scene["terrain"].get("assumptions") or {}
        cls.road_net = RoadElevationNetwork(
            cls.elevation,
            cls.scene["layers"]["roads"],
            road_width,
            ROAD_ELEVATION_M,
            CURB_HEIGHT_M,
            smoothing_window_m=float(assumptions.get("road_smoothing_window_m", 12.0)),
            # Sprint 13: rebuild with the same walk-in tunnels as the package (they fix the drawbridge abutment)
            built_tunnel_ids=set(
                (json.loads((ROOT / "data/manifests/doemitz-altstadt-landmarks.json").read_text(encoding="utf-8"))
                 .get("tunnel_portals") or {})
            ),
        )

    def test_bridge_chains_detected_with_two_abutments_and_osm_tags(self):
        bridges = self.package.get("bridges") or []
        # Altstadt: 6 OSM bridge ways form 5 connected bridge chains (120431984 + 120431986 combine into 1 chain);
        # Sprint 14 adds 4 bridges in the harbour/lock extension
        self.assertEqual(len(bridges), 9)
        ids = {b["id"] for b in bridges}
        self.assertIn("bridge:osm:way:94526517", ids)   # Steinbrücke
        self.assertIn("bridge:osm:way:29732766", ids)   # Torbrücke
        self.assertIn("bridge:osm:way:29732751", ids)   # Fläutendörper Steg
        self.assertIn("bridge:osm:way:120431984", ids)  # Festungsbrücke + Zugbrücke
        self.assertIn("bridge:osm:way:120432334", ids)  # NW-Holzsteg

        for b in bridges:
            self.assertEqual(len(b["abutments"]), 2, f"{b['id']} must have exactly 2 abutments")
            self.assertEqual(b["deck_thickness_m"], 0.50)
            self.assertEqual(b["parapet_height_m"], 1.00)
            self.assertIn(b["material"], {"stone", "wood"})
            self.assertTrue(b["material_source"])
            for ab in b["abutments"]:
                self.assertTrue(ab["source"])

        # Check combined Festungsbrücke chain contains both ways
        fest_bridge = next(b for b in bridges if b["id"] == "bridge:osm:way:120431984")
        self.assertEqual(set(fest_bridge["way_ids"]), {"osm:way:120431984", "osm:way:120431986"})
        self.assertEqual(fest_bridge["material"], "wood")

        # Verify extra OSM bridge tags were exported into scene.json
        roads_by_id = {r["id"]: r["properties"] for r in self.scene["layers"]["roads"]}
        self.assertEqual(roads_by_id["osm:way:120431986"].get("material"), "wood")
        self.assertEqual(roads_by_id["osm:way:120432334"].get("bridge:structure"), "beam")

        # Verify SM_Bridges mesh exists with collision and vertex colors
        self.assertIn("Bridges", self.package["meshes"])
        bmesh = self.package["meshes"]["Bridges"]
        self.assertTrue(bmesh["collision"])
        self.assertGreater(len(bmesh["triangles"]), 100)
        self.assertEqual(len(bmesh["vertex_colors"]), len(bmesh["vertices"]))

    def test_bridge_roadway_vertices_are_linear_between_abutments_within_2cm(self):
        # Check every bridge chain's sampled profile and every road-graph edge point on a bridge
        bridges_by_way = {}
        for chain in self.road_net.bridges:
            ab_a, ab_b = chain.abutments
            z_lo = min(ab_a.ground_z_m, ab_b.ground_z_m) + ROAD_ELEVATION_M
            z_hi = max(ab_a.ground_z_m, ab_b.ground_z_m) + ROAD_ELEVATION_M
            for wid in chain.way_ids:
                bridges_by_way[wid] = (chain, z_lo, z_hi)
            # Check all chain profile samples
            for s, z in zip(chain.s_vals, chain.z_vals):
                z_surf = float(z) + ROAD_ELEVATION_M
                expected = (ab_a.ground_z_m + (float(s) / chain.length_m) * (ab_b.ground_z_m - ab_a.ground_z_m)) + ROAD_ELEVATION_M
                self.assertLessEqual(abs(z_surf - expected), 0.02, f"{chain.id} deviates from linear profile")
                self.assertGreaterEqual(z_surf, z_lo - 0.02)
                self.assertLessEqual(z_surf, z_hi + 0.02)

        # Check all drivable road-graph bridge edges
        checked_edges = 0
        for edge in self.package["road-graph"]["edges"]:
            if edge["way_id"] not in bridges_by_way:
                continue
            self.assertTrue(edge["is_bridge"])
            chain, z_lo, z_hi = bridges_by_way[edge["way_id"]]
            for pt in edge["points_m"]:
                self.assertGreaterEqual(pt[2], z_lo - 0.02, f"Bridge edge {edge['id']} dips below abutment range")
                self.assertLessEqual(pt[2], z_hi + 0.02, f"Bridge edge {edge['id']} exceeds abutment range")
            checked_edges += 1
        self.assertGreaterEqual(checked_edges, 4)

    def test_deck_underside_at_least_50cm_above_water_level(self):
        bridges_by_id = {b["id"]: b for b in self.package["bridges"]}
        for required_id in (
            "bridge:osm:way:94526517",   # Steinbrücke
            "bridge:osm:way:29732766",   # Torbrücke
            "bridge:osm:way:29732751",   # Fläutendörper Steg
            "bridge:osm:way:120431984",  # Festungsbrücke
            "bridge:osm:way:120432334",  # NW-Holzsteg
        ):
            b = bridges_by_id[required_id]
            self.assertIsNotNone(b["clearance_over_water_m"], f"{required_id} missing water clearance")
            self.assertGreaterEqual(
                b["clearance_over_water_m"],
                0.50,
                f"{required_id} clearance {b['clearance_over_water_m']} m < 0.50 m",
            )

    def test_no_prop_under_bridge_footprint(self):
        bridge_polys = []
        for chain in self.road_net.bridges:
            line = LineString(chain.coords)
            # Match bridge total deck width (road + optional 1.6 m sidewalk on primary)
            sw = 1.6 if chain.highway == "primary" else 0.0
            bridge_polys.append(line.buffer(chain.width_m * 0.5 + sw, quad_segs=2, cap_style="flat"))

        instances = self.package["props"]["instances"]
        for category in ("street_lamps", "benches", "planters", "bollards", "trees", "bushes"):
            for entry in instances.get(category, []):
                pt = Point(entry[0], entry[1])
                for bpoly in bridge_polys:
                    self.assertFalse(
                        bpoly.contains(pt),
                        f"Prop {category} at ({entry[0]:.2f}, {entry[1]:.2f}) lies under/on bridge footprint",
                    )

    def test_road_to_bridge_transition_has_no_step_over_2cm(self):
        for chain in self.road_net.bridges:
            for ab_idx, ab in enumerate(chain.abutments):
                ax, ay = ab.position_xy
                bridge_way_id = chain.way_ids[0] if ab_idx == 0 else chain.way_ids[-1]
                z_bridge = self.road_net.road_surface_z(ax, ay, road_id=bridge_way_id)
                for conn_rid in ab.connected_road_ids:
                    z_road = self.road_net.road_surface_z(ax, ay, road_id=conn_rid)
                    self.assertLessEqual(
                        abs(z_road - z_bridge),
                        0.02,
                        f"Step > 2 cm at {chain.id} <-> {conn_rid}: road={z_road:.4f} vs bridge={z_bridge:.4f}",
                    )

    def test_offline_build_byte_identical_with_bridges_in_flat_and_dgm1(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fa, fb = tmp_path / "flat_a", tmp_path / "flat_b"
            geo_build(self.config, RAW_DIR, fa, terrain_mode="flat")
            geo_build(self.config, RAW_DIR, fb, terrain_mode="flat")
            self.assertEqual((fa / "scene.json").read_bytes(), (fb / "scene.json").read_bytes())
            sa = json.loads((fa / "scene.json").read_text(encoding="utf-8"))
            ra = json.loads((fa / "import-report.json").read_text(encoding="utf-8"))
            p1 = mesh_build(sa, ra, scene_dir=fa)
            p2 = mesh_build(sa, ra, scene_dir=fb)
            self.assertEqual(len(p1["bridges"]), 9)
            write_json(fa / "p.json", p1)
            write_json(fb / "p.json", p2)
            self.assertEqual((fa / "p.json").read_bytes(), (fb / "p.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
