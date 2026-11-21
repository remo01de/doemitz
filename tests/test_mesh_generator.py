import unittest

from shapely.geometry import LineString, box, mapping

from tools.mesh_generator.__main__ import CURB_HEIGHT_M, PALETTE, ROAD_ELEVATION_M, Mesh, add_streets
from tools.mesh_generator.citizens import build_citizens
from tools.mesh_generator.traffic import route_vertices


class MeshGeneratorTest(unittest.TestCase):
    def test_adjacent_buildings_keep_independent_wall_faces(self):
        mesh = Mesh()
        mesh.add_walls(box(0, 0, 5, 5), height_m=6.5, base_m=0)
        mesh.add_walls(box(5, 0, 10, 5), height_m=6.5, base_m=0)
        self.assertEqual(len(mesh.triangles), 16)
        self.assertEqual(len(mesh.vertices), 32)
        self.assertTrue(
            {index for triangle in mesh.triangles[:8] for index in triangle}.isdisjoint(
                index for triangle in mesh.triangles[8:] for index in triangle
            )
        )

    def test_pilot_sidewalks_respect_crossings_and_buildings(self):
        meshes = {name: Mesh() for name in PALETTE}
        roads = [
            {
                "id": "osm:way:1",
                "properties": {"highway": "residential", "surface": "sett", "width": "6 m"},
                "geometry": mapping(LineString([(-20, 0), (20, 0)])),
            },
            {
                "id": "osm:way:2",
                "properties": {"highway": "residential", "width": "6 m"},
                "geometry": mapping(LineString([(0, -20), (0, 20)])),
            },
        ]
        building = box(6, 3, 8, 5)
        sources, sidewalks = add_streets(
            meshes, roads, box(-25, -25, 25, 25), building, 0, {"osm:way:1": 1.6},
        )
        self.assertEqual(sources, {"osm_width": 2})
        self.assertTrue(meshes["Paving"].triangles)
        self.assertTrue(meshes["Roads"].triangles)
        self.assertGreater(len(sidewalks), 0)
        self.assertAlmostEqual(sum(polygon.area for polygon in sidewalks), (2 * 34 - 2) * 1.6)
        self.assertTrue(all(polygon.intersection(building).area == 0 for polygon in sidewalks))
        self.assertTrue(all(polygon.intersection(box(-3, -20, 3, 20)).area == 0 for polygon in sidewalks))
        sidewalk_heights = {vertex[2] for vertex in meshes["Sidewalks"].vertices}
        self.assertEqual(sidewalk_heights, {0, ROAD_ELEVATION_M + CURB_HEIGHT_M})

    def test_vehicle_route_keeps_mapped_junctions_and_oneway_direction(self):
        vertices = [(0, 0), (20, 0), (20, 20), (0, 20)]
        roads = [
            {
                "id": f"osm:way:{index + 1}",
                "properties": {"highway": "residential", "oneway": "yes"},
                "geometry": mapping(LineString([start, end])),
            }
            for index, (start, end) in enumerate(zip(vertices, [*vertices[1:], vertices[0]]))
        ]
        self.assertEqual(route_vertices(roads), vertices)
        with self.assertRaisesRegex(ValueError, "invalid direction"):
            route_vertices(roads[::-1])
        with self.assertRaisesRegex(ValueError, "mapped junction"):
            route_vertices(roads[1:])

    def test_citizen_builder_validates_schedules_and_generates_sidewalk_routes(self):
        road = {
            "id": "osm:way:1",
            "properties": {"highway": "residential", "width": "6 m"},
            "geometry": mapping(LineString([(-20, 0), (20, 0)])),
        }
        buildings = [
            {"id": "osm:way:10", "properties": {"building": "yes"}, "geometry": mapping(box(-12, 5, -8, 9))},
            {"id": "osm:way:11", "properties": {"building": "civic"}, "geometry": mapping(box(8, -9, 12, -5))},
        ]
        sidewalks = [box(-20, 3, 20, 4.6), box(-20, -4.6, 20, -3)]
        obstacles = box(-12, 5, -8, 9).union(box(8, -9, 12, -5))
        config = {
            "pilot_road_id": "osm:way:1",
            "clock": {"start_minute": 470, "time_scale": 60.0},
            "places": [
                {"id": "home_a", "name": "Home A", "building_id": "osm:way:10", "kind": "home"},
                {"id": "work_b", "name": "Work B", "building_id": "osm:way:11", "kind": "work"},
            ],
            "citizens": [
                {
                    "id": "citizen_01",
                    "name": "Anna",
                    "home_place_id": "home_a",
                    "work_place_id": "work_b",
                    "walk_speed_mps": 1.35,
                    "coat_color": [0.5, 0.2, 0.2],
                    "schedule": [
                        {"start_minute": 0, "activity": "Home", "place_id": "home_a"},
                        {"start_minute": 480, "activity": "Working", "place_id": "work_b"},
                    ],
                }
            ],
        }
        compiled = build_citizens(
            config, {"osm:way:1": (road, 6.0)}, buildings, sidewalks, obstacles,
            ROAD_ELEVATION_M, ROAD_ELEVATION_M + CURB_HEIGHT_M,
        )
        self.assertEqual(len(compiled["places"]), 2)
        self.assertEqual(len(compiled["citizens"]), 1)
        self.assertEqual(len(compiled["routes"]), 2)
        for route in compiled["routes"]:
            self.assertGreaterEqual(len(route["points_m"]), 3)
            self.assertEqual(route["points_m"][0][2], round(ROAD_ELEVATION_M + CURB_HEIGHT_M, 4))
            self.assertEqual(route["points_m"][-1][2], round(ROAD_ELEVATION_M + CURB_HEIGHT_M, 4))

        bad_schedule = dict(config)
        bad_schedule["citizens"] = [dict(config["citizens"][0], schedule=[
            {"start_minute": 0, "activity": "Home", "place_id": "home_a"},
            {"start_minute": 480, "activity": "Working", "place_id": "work_b"},
            {"start_minute": 470, "activity": "Home", "place_id": "home_a"},
        ])]
        with self.assertRaisesRegex(ValueError, "strictly increase"):
            build_citizens(
                bad_schedule, {"osm:way:1": (road, 6.0)}, buildings, sidewalks, obstacles,
                ROAD_ELEVATION_M, ROAD_ELEVATION_M + CURB_HEIGHT_M,
            )
