"""Sprint 13.1: blocking street props and the fortress gate after the reference photos (gatehouse, loophole
parapet, timber bridges, Sandsteintor in the plane of the gate wall)."""

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"
PROP_MESHES = ROOT / "unreal/DoemitzLivingCity/Content/Python/doemitz_prop_meshes.py"
GATE_TUNNEL = "osm:way:120431987"
GATE_WALL = "osm:way:416256360"


def _prop_module():
    spec = importlib.util.spec_from_file_location("doemitz_prop_meshes", PROP_MESHES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PropCollisionTest(unittest.TestCase):
    def test_lamps_benches_bollards_planters_and_trunks_block_the_player(self):
        props = _prop_module()
        meshes = {
            "lamp": props.street_lamp_metal(), "bench": props.street_bench(), "bollard": props.street_bollard(),
            "planter": props.street_planter(), "tree0": props.stylized_tree(0), "tree2": props.stylized_tree(2),
        }
        for name, mesh in meshes.items():
            shapes = mesh.get("blocking_shapes") or []
            self.assertTrue(shapes, f"{name} needs a blocking collision shape")
            xs = [v[0] for v in mesh["vertices"]]
            ys = [v[1] for v in mesh["vertices"]]
            zs = [v[2] for v in mesh["vertices"]]
            for shape in shapes:
                cx, cy, cz = shape["center_m"]
                if shape["kind"] == "capsule":
                    ex = ey = shape["radius_m"]
                    ez = shape["half_height_m"]
                else:
                    ex, ey, ez = shape["half_extent_m"]
                # the collision stays within the visible prop (+2 cm) and starts on the ground
                self.assertGreaterEqual(cx - ex, min(xs) - 0.02, name)
                self.assertLessEqual(cx + ex, max(xs) + 0.02, name)
                self.assertGreaterEqual(cy - ey, min(ys) - 0.02, name)
                self.assertLessEqual(cy + ey, max(ys) + 0.02, name)
                self.assertAlmostEqual(cz - ez, 0.0, delta=0.01, msg=name)
                self.assertLessEqual(cz + ez, max(zs) + 0.02, name)
        # tree collision is the trunk only: the player walks under the canopy, not into it
        trunk = meshes["tree0"]["blocking_shapes"][0]
        self.assertLess(trunk["radius_m"], 0.3)

    def test_bushes_and_lantern_glow_stay_walk_through(self):
        props = _prop_module()
        self.assertFalse(props.stylized_bush(0).get("blocking_shapes"))
        self.assertFalse(props.street_lamp_glow().get("blocking_shapes"))


class FortressGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))
        cls.wall = next(w for w in cls.pkg["fortress_walls"] if w["outline_id"] == "osm:way:42318561")

    def test_gatehouse_is_an_open_round_arch_portal_without_roof(self):
        self.assertEqual(len(self.wall["gatehouses"]), 1)
        gh = self.wall["gatehouses"][0]
        self.assertEqual(gh["style"], "brick_round_arch_oculi")
        self.assertAlmostEqual(gh["opening_width_m"], 3.3, delta=0.01)
        self.assertAlmostEqual(gh["opening_height_m"], 4.1, delta=0.01)
        # cambered attic about 5.8 m above the bridge deck, no gable roof any more
        self.assertAlmostEqual(gh["top_z_m"] - gh["road_z_m"], 5.84, delta=0.05)
        meshes = self.pkg["meshes"]
        self.assertIn("FortressSandstone", meshes)
        self.assertTrue(meshes["FortressSandstone"]["collision"])
        self.assertFalse(meshes["FortressSteel"]["collision"], "drawbridge beams and chains are decoration")

    def test_forecourt_parapet_is_low_level_and_has_loopholes(self):
        parapets = self.wall["forecourt_parapets"]
        self.assertEqual(len(parapets), 1)
        fc = parapets[0]
        self.assertAlmostEqual(fc["height_above_court_m"], 2.3, delta=0.01)
        self.assertGreater(fc["length_m"], 15.0)
        gh = self.wall["gatehouses"][0]
        self.assertAlmostEqual(fc["court_z_m"], gh["road_z_m"], delta=0.05, msg="parapet stands at bridge level")
        self.assertGreaterEqual(self.wall["forecourt_loopholes"], 6)
        self.assertEqual(self.wall["stone_plinth_scope"], "forecourt")

    def test_wooden_bridges_have_open_timber_railings(self):
        bridges = {b["id"]: b for b in self.pkg["bridges"]}
        gate_bridge = bridges["bridge:osm:way:120431984"]
        self.assertEqual(gate_bridge["material"], "wood")
        self.assertEqual(gate_bridge["railing"], "timber_posts_rails")
        for b in bridges.values():
            self.assertEqual(b["railing"], "timber_posts_rails" if b["material"] == "wood" else "solid_parapet", b["id"])

    def test_sandsteintor_facade_lies_in_the_gate_wall(self):
        portals = {p["road_id"]: p for p in self.pkg["tunnel_portals"]}
        gate = portals[GATE_TUNNEL]
        self.assertEqual(gate["end_styles"].get("exit"), "sandstone_aedicula")
        facade = gate["facades"]["exit"]
        self.assertGreater(facade["skew_deg"], 15.0, "the passage meets the gate wall obliquely")
        self.assertLess(facade["skew_deg"], 30.0)
        self.assertLess(abs(facade["end_offset_m"]), 0.5)
        # the gate wall reaches into the brick portal block on both sides (no grass strip beside the portal)
        walls = {w["id"]: w for w in self.pkg["osm_walls"]}
        opening = next(o for o in walls[GATE_WALL]["openings"] if GATE_TUNNEL in o["label"])
        self.assertAlmostEqual(opening["width_m"], 7.2 - 0.6, delta=0.01)  # portal_wall_width_m - 2 x 0.3 m


if __name__ == "__main__":
    unittest.main()
