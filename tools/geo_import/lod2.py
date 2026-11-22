"""Fetch and parse official LoD2 CityGML 3D building models from LAiV Mecklenburg-Vorpommern."""

from __future__ import annotations

from hashlib import file_digest, sha256
import json
from math import atan2, degrees, hypot
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

from shapely import make_valid, union_all
from shapely.geometry import Polygon, shape
from shapely.strtree import STRtree

from tools.geo_transform.local import LocalFrame


CITYGML_NS = {
    "core": "http://www.opengis.net/citygml/1.0",
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml": "http://www.opengis.net/gml",
}


DEFAULT_LOD2_ATOM_URL = (
    "https://www.geodaten-mv.de/dienste/gebaeude_atom"
    "?type=dataset&id=8397b554-5cb9-4274-8be8-c20490d9a6e8"
)
DEFAULT_LOD2_MARGIN_M = 50.0
DEFAULT_LOD2_OVERLAP_THRESHOLD = 0.60
TILE_NAME_RE = re.compile(r"lod2_33_(\d+)_(\d+)_(\d+)_gml\.zip$", re.IGNORECASE)
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# AdV / ALKIS CityGML roofType code table -> normalized roof shape
ADV_ROOF_TYPE_MAP = {
    "1000": "flat",          # Flachdach
    "2100": "skillion",      # Pultdach
    "2200": "skillion",      # Versetztes Pultdach
    "3100": "gabled",        # Satteldach
    "3200": "hipped",        # Walmdach
    "3300": "half-hipped",   # Krüppelwalmdach
    "3400": "mansard",       # Mansardendach
    "3500": "pyramidal",     # Zeltdach
    "3600": "conical",       # Kegeldach
    "3700": "dome",          # Kuppeldach
    "3800": "sawtooth",      # Sheddach
    "3900": "arch",          # Bogendach
    "4000": "gabled",        # Turmdach (handled specially for church towers / spires)
    "5000": "gabled",        # Mischform
    "9999": "gabled",        # Sonstiges
}


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(payload)
            stream.close()
            tmp.replace(path)
        finally:
            stream.close()
            tmp.unlink(missing_ok=True)


def _projected_bounds_with_margin(config: dict, margin_m: float) -> tuple[float, float, float, float]:
    frame = LocalFrame(config["projected_crs"], config["origin_lonlat"])
    min_lon, min_lat, max_lon, max_lat = config["bounds_lonlat"]
    corners = [
        frame.transformer.transform(lon, lat, errcheck=True)
        for lon in (min_lon, max_lon)
        for lat in (min_lat, max_lat)
    ]
    return (
        min(c[0] for c in corners) - margin_m,
        min(c[1] for c in corners) - margin_m,
        max(c[0] for c in corners) + margin_m,
        max(c[1] for c in corners) + margin_m,
    )


def discover_lod2_tiles(atom_xml: bytes, bounds_utm: tuple[float, float, float, float]) -> dict:
    """Parse LAiV M-V LoD2 Atom dataset feed and select CityGML-ZIP tiles overlapping bounds_utm."""
    root = ET.fromstring(atom_xml)
    updated = (root.findtext("atom:updated", namespaces=ATOM_NS) or "").strip()
    year_match = re.match(r"(\d{4})", updated)
    delivery_year = int(year_match.group(1)) if year_match else 2026
    rights = (root.findtext("atom:rights", namespaces=ATOM_NS) or "").strip()

    min_e, min_n, max_e, max_n = bounds_utm
    tiles = []
    seen = set()
    for entry in root.findall("atom:entry", namespaces=ATOM_NS):
        entry_updated = (entry.findtext("atom:updated", namespaces=ATOM_NS) or updated).strip()
        e_year_match = re.match(r"(\d{4})", entry_updated)
        e_year = int(e_year_match.group(1)) if e_year_match else delivery_year
        for link in entry.findall("atom:link", namespaces=ATOM_NS):
            href = link.attrib.get("href", "")
            match = TILE_NAME_RE.search(href)
            if not match:
                continue
            tile_name = match.group(0)
            if tile_name in seen:
                continue
            e_km = int(match.group(1))
            n_km = int(match.group(2))
            size_km = int(match.group(3))
            tile_min_e = e_km * 1000.0
            tile_min_n = n_km * 1000.0
            tile_size_m = size_km * 1000.0
            tile_max_e = tile_min_e + tile_size_m
            tile_max_n = tile_min_n + tile_size_m
            if tile_max_e >= min_e and tile_min_e <= max_e and tile_max_n >= min_n and tile_min_n <= max_n:
                seen.add(tile_name)
                tiles.append(
                    {
                        "name": tile_name,
                        "url": href,
                        "delivery_year": e_year,
                        "updated": entry_updated,
                        "easting_min_m": tile_min_e,
                        "northing_min_m": tile_min_n,
                        "tile_size_m": tile_size_m,
                    }
                )
    tiles.sort(key=lambda item: item["name"])
    if not tiles:
        raise ValueError(f"no LoD2 CityGML tiles overlap UTM bounds {bounds_utm}")
    return {
        "updated": updated,
        "delivery_year": max(t["delivery_year"] for t in tiles),
        "rights": rights,
        "tiles": tiles,
    }


