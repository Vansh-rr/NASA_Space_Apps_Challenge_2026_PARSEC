from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
from shapely.geometry import Polygon

from phase1_storage import DATA_DIR
from phase2.phase2_config import Phase2Config, load_config


@dataclass(frozen=True)
class GridConfig:
    """Configuration for the Phase 2 equal-area spatial grid."""

    region_name: str = "british_columbia"
    bbox: tuple[float, float, float, float] = (-139.0, 48.0, -114.0, 60.0)
    cell_sizes_km: tuple[int | float, ...] = (1, 5, 10)
    grid_version: str = "v2"
    lat_bounds: tuple[float, float] = (-90.0, 90.0)
    lon_bounds: tuple[float, float] = (-180.0, 180.0)
    geographic_crs: str = "EPSG:4326"


def grid_config_from_team(
    region: str | None = None,
    cfg: Phase2Config | None = None,
) -> GridConfig:
    """Build a GridConfig from the team Phase 2 configuration."""
    if cfg is None:
        cfg = load_config()
    region_key = region if region is not None else cfg.default_region
    reg = cfg.region(region_key)
    return GridConfig(
        region_name=region_key,
        bbox=reg.bbox,
        cell_sizes_km=tuple(cfg.grid.cell_sizes_km),
        grid_version="v2",
    )


def build_crs(config: GridConfig) -> pyproj.CRS:
    """Build a Lambert Azimuthal Equal Area CRS in kilometres centred on config.bbox."""
    west, south, east, north = config.bbox
    lon_0 = float(np.mean([west, east]))
    lat_0 = float(np.mean([south, north]))
    return pyproj.CRS.from_proj4(
        f"+proj=laea +lat_0={lat_0} +lon_0={lon_0} +datum=WGS84 +units=km +no_defs"
    )


