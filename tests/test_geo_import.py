import unittest
import xml.etree.ElementTree as ET

from shapely.geometry import box

from tools.geo_import.export import clipped_geometry
from tools.geo_import.osm import Dataset, multipolygon
from tools.geo_transform.local import LocalFrame


class GeoImportTest(unittest.TestCase):
    def test_split_relation_ring_preserves_courtyard_when_clipped(self):
        dataset = Dataset(
            nodes={
                1: (0, 0), 2: (10, 0), 3: (10, 10), 4: (0, 10),
                5: (3, 3), 6: (5, 3), 7: (5, 5), 8: (3, 5),
            },
            ways={
                1: ET.fromstring('<way><nd ref="1"/><nd ref="2"/><nd ref="3"/></way>'),
                2: ET.fromstring('<way><nd ref="1"/><nd ref="4"/><nd ref="3"/></way>'),
                3: ET.fromstring(
                    '<way><nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/></way>'
                ),
            },
        )
        relation = ET.fromstring(
            '<relation><member type="way" ref="1" role="outer"/>'
            '<member type="way" ref="2" role="outer"/>'
            '<member type="way" ref="3" role="inner"/></relation>'
        )
        result, repaired = clipped_geometry(multipolygon(dataset, relation), box(0, 0, 8, 10), True)
        self.assertFalse(repaired)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.interiors), 1)
        self.assertAlmostEqual(result.area, 76)

    def test_projected_origin_and_axes(self):
        longitude, latitude = 11.2487, 53.14265
        frame = LocalFrame("EPSG:25833", [longitude, latitude])
        self.assertEqual(frame.xy(longitude, latitude), (0.0, 0.0))
        east, _ = frame.xy(longitude + 0.001, latitude)
        _, north = frame.xy(longitude, latitude + 0.001)
        self.assertTrue(66 < east < 68)
        self.assertTrue(110 < north < 113)