def fetch_lod2_tiles(config: dict, raw_dir: Path, margin_m: float | None = None) -> dict:
    """Download all LoD2 CityGML ZIP tiles intersecting config bounds + margin into raw_dir/lod2/."""
    lod2_cfg = config.get("lod2") or {}
    atom_url = lod2_cfg.get("atom_url", DEFAULT_LOD2_ATOM_URL)
    margin = float(margin_m if margin_m is not None else lod2_cfg.get("margin_m", DEFAULT_LOD2_MARGIN_M))
    bounds_utm = _projected_bounds_with_margin(config, margin)

    req = Request(atom_url, headers={"User-Agent": "DoemitzLivingCity/0.1"})
    with urlopen(req, timeout=60) as response:
        atom_xml = response.read()

    discovered = discover_lod2_tiles(atom_xml, bounds_utm)
    lod2_dir = raw_dir / "lod2"
    lod2_dir.mkdir(parents=True, exist_ok=True)

    downloaded_tiles = []
    for tile in discovered["tiles"]:
        dest = lod2_dir / tile["name"]
        tile_req = Request(tile["url"], headers={"User-Agent": "DoemitzLivingCity/0.1"})
        with urlopen(tile_req, timeout=180) as response:
            payload = response.read()
        _atomic_write_bytes(dest, payload)
        digest = sha256(payload).hexdigest()
        downloaded_tiles.append(
            {
                **tile,
                "sha256": digest,
                "size_bytes": len(payload),
            }
        )

    delivery_year = discovered["delivery_year"]
    metadata = {
        "schema_version": 1,
        "dataset": "3D-Gebäudemodelle (Strukturmodell, LoD2) Mecklenburg-Vorpommern",
        "atom_url": atom_url,
        "projected_crs": config["projected_crs"],
        "vertical_crs": "DHHN2016 (NHN)",
        "format": "CityGML 1.0 (XML/ZIP)",
        "margin_m": margin,
        "updated": discovered["updated"],
        "delivery_year": delivery_year,
        "license": "Creative Commons Namensnennung – 4.0 International (CC BY 4.0)",
        "license_id": "cc-by/4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": f"© GeoBasis-DE/M-V {delivery_year}",
        "tiles": downloaded_tiles,
    }
    meta_bytes = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write_bytes(lod2_dir / "sources.json", meta_bytes)
    return metadata


def _parse_poslist_local(text: str, origin_e: float, origin_n: float) -> list[tuple[float, float, float]]:
    vals = [float(v) for v in text.split()]
    return [
        (vals[i] - origin_e, vals[i + 1] - origin_n, vals[i + 2])
        for i in range(0, len(vals) - 2, 3)
    ]


