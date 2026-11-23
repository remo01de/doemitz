"""Fetch and parse official DGM1 elevation tiles from LAiV Mecklenburg-Vorpommern."""

from __future__ import annotations

from hashlib import file_digest, sha256
import io
import json
from math import floor
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from tools.geo_transform.local import LocalFrame


DEFAULT_DGM_ATOM_URL = (
    "https://www.geodaten-mv.de/dienste/dgm_atom"
    "?type=dataset&id=ca268792-s2q1-4a39-b34c-9ec5bf9a4469"
)
DEFAULT_DGM_MARGIN_M = 50.0
DEFAULT_GRID_CLIP_MARGIN_M = 16.0
TILE_NAME_RE = re.compile(r"dgm1_33_(\d+)_(\d+)_(\d+)_xyz\.zip$", re.IGNORECASE)
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


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
    min_e = min(c[0] for c in corners) - margin_m
    max_e = max(c[0] for c in corners) + margin_m
    min_n = min(c[1] for c in corners) - margin_m
    max_n = max(c[1] for c in corners) + margin_m
    return min_e, min_n, max_e, max_n


def discover_dgm_tiles(atom_xml: bytes, bounds_utm: tuple[float, float, float, float]) -> dict:
    """Parse LAiV M-V DGM1 Atom dataset feed and select XYZ-ZIP tiles overlapping bounds_utm."""
    root = ET.fromstring(atom_xml)
    updated = (root.findtext("atom:updated", namespaces=ATOM_NS) or "").strip()
    year_match = re.match(r"(\d{4})", updated)
    delivery_year = int(year_match.group(1)) if year_match else 2025
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
        raise ValueError(f"no DGM1 XYZ tiles overlap UTM bounds {bounds_utm}")
    return {
        "updated": updated,
        "delivery_year": max(t["delivery_year"] for t in tiles),
        "rights": rights,
        "tiles": tiles,
    }


def fetch_dgm_tiles(config: dict, raw_dir: Path, margin_m: float | None = None) -> dict:
    """Download all DGM1 XYZ-ZIP tiles intersecting config bounds + margin into raw_dir/dgm1/."""
    dgm_cfg = config.get("dgm") or {}
    atom_url = dgm_cfg.get("atom_url", DEFAULT_DGM_ATOM_URL)
    margin = float(margin_m if margin_m is not None else dgm_cfg.get("margin_m", DEFAULT_DGM_MARGIN_M))
    bounds_utm = _projected_bounds_with_margin(config, margin)

    req = Request(atom_url, headers={"User-Agent": "DoemitzLivingCity/0.1"})
    with urlopen(req, timeout=60) as response:
        atom_xml = response.read()

    discovered = discover_dgm_tiles(atom_xml, bounds_utm)
    dgm_dir = raw_dir / "dgm1"
    dgm_dir.mkdir(parents=True, exist_ok=True)

    downloaded_tiles = []
    for tile in discovered["tiles"]:
        dest = dgm_dir / tile["name"]
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
        "dataset": "Digitales Geländemodell 1 m (DGM1) Mecklenburg-Vorpommern",
        "atom_url": atom_url,
        "projected_crs": config["projected_crs"],
        "vertical_crs": "DHHN2016 (NHN)",
        "grid_spacing_m": 1.0,
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
    _atomic_write_bytes(dgm_dir / "sources.json", meta_bytes)
    return metadata


def _read_xyz_points(tile_path: Path) -> np.ndarray:
    """Read (N, 3) float64 array [easting, northing, nhn_m] from an .xyz file or .zip containing .xyz."""
    chunks = []
    if tile_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(tile_path, "r") as zf:
            xyz_names = sorted(name for name in zf.namelist() if name.lower().endswith(".xyz"))
            if not xyz_names:
                raise ValueError(f"{tile_path.name} contains no .xyz files")
            for name in xyz_names:
                raw = zf.read(name)
                arr = np.loadtxt(raw.splitlines(), dtype=np.float64, ndmin=2)
                if arr.shape[1] != 3:
                    raise ValueError(f"unexpected XYZ column count in {tile_path.name}:{name}")
                chunks.append(arr)
    else:
        raw = tile_path.read_bytes()
        arr = np.loadtxt(raw.splitlines(), dtype=np.float64, ndmin=2)
        if arr.shape[1] != 3:
            raise ValueError(f"unexpected XYZ column count in {tile_path.name}")
        chunks.append(arr)
    return np.vstack(chunks) if len(chunks) > 1 else chunks[0]


