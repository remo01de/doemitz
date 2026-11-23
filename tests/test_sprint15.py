"""Sprint 15: East-border harbour road closure, walkable tunnel portals, 6-subsystem split,
hybrid time scale (BaseTimeScale=20.0), interior lights fix, Speicher real gables,
harbour gangways & quay end-caps, and sharp-normal closed-bow boats."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
from shapely.geometry import LineString, Polygon, shape
from shapely.ops import unary_union

from tools.mesh_generator.harbour import _parse_meters
from tools.mesh_generator.locks import build_edge_wall

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/manifests/doemitz-altstadt.json"
DGM_LICENSE = ROOT / "data/manifests/doemitz-altstadt-dgm-license.json"
LOD2_LICENSE = ROOT / "data/manifests/doemitz-altstadt-lod2-license.json"
PROCESSED_DIR = ROOT / "data/processed/doemitz-altstadt"
CPP_ROOT = ROOT / "unreal/DoemitzLivingCity/Source/DoemitzLivingCity"
PROP_MESHES_PY = ROOT / "unreal/DoemitzLivingCity/Content/Python/doemitz_prop_meshes.py"

REF_NHN = 13.001


def _load_prop_meshes_module():
    spec = importlib.util.spec_from_file_location("doemitz_prop_meshes", PROP_MESHES_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FlatElevation:
    def __init__(self, z: float):
        self.z = z

    def sample_array(self, xs, ys):
        return np.full_like(np.asarray(xs, dtype=float), self.z, dtype=float)


class Sprint15Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.scene = json.loads((PROCESSED_DIR / "scene.json").read_text(encoding="utf-8"))
        cls.pkg = json.loads((PROCESSED_DIR / "unreal-city-meshes.json").read_text(encoding="utf-8"))

    def test_m1_extended_east_bounds_and_two_laiv_tiles(self):
        self.assertEqual(self.config["bounds_lonlat"], [11.2428, 53.1372, 11.2630, 53.1455])
        self.assertEqual(self.config["origin_lonlat"], [11.2487, 53.14265])
        self.assertAlmostEqual(self.config["dgm"]["reference_elevation_m"], REF_NHN)

        dgm_lic = json.loads(DGM_LICENSE.read_text(encoding="utf-8"))
        lod2_lic = json.loads(LOD2_LICENSE.read_text(encoding="utf-8"))
        self.assertIn("dgm1_33_248_5894_2_xyz.zip", dgm_lic["notes"])
        self.assertIn("dgm1_33_250_5894_2_xyz.zip", dgm_lic["notes"])
        self.assertIn("lod2_33_248_5894_2_gml.zip", lod2_lic["notes"])
        self.assertIn("lod2_33_250_5894_2_gml.zip", lod2_lic["notes"])
        self.assertGreater(self.scene["terrain"]["grid"]["cols"], 1350)

    def test_m1_south_harbour_roads_connected_and_parking_local(self):
        graph = self.pkg["road-graph"]
        harbour_streets = {"Werderstraße", "Am Hafen", "Hafenplatz"}
        found = 0
        for edge in graph["edges"]:
            if edge.get("name") in harbour_streets:
                found += 1
                self.assertFalse(edge.get("dead_end"), f"Harbour edge {edge['id']} ({edge['name']}) must not be a dead_end")
        self.assertGreaterEqual(found, 10)

        edge_by_id = {e["id"]: e for e in graph["edges"]}
        south_harbour_lots = 0
        for lot in graph["parking_lots"]:
            self.assertIn(lot["access_edge_id"], edge_by_id)
            self.assertLessEqual(
                float(lot["access_distance_m"]),
                95.0,
                f"Parking lot {lot['id']} bound too far ({lot['access_distance_m']:.1f}m) from access edge {lot['access_edge_id']}",
            )
            px, py = lot["position_m"][0], lot["position_m"][1]
            if px > 650.0 and py < -500.0:
                south_harbour_lots += 1
                self.assertEqual(
                    edge_by_id[lot["access_edge_id"]].get("name"),
                    "Am Hafen",
                    f"South harbour lot {lot['id']} should bind to Am Hafen, got {edge_by_id[lot['access_edge_id']].get('name')}",
                )
        self.assertGreaterEqual(south_harbour_lots, 3)

    def test_m1_pedestrian_graph_tunnels_connected_and_no_water_crossings(self):
        cit = self.pkg["citizens"]
        self.assertEqual(cit["disconnected_route_count"], 0)
        walkable_tunnels = set(cit.get("walkable_tunnel_ids", []))
        self.assertIn("osm:way:120431987", walkable_tunnels)
        self.assertIn("osm:way:416256369", walkable_tunnels)

        waters = [shape(w["geometry"]).buffer(-1.5) for w in self.scene["layers"]["water"]]
        bridges = [
            shape(r["geometry"]).buffer(5.0)
            for r in self.scene["layers"]["roads"]
            if str(r["properties"].get("bridge", "no")).lower() not in ("", "no", "false", "0")
        ]
        open_water = unary_union(waters).difference(unary_union(bridges))
        for route in cit["routes"]:
            line = LineString([(p[0], p[1]) for p in route["points_m"]])
            wet_m = line.intersection(open_water).length
            self.assertLessEqual(
                wet_m,
                3.0,
                f"Citizen route {route['from_place_id']}->{route['to_place_id']} crosses {wet_m:.1f}m of open water",
            )

    def test_m3_hybrid_time_scale_and_schedule_reachability(self):
        cit = self.pkg["citizens"]
        self.assertAlmostEqual(cit["clock"]["time_scale"], 20.0, places=3)

        route_len = {
            (r["from_place_id"], r["to_place_id"]): LineString([(p[0], p[1]) for p in r["points_m"]]).length
            for r in cit["routes"]
        }
        for person in cit["citizens"]:
            speed = float(person.get("walk_speed_mps", 1.35))
            sched = person["schedule"]
            for i in range(len(sched)):
                a, b = sched[i], sched[(i + 1) % len(sched)]
                if a["place_id"] == b["place_id"]:
                    continue
                dist_m = route_len.get((a["place_id"], b["place_id"]), 0.0)
                slot_min = (sched[(i + 2) % len(sched)]["start_minute"] - b["start_minute"]) % 1440
                if slot_min <= 0:
                    slot_min = 60
                game_walk_min = (dist_m / speed) / 60.0
                self.assertLess(
                    game_walk_min,
                    slot_min,
                    f"{person['id']} leg {a['place_id']}->{b['place_id']} ({dist_m:.0f}m) exceeds {slot_min}m slot",
                )

    def test_m4_speicher_has_only_two_real_gable_hoist_beams(self):
        sp_b = next(b for b in self.scene["layers"]["buildings"] if b["id"] == "osm:way:42883863")
        minx, miny, maxx, maxy = shape(sp_b["geometry"]).bounds
        timber_lm = self.pkg["meshes"].get("TimberTrim__lm", {"vertices": []})
        high_pts = [
            v for v in timber_lm["vertices"]
            if minx - 2.0 <= v[0] <= maxx + 2.0 and miny - 2.0 <= v[1] <= maxy + 2.0 and v[2] > 20.0
        ]
        clusters = sorted({(round(v[0] / 2.0) * 2, round(v[1] / 2.0) * 2) for v in high_pts})
        self.assertEqual(
            len(clusters),
            2,
            f"Expected exactly 2 Speicher gable hoist beam clusters, got {len(clusters)}: {clusters}",
        )

    def test_m4_harbour_parse_meters_and_south_gangways(self):
        self.assertEqual(_parse_meters(2), 2.0)
        self.assertEqual(_parse_meters(2.5), 2.5)
        self.assertEqual(_parse_meters("2"), 2.0)
        self.assertEqual(_parse_meters("2 m"), 2.0)
        self.assertEqual(_parse_meters("2,5 m"), 2.5)
        self.assertIsNone(_parse_meters("invalid"))
        self.assertIsNone(_parse_meters(None))
        self.assertIsNone(_parse_meters(True))
        self.assertIsNone(_parse_meters("-1.5"))

        gangways = {g["id"]: g for g in self.pkg["harbour"].get("gangways", [])}
        for steps_id in ("osm:way:1355847994", "osm:way:1355847995"):
            self.assertIn(steps_id, gangways, f"Missing south marina steps gangway {steps_id}")
            self.assertEqual(gangways[steps_id]["kind"], "quay_steps_gangway")
            self.assertLessEqual(gangways[steps_id]["slope_deg"], 15.0)
            self.assertGreater(gangways[steps_id]["z_high_m"] - gangways[steps_id]["z_low_m"], 2.0)
        for g in gangways.values():
            self.assertLessEqual(g["slope_deg"], 15.0, f"Gangway {g['id']} too steep: {g['slope_deg']} deg")

    def test_m4_lock_edge_wall_has_solid_end_caps(self):
        meshes = {k: SimpleNamespace(vertices=[], triangles=[]) for k in ("LockConcrete", "LockCoping", "LockRailing", "LockSteel")}
        side = LineString([(0.0, 0.0), (10.0, 0.0)])
        water_area = Polygon([(-2.0, 0.0), (12.0, 0.0), (12.0, 10.0), (-2.0, 10.0)])
        build_edge_wall(
            meshes,
            side=side,
            water_area=water_area,
            z_bot=0.0,
            water_level=1.5,
            elevation=_FlatElevation(4.0),
            wall_id="test_wall",
            ladders=False,
            bollards=False,
            railing=False,
        )
        verts = meshes["LockConcrete"].vertices
        tris = meshes["LockConcrete"].triangles
        start_cap = any(
            abs(verts[a][0]) < 1e-6 and abs(verts[b][0]) < 1e-6 and abs(verts[c][0]) < 1e-6
            for a, b, c in tris
        )
        end_cap = any(
            abs(verts[a][0] - 10.0) < 1e-6 and abs(verts[b][0] - 10.0) < 1e-6 and abs(verts[c][0] - 10.0) < 1e-6
            for a, b, c in tris
        )
        self.assertTrue(start_cap, "build_edge_wall missing solid start end-cap")
        self.assertTrue(end_cap, "build_edge_wall missing solid end end-cap")

    def test_m4_boat_closed_bow_keel_and_sharp_cabin_boxes(self):
        mod = _load_prop_meshes_module()
        for variant in (0, 1, 2):
            boat = mod.stylized_boat(variant)
            verts = boat["vertices"]
            tris = boat["triangles"]
            bow_verts = [v for v in verts if abs(v[1] - 4.5) < 1e-4]
            self.assertTrue(bow_verts, f"Boat variant {variant} missing bow vertices at y=4.5")
            for v in bow_verts:
                self.assertAlmostEqual(v[0], 0.0, places=5, msg=f"Boat variant {variant} bow slit open at x={v[0]}")
            keel_tris = [t for t in tris if all(verts[idx][2] <= -0.1 for idx in t)]
            self.assertGreaterEqual(len(keel_tris), 5, f"Boat variant {variant} missing closed keel bottom")
            usage = [0] * len(verts)
            for a, b, c in tris:
                usage[a] += 1
                usage[b] += 1
                usage[c] += 1
            if variant in (0, 1):
                cabin_v_indices = [i for i, v in enumerate(verts) if v[2] > 0.86]
                self.assertTrue(cabin_v_indices)
                self.assertLessEqual(
                    max(usage[i] for i in cabin_v_indices),
                    2,
                    f"Boat variant {variant} cabin box shares vertices across orthogonal faces (causes smooth shading)",
                )

    def test_m2_and_m4_cpp_architecture_and_lighting_guards(self):
        required_headers = [
            "Public/Simulation/DoemitzSimulationTypes.h",
            "Public/Simulation/DoemitzSimulationSubsystem.h",
            "Public/Economy/DoemitzEconomySubsystem.h",
            "Public/Simulation/DoemitzCitizenSubsystem.h",
            "Public/Traffic/DoemitzTrafficSubsystem.h",
            "Public/Tasks/DoemitzTaskSubsystem.h",
            "Public/Simulation/DoemitzSaveSubsystem.h",
        ]
        for rel in required_headers:
            self.assertTrue((CPP_ROOT / rel).is_file(), f"Missing Sprint 15 subsystem header: {rel}")

        sim_cpp = (CPP_ROOT / "Private/Simulation/DoemitzSimulationSubsystem.cpp").read_text(encoding="utf-8")
        self.assertLess(len(sim_cpp.splitlines()), 600, "DoemitzSimulationSubsystem.cpp should stay lean (<600 lines, down from 3708)")

        gfx_cpp = (CPP_ROOT / "Private/Settings/DoemitzGraphicsSettings.cpp").read_text(encoding="utf-8")
        self.assertNotIn(
            "TActorIterator<APointLight>",
            gfx_cpp,
            "DoemitzGraphicsSettings must only throttle DayNightController::GetStreetLights(), never all APointLight actors",
        )
        self.assertIn("GetStreetLights()", gfx_cpp)


if __name__ == "__main__":
    unittest.main()