def _extract_ridge_direction_deg(
    roof_rings: list[list[tuple[float, float, float]]],
    ridge_nhn_m: float,
    footprint: Polygon,
) -> float:
    """Extract primary ridge direction in degrees [0, 180) (0 = East, 90 = North) from LoD2 roof surfaces."""
    best_len = 0.0
    best_angle = None
    tol_m = 0.25
    for ring in roof_rings:
        for a, b in zip(ring, ring[1:]):
            if a[2] >= ridge_nhn_m - tol_m and b[2] >= ridge_nhn_m - tol_m:
                dx = b[0] - a[0]
                dy = b[1] - a[1]
                seg = hypot(dx, dy)
                if seg > best_len + 1e-6:
                    best_len = seg
                    best_angle = degrees(atan2(dy, dx)) % 180.0
    if best_angle is not None and best_len >= 0.5:
        return round(best_angle, 2)

    # Fallback: longest edge of footprint's minimum rotated rectangle
    mrr = footprint.minimum_rotated_rectangle
    if isinstance(mrr, Polygon) and len(mrr.exterior.coords) >= 4:
        coords = list(mrr.exterior.coords)[:4]
        e0 = hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
        e1 = hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
        if e0 >= e1:
            dx, dy = coords[1][0] - coords[0][0], coords[1][1] - coords[0][1]
        else:
            dx, dy = coords[2][0] - coords[1][0], coords[2][1] - coords[1][1]
        return round(degrees(atan2(dy, dx)) % 180.0, 2)
    return 0.0


def _extract_slope_direction_deg(
    roof_rings: list[list[tuple[float, float, float]]],
) -> float | None:
    """For skillion roofs, compute downhill direction [0, 360) from highest to lowest roof vertices."""
    all_pts = [pt for ring in roof_rings for pt in ring]
    if len(all_pts) < 3:
        return None
    z_min = min(p[2] for p in all_pts)
    z_max = max(p[2] for p in all_pts)
    if z_max - z_min < 0.2:
        return None
    hi = [p for p in all_pts if p[2] >= z_max - 0.25]
    lo = [p for p in all_pts if p[2] <= z_min + 0.25]
    if not hi or not lo:
        return None
    hx = sum(p[0] for p in hi) / len(hi)
    hy = sum(p[1] for p in hi) / len(hi)
    lx = sum(p[0] for p in lo) / len(lo)
    ly = sum(p[1] for p in lo) / len(lo)
    dx, dy = lx - hx, ly - hy
    if hypot(dx, dy) < 0.1:
        return None
    return round(degrees(atan2(dy, dx)) % 360.0, 2)


def _iter_citygml_streams(lod2_dir: Path) -> list[tuple[str, bytes]]:
    streams: list[tuple[str, bytes]] = []
    for path in sorted(lod2_dir.iterdir()):
        low = path.name.lower()
        if low.endswith(".zip"):
            with zipfile.ZipFile(path, "r") as zf:
                for member in sorted(zf.namelist()):
                    if member.lower().endswith((".gml", ".xml")):
                        streams.append((f"{path.name}:{member}", zf.read(member)))
        elif low.endswith((".gml", ".xml")):
            streams.append((path.name, path.read_bytes()))
    return streams