def load_clipped_dgm1(
    config: dict,
    raw_dir: Path,
    frame: LocalFrame,
    clip_margin_m: float = DEFAULT_GRID_CLIP_MARGIN_M,
) -> tuple[np.ndarray, dict, list[dict]]:
    """
    Read DGM1 tiles from raw_dir/dgm1/, clip to local bounds + clip_margin_m,
    and convert NHN heights to local meters (nhn - reference_elevation_m).
    Returns (heights_local_f32 [rows_north, cols_east], terrain_meta, dgm_raw_files).
    """
    dgm_dir = raw_dir / "dgm1"
    sources_path = dgm_dir / "sources.json"
    if not sources_path.is_file():
        raise ValueError(
            f"missing DGM1 metadata {sources_path}; run 'python -m tools.geo_import fetch-dgm' first"
        )
    sources_meta = json.loads(sources_path.read_text(encoding="utf-8"))
    tiles = sources_meta.get("tiles") or []
    if not tiles:
        raise ValueError(f"no DGM1 tiles listed in {sources_path}")

    min_lon, min_lat, max_lon, max_lat = config["bounds_lonlat"]
    corners = [
        frame.transformer.transform(lon, lat, errcheck=True)
        for lon in (min_lon, max_lon)
        for lat in (min_lat, max_lat)
    ]
    spacing_m = float(sources_meta.get("grid_spacing_m", 1.0))
    if spacing_m != 1.0:
        raise ValueError(f"unsupported DGM grid spacing: {spacing_m}")

    # Load all tile points first so we align exactly to the DGM grid phase (e.g. .5 m cell centers).
    loaded_tiles = []
    raw_files = []
    for tile in sorted(tiles, key=lambda item: item["name"]):
        tile_path = dgm_dir / tile["name"]
        if not tile_path.is_file():
            raise ValueError(f"missing DGM1 tile file: {tile_path}")
        with tile_path.open("rb") as stream:
            actual_sha = file_digest(stream, "sha256").hexdigest()
        raw_files.append(
            {
                "name": f"dgm1/{tile['name']}",
                "tile_name": tile["name"],
                "url": tile.get("url", ""),
                "delivery_year": tile.get("delivery_year", sources_meta.get("delivery_year")),
                "sha256": actual_sha,
            }
        )
        pts = _read_xyz_points(tile_path)
        e_vals = pts[:, 0]
        n_vals = pts[:, 1]
        z_vals = pts[:, 2]
        if np.median(e_vals) > 30_000_000.0:
            e_vals = e_vals - 33_000_000.0
        loaded_tiles.append((e_vals, n_vals, z_vals))

    first_e, first_n, _ = loaded_tiles[0]
    e_phase = round(float(first_e[0] - floor(first_e[0])), 4)
    n_phase = round(float(first_n[0] - floor(first_n[0])), 4)

    e_min_utm = floor(min(c[0] for c in corners) - clip_margin_m) + e_phase
    e_max_utm = float(int(np.ceil(max(c[0] for c in corners) + clip_margin_m))) + e_phase
    n_min_utm = floor(min(c[1] for c in corners) - clip_margin_m) + n_phase
    n_max_utm = float(int(np.ceil(max(c[1] for c in corners) + clip_margin_m))) + n_phase

    cols = int(round(e_max_utm - e_min_utm)) + 1
    rows = int(round(n_max_utm - n_min_utm)) + 1
    nhn_grid = np.full((rows, cols), np.nan, dtype=np.float64)

    for e_vals, n_vals, z_vals in loaded_tiles:
        mask = (
            (e_vals >= e_min_utm - 0.05)
            & (e_vals <= e_max_utm + 0.05)
            & (n_vals >= n_min_utm - 0.05)
            & (n_vals <= n_max_utm + 0.05)
        )
        if not np.any(mask):
            continue
        col_idx = np.rint(e_vals[mask] - e_min_utm).astype(np.int64)
        row_idx = np.rint(n_vals[mask] - n_min_utm).astype(np.int64)
        valid = (col_idx >= 0) & (col_idx < cols) & (row_idx >= 0) & (row_idx < rows)
        nhn_grid[row_idx[valid], col_idx[valid]] = z_vals[mask][valid]

    missing_count = int(np.isnan(nhn_grid).sum())
    if missing_count > 0:
        raise ValueError(f"DGM1 clipped grid has {missing_count} missing cells in UTM window")

    # Compute or read versioned reference elevation (NHN)
    dgm_cfg = config.get("dgm") or {}
    origin_col = frame.easting - e_min_utm
    origin_row = frame.northing - n_min_utm
    c0 = int(floor(origin_col))
    r0 = int(floor(origin_row))
    fc = origin_col - c0
    fr = origin_row - r0
    origin_nhn = float(
        (1.0 - fr) * ((1.0 - fc) * nhn_grid[r0, c0] + fc * nhn_grid[r0, c0 + 1])
        + fr * ((1.0 - fc) * nhn_grid[r0 + 1, c0] + fc * nhn_grid[r0 + 1, c0 + 1])
    )
    if "reference_elevation_m" in dgm_cfg and dgm_cfg["reference_elevation_m"] is not None:
        reference_elevation_m = float(dgm_cfg["reference_elevation_m"])
        ref_source = str(dgm_cfg.get("reference_elevation_source", "manifest_versioned_origin_dgm1"))
    else:
        reference_elevation_m = round(origin_nhn, 3)
        ref_source = "computed_origin_dgm1"

    local_grid_f32 = (nhn_grid - reference_elevation_m).astype("<f4")
    grid_bytes = local_grid_f32.tobytes()
    grid_sha256 = sha256(grid_bytes).hexdigest()

    delivery_year = int(sources_meta.get("delivery_year", 2025))
    attribution = sources_meta.get("attribution", f"© GeoBasis-DE/M-V {delivery_year}")

    terrain_meta = {
        "kind": "dgm1",
        "vertical_crs": sources_meta.get("vertical_crs", "DHHN2016 (NHN)"),
        "reference_elevation_m": round(reference_elevation_m, 4),
        "reference_elevation_source": ref_source,
        "origin_nhn_m": round(origin_nhn, 4),
        "min_nhn_m": round(float(nhn_grid.min()), 4),
        "max_nhn_m": round(float(nhn_grid.max()), 4),
        "min_local_m": round(float(local_grid_f32.min()), 4),
        "max_local_m": round(float(local_grid_f32.max()), 4),
        "attribution": attribution,
        "license": sources_meta.get("license", "Creative Commons Namensnennung – 4.0 International (CC BY 4.0)"),
        "license_id": sources_meta.get("license_id", "cc-by/4.0"),
        "license_url": sources_meta.get("license_url", "https://creativecommons.org/licenses/by/4.0/"),
        "delivery_year": delivery_year,
        "assumptions": {
            "terrain_tile_size_m": float(dgm_cfg.get("terrain_tile_size_m", 64.0)),
            "terrain_max_error_m": float(dgm_cfg.get("terrain_max_error_m", 0.05)),
            "terrain_max_triangles": int(dgm_cfg.get("terrain_max_triangles", 150000)),
            "road_smoothing_window_m": float(dgm_cfg.get("road_smoothing_window_m", 12.0)),
            "water_bank_depression_m": float(dgm_cfg.get("water_bank_depression_m", 0.05)),
            # Sprint 14: finer tolerance only in the historic core (the Sprint 1-13 area), coarser outside
            **({"terrain_fine_bounds_lonlat": [float(v) for v in dgm_cfg["terrain_fine_bounds_lonlat"]],
                "terrain_outer_max_error_m": float(dgm_cfg.get("terrain_outer_max_error_m", 0.10))}
               if dgm_cfg.get("terrain_fine_bounds_lonlat") else {}),
        },
        "grid": {
            "file": "terrain-grid.bin",
            "dtype": "<f4",
            "order": "row_major_north_then_east",
            "rows": rows,
            "cols": cols,
            "spacing_m": spacing_m,
            "origin_local_east_m": round(float(e_min_utm - frame.easting), 6),
            "origin_local_north_m": round(float(n_min_utm - frame.northing), 6),
            "utm_easting_min_m": e_min_utm,
            "utm_northing_min_m": n_min_utm,
            "sha256": grid_sha256,
        },
    }
    return local_grid_f32, terrain_meta, raw_files
