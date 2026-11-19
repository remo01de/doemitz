"""Project WGS84 geometry into a shared ETRS89/UTM frame in meters."""

from pyproj import Transformer
from shapely import transform


class LocalFrame:
    def __init__(self, crs: str, origin_lonlat: list[float]):
        self.transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self.easting, self.northing = self.transformer.transform(*origin_lonlat, errcheck=True)

    def xy(self, longitude, latitude):
        easting, northing = self.transformer.transform(longitude, latitude, errcheck=True)
        return easting - self.easting, northing - self.northing

    def geometry(self, geometry):
        return transform(geometry, self.xy, interleaved=False)