def parse_lod2_buildings(lod2_dir: Path, frame: LocalFrame) -> list[dict]:
    """Parse all CityGML LoD2 buildings in lod2_dir into local meters."""
    oe, on = frame.easting, frame.northing
    buildings: list[dict] = []
    seen_ids: set[str] = set()

    for _, payload in _iter_citygml_streams(lod2_dir):
        root = ET.fromstring(payload)
        for elem in root.findall(".//bldg:Building", CITYGML_NS):
            gid = elem.attrib.get(f"{{{CITYGML_NS['gml']}}}id", "").strip()
            if not gid or gid in seen_ids:
                continue
            rt_code = (elem.findtext("bldg:roofType", namespaces=CITYGML_NS) or "").strip()
            roof_shape = ADV_ROOF_TYPE_MAP.get(rt_code, "gabled")
            mh_txt = elem.findtext("bldg:measuredHeight", namespaces=CITYGML_NS)
            measured_h = float(mh_txt) if mh_txt else None

            ground_polys: list[Polygon] = []
            ground_zs: list[float] = []
            for gs in elem.findall(".//bldg:GroundSurface", CITYGML_NS):
                for pl in gs.findall(".//gml:exterior//gml:posList", CITYGML_NS):
                    if not pl.text:
                        continue
                    pts = _parse_poslist_local(pl.text, oe, on)
                    if len(pts) >= 4:
                        poly = Polygon([(p[0], p[1]) for p in pts])
                        if not poly.is_valid:
                            poly = make_valid(poly)
                        if poly.area > 0.1:
                            ground_polys.append(poly)
                            ground_zs.extend(p[2] for p in pts)

            if not ground_polys or not ground_zs:
                continue
            footprint = union_all(ground_polys)
            if footprint.is_empty or footprint.area < 0.5:
                continue

            roof_rings: list[list[tuple[float, float, float]]] = []
            roof_surface_eaves: list[tuple[float, float]] = []
            for rs in elem.findall(".//bldg:RoofSurface", CITYGML_NS):
                for pl in rs.findall(".//gml:exterior//gml:posList", CITYGML_NS):
                    if not pl.text:
                        continue
                    pts = _parse_poslist_local(pl.text, oe, on)
                    if len(pts) >= 4:
                        roof_rings.append(pts)
                        rpoly = Polygon([(p[0], p[1]) for p in pts])
                        area_2d = rpoly.area if rpoly.is_valid else 0.0
                        roof_surface_eaves.append((max(area_2d, 0.1), min(p[2] for p in pts)))

            ground_nhn = min(ground_zs)
            all_rz = [p[2] for ring in roof_rings for p in ring]
            if all_rz:
                ridge_nhn = max(all_rz)
                if len(roof_surface_eaves) >= 2:
                    # Area-weighted median eave height for every roof type (Sprint 13): small low roof
                    # surfaces (porches, cellar entrances, annexes) must not pull down the main eave.
                    # Example: Wallstraße 6 has a 7.7 m² flat roof 0.1 m above ground next to its
                    # 160 m² gabled main roof (eave 8.5 m); min() produced a 2 m eave.
                    roof_surface_eaves.sort(key=lambda item: item[1])
                    total_a = sum(a for a, _ in roof_surface_eaves)
                    acc = 0.0
                    eave_nhn = roof_surface_eaves[0][1]
                    for a, ez in roof_surface_eaves:
                        acc += a
                        if acc >= total_a * 0.5:
                            eave_nhn = ez
                            break
                else:
                    eave_nhn = min(all_rz)
            else:
                h_fallback = measured_h if measured_h is not None else 6.5
                eave_nhn = ground_nhn + h_fallback
                ridge_nhn = eave_nhn

            eave_h = max(2.0, round(eave_nhn - ground_nhn, 3))
            ridge_h = max(eave_h, round(ridge_nhn - ground_nhn, 3))
            if measured_h is not None and measured_h > ridge_h:
                ridge_h = round(measured_h, 3)

            ridge_dir = _extract_ridge_direction_deg(roof_rings, ridge_nhn, footprint)
            slope_dir = _extract_slope_direction_deg(roof_rings) if roof_shape == "skillion" else None

            seen_ids.add(gid)
            buildings.append(
                {
                    "lod2_id": gid,
                    "footprint": footprint,
                    "roof_type_code": rt_code,
                    "roof_shape": roof_shape,
                    "eave_height_m": eave_h,
                    "ridge_height_m": ridge_h,
                    "measured_height_m": round(measured_h, 3) if measured_h is not None else None,
                    "ridge_direction_deg": ridge_dir,
                    "slope_direction_deg": slope_dir,
                    "ground_nhn_m": round(ground_nhn, 3),
                    "eave_nhn_m": round(eave_nhn, 3),
                    "ridge_nhn_m": round(ridge_nhn, 3),
                }
            )
    buildings.sort(key=lambda b: b["lod2_id"])
    return buildings