def cell_index(
    x_km: np.ndarray | float,
    y_km: np.ndarray | float,
    cell_size_km: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute half-open integer cell indices (ix, iy) from projected km coordinates."""
    if not np.isfinite(cell_size_km) or cell_size_km <= 0:
        raise ValueError(f"cell_size_km must be positive, got {cell_size_km!r}")
    x_arr = np.asarray(x_km, dtype=float)
    y_arr = np.asarray(y_km, dtype=float)
    if not (np.all(np.isfinite(x_arr)) and np.all(np.isfinite(y_arr))):
        raise ValueError("Projected coordinates must be finite numbers.")
    ix = np.floor(x_arr / cell_size_km).astype(np.int64)
    iy = np.floor(y_arr / cell_size_km).astype(np.int64)
    return ix, iy


def assign_cells(
    df: pd.DataFrame,
    config: GridConfig,
    cell_size_km: float,
) -> pd.DataFrame:
    """Project detections and assign each row to a deterministic grid cell."""
    if not np.isfinite(cell_size_km) or cell_size_km <= 0:
        raise ValueError(f"cell_size_km must be positive, got {cell_size_km!r}")

    required = {"observation_id", "latitude", "longitude"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df["observation_id"].isna().any():
        raise ValueError("observation_id contains missing values.")

    lat = pd.to_numeric(df["latitude"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["longitude"], errors="coerce").to_numpy(dtype=float)

    if not (np.all(np.isfinite(lat)) and np.all(np.isfinite(lon))):
        raise ValueError("Coordinates contain NaN or non-finite values.")

    min_lat, max_lat = config.lat_bounds
    min_lon, max_lon = config.lon_bounds
    if np.any((lat < min_lat) | (lat > max_lat)):
        raise ValueError(f"latitude out of bounds [{min_lat}, {max_lat}].")
    if np.any((lon < min_lon) | (lon > max_lon)):
        raise ValueError(f"longitude out of bounds [{min_lon}, {max_lon}].")

    crs = build_crs(config)
    transformer = pyproj.Transformer.from_crs(
        config.geographic_crs, crs, always_xy=True
    )
    x_km, y_km = transformer.transform(lon, lat)
    ix, iy = cell_index(x_km, y_km, cell_size_km)

    ix_series = pd.Series(ix, index=df.index, dtype="int64")
    iy_series = pd.Series(iy, index=df.index, dtype="int64")
    prefix = f"{config.region_name}_{cell_size_km:g}km_"
    cell_id = (
        prefix + ix_series.astype(str) + "_" + iy_series.astype(str)
    )

    return pd.DataFrame(
        {
            "observation_id": df["observation_id"].to_numpy(),
            "cell_id": cell_id.to_numpy(),
            "cell_size_km": cell_size_km,
            "ix": ix,
            "iy": iy,
            "grid_version": config.grid_version,
        }
    )


def aggregate_by_cell(
    df: pd.DataFrame,
    assignments: pd.DataFrame,
) -> pd.DataFrame:
    """Count detections per (cell_id, sensor_family, satellite)."""
    merged = assignments[["observation_id", "cell_id"]].merge(
        df[["observation_id", "sensor_family", "satellite"]],
        on="observation_id",
        how="inner",
        validate="one_to_one",
    )
    grouped = (
        merged.groupby(
            ["cell_id", "sensor_family", "satellite"],
            as_index=False,
             dropna=False,
        )
        .size()
        .rename(columns={"size": "detections"})
    )
    return grouped[["cell_id", "sensor_family", "satellite", "detections"]]


def build_grid_cells(
    assignments: pd.DataFrame,
    config: GridConfig,
) -> gpd.GeoDataFrame:
    """Build unique cell polygons and geodesic areas for cells present in assignments."""
    cols = [
        "cell_id",
        "region_name",
        "cell_size_km",
        "ix",
        "iy",
        "centroid_lat",
        "centroid_lon",
        "area_km2",
        "grid_version",
        "geometry",
    ]
    if assignments.empty:
        return gpd.GeoDataFrame(
            {c: [] for c in cols}, geometry="geometry", crs=config.geographic_crs
        )

    unique = (
        assignments[["cell_id", "cell_size_km", "ix", "iy", "grid_version"]]
        .drop_duplicates(subset=["cell_id"])
        .reset_index(drop=True)
    )

    crs = build_crs(config)
    to_geo = pyproj.Transformer.from_crs(
        crs, config.geographic_crs, always_xy=True
    )
    geod = pyproj.Geod(ellps="WGS84")

    size = unique["cell_size_km"].to_numpy(dtype=float)
    ix = unique["ix"].to_numpy(dtype=np.int64)
    iy = unique["iy"].to_numpy(dtype=np.int64)

    x0 = ix * size
    x1 = (ix + 1) * size
    y0 = iy * size
    y1 = (iy + 1) * size
    cx = (ix + 0.5) * size
    cy = (iy + 0.5) * size

    centroid_lon, centroid_lat = to_geo.transform(cx, cy)
    lon00, lat00 = to_geo.transform(x0, y0)
    lon10, lat10 = to_geo.transform(x1, y0)
    lon11, lat11 = to_geo.transform(x1, y1)
    lon01, lat01 = to_geo.transform(x0, y1)

    geometries = []
    areas_km2 = []
    for i in range(len(unique)):
        poly = Polygon(
            [
                (lon00[i], lat00[i]),
                (lon10[i], lat10[i]),
                (lon11[i], lat11[i]),
                (lon01[i], lat01[i]),
            ]
        )
        area_m2, _ = geod.geometry_area_perimeter(poly)
        geometries.append(poly)
        areas_km2.append(abs(area_m2) / 1e6)

    return gpd.GeoDataFrame(
        {
            "cell_id": unique["cell_id"],
            "region_name": config.region_name,
            "cell_size_km": unique["cell_size_km"],
            "ix": unique["ix"],
            "iy": unique["iy"],
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "area_km2": areas_km2,
            "grid_version": unique["grid_version"],
            "geometry": geometries,
        },
        geometry="geometry",
        crs=config.geographic_crs,
    )


def export_grid(
    grid_cells: gpd.GeoDataFrame,
    assignments: pd.DataFrame,
    out_dir: str | Path | None = None,
) -> None:
    """Write grid_cells as GeoParquet and assignments as Parquet to out_dir."""
    out_path = DATA_DIR / "phase2" / "grid" if out_dir is None else Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    grid_cells.to_parquet(out_path / "grid_cells.parquet", index=False)
    assignments.to_parquet(out_path / "grid_observations.parquet", index=False)