def load_and_match_lod2_buildings(
    config: dict,
    raw_dir: Path,
    frame: LocalFrame,
    osm_buildings: list[dict],
    overlap_threshold: float | None = None,
) -> tuple[dict[str, dict], dict | None, list[dict]]:
    """
    Match OSM building footprints 1:1 to LAiV M-V LoD2 CityGML buildings by area overlap.
    Each LoD2 building is assigned to at most one OSM building (greedy by intersection area).
    Returns (matches_by_osm_id, lod2_meta, lod2_raw_files).
    """
    lod2_dir = raw_dir / "lod2"
    if not lod2_dir.is_dir():
        return {}, None, []

    tile_files = sorted(
        p for p in lod2_dir.iterdir()
        if p.is_file() and p.name.lower().endswith((".zip", ".gml", ".xml"))
    )
    if not tile_files:
        return {}, None, []

    lod2_cfg = config.get("lod2") or {}
    threshold = float(
        overlap_threshold
        if overlap_threshold is not None
        else lod2_cfg.get("overlap_threshold", DEFAULT_LOD2_OVERLAP_THRESHOLD)
    )

    sources_meta = {}
    sources_path = lod2_dir / "sources.json"
    if sources_path.is_file():
        sources_meta = json.loads(sources_path.read_text(encoding="utf-8"))
    tiles_by_name = {t["name"]: t for t in sources_meta.get("tiles", [])}

    raw_files = []
    for path in tile_files:
        with path.open("rb") as stream:
            digest = file_digest(stream, "sha256").hexdigest()
        t_info = tiles_by_name.get(path.name, {})
        raw_files.append(
            {
                "name": f"lod2/{path.name}",
                "url": t_info.get("url", ""),
                "delivery_year": t_info.get("delivery_year", sources_meta.get("delivery_year", 2026)),
                "sha256": digest,
            }
        )

    lod2_buildings = parse_lod2_buildings(lod2_dir, frame)
    if not lod2_buildings:
        return {}, None, raw_files

    geoms = [b["footprint"] for b in lod2_buildings]
    tree = STRtree(geoms)

    candidates: list[tuple[float, float, str, int]] = []
    for ob in osm_buildings:
        opoly = shape(ob["geometry"])
        if opoly.is_empty or opoly.area <= 0.0:
            continue
        for idx in tree.query(opoly, predicate="intersects"):
            lpoly = geoms[int(idx)]
            inter_area = opoly.intersection(lpoly).area
            cov_osm = inter_area / opoly.area
            if cov_osm >= threshold:
                candidates.append((inter_area, cov_osm, ob["id"], int(idx)))

    # Deterministic greedy 1:1 assignment: largest overlap area first, never double-assign an LoD2 building.
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2], lod2_buildings[item[3]]["lod2_id"]))
    used_osm: set[str] = set()
    used_lod2: set[int] = set()
    matches: dict[str, dict] = {}
    for inter_area, cov_osm, osm_id, lod_idx in candidates:
        if osm_id in used_osm or lod_idx in used_lod2:
            continue
        used_osm.add(osm_id)
        used_lod2.add(lod_idx)
        lb = lod2_buildings[lod_idx]
        entry = {
            "lod2_id": lb["lod2_id"],
            "overlap_ratio": round(cov_osm, 4),
            "roof_type_code": lb["roof_type_code"],
            "roof_shape": lb["roof_shape"],
            "eave_height_m": lb["eave_height_m"],
            "ridge_height_m": lb["ridge_height_m"],
            "ridge_direction_deg": lb["ridge_direction_deg"],
            "ground_nhn_m": lb["ground_nhn_m"],
            "eave_nhn_m": lb["eave_nhn_m"],
            "ridge_nhn_m": lb["ridge_nhn_m"],
        }
        if lb["slope_direction_deg"] is not None:
            entry["slope_direction_deg"] = lb["slope_direction_deg"]
        matches[osm_id] = entry

    delivery_year = int(sources_meta.get("delivery_year", 2026))
    lod2_meta = {
        "status": "imported",
        "dataset": sources_meta.get(
            "dataset", "3D-Gebäudemodelle (Strukturmodell, LoD2) Mecklenburg-Vorpommern"
        ),
        "atom_url": sources_meta.get("atom_url", lod2_cfg.get("atom_url", DEFAULT_LOD2_ATOM_URL)),
        "delivery_year": delivery_year,
        "license": sources_meta.get(
            "license", "Creative Commons Namensnennung – 4.0 International (CC BY 4.0)"
        ),
        "license_id": sources_meta.get("license_id", "cc-by/4.0"),
        "license_url": sources_meta.get("license_url", "https://creativecommons.org/licenses/by/4.0/"),
        "attribution": sources_meta.get("attribution", f"© GeoBasis-DE/M-V {delivery_year}"),
        "overlap_threshold": threshold,
        "total_lod2_buildings": len(lod2_buildings),
        "matched_osm_buildings": len(matches),
        "total_osm_buildings": len(osm_buildings),
    }
    return matches, lod2_meta, raw_files
