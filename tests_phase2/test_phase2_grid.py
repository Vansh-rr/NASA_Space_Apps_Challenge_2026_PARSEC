from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyproj
import pytest

from phase1_modis import standardize_modis
from phase1_viirs import standardize_viirs
from phase2.phase2_grid import (
    GridConfig,
    aggregate_by_cell,
    assign_cells,
    build_crs,
    cell_index,
    grid_config_from_team,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_cell_index_interior() -> None:
    assert cell_index(0, 0, 5) == (0, 0)
    assert cell_index(2.5, 0, 5) == (0, 0)


def test_cell_index_border_rule() -> None:
    assert cell_index(5.0, 0, 5) == (1, 0)
    assert cell_index(-0.001, 0, 5) == (-1, 0)


def test_bbox_centre_projects_to_origin() -> None:
    config = GridConfig()
    crs = build_crs(config)
    west, south, east, north = config.bbox
    lon_0 = (west + east) / 2.0
    lat_0 = (south + north) / 2.0
    to_grid = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x_km, y_km = to_grid.transform(lon_0, lat_0)
    assert abs(x_km) < 1e-6
    assert abs(y_km) < 1e-6
    x_north_km, y_north_km = to_grid.transform(lon_0, lat_0 + 1.0)
    assert abs(x_north_km) < 0.001
    assert 110.0 <= y_north_km <= 112.5


def test_round_trip_assign_cells() -> None:
    config = GridConfig()
    crs = build_crs(config)
    to_lonlat = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = to_lonlat.transform(2.5, 2.5)
    df = _make_df([
        {
            "observation_id": "obs_rt_1",
            "latitude": float(lat),
            "longitude": float(lon),
            "sensor_family": "MODIS",
            "satellite": "Terra",
        }
    ])
    out = assign_cells(df, config, 5)
    assert len(out) == 1
    row = out.iloc[0]
    assert int(row["ix"]) == 0
    assert int(row["iy"]) == 0
    assert row["cell_id"] == "british_columbia_5km_0_0"


def test_assign_cells_deterministic() -> None:
    config = GridConfig()
    df = _make_df([
        {
            "observation_id": "obs_1",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        },
        {
            "observation_id": "obs_2",
            "latitude": 55.1,
            "longitude": -120.2,
            "sensor_family": "VIIRS",
            "satellite": "S-NPP",
        },
    ])
    first = assign_cells(df, config, 5)
    second = assign_cells(df, config, 5)
    pd.testing.assert_frame_equal(first, second)


def test_assign_cells_row_count_and_unique_observation_ids() -> None:
    config = GridConfig()
    df = _make_df([
        {
            "observation_id": f"obs_{i}",
            "latitude": 50.0 + i * 0.5,
            "longitude": -130.0 + i * 0.5,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        }
        for i in range(10)
    ])
    out = assign_cells(df, config, 5)
    assert list(out.columns) == [
        "observation_id",
        "cell_id",
        "cell_size_km",
        "ix",
        "iy",
        "grid_version",
    ]
    assert len(out) == len(df)
    assert out["observation_id"].nunique() == len(df)
    assert list(out["observation_id"]) == list(df["observation_id"])


def test_invalid_inputs_raise_value_error() -> None:
    config = GridConfig()
    base = {
        "observation_id": "obs_1",
        "latitude": 54.0,
        "longitude": -126.5,
        "sensor_family": "MODIS",
        "satellite": "Terra",
    }

    with pytest.raises(ValueError):
        assign_cells(_make_df([{**base, "latitude": np.nan}]), config, 5)

    with pytest.raises(ValueError):
        assign_cells(_make_df([{**base, "latitude": 95.0}]), config, 5)

    with pytest.raises(ValueError):
        assign_cells(_make_df([base]), config, 0)

    with pytest.raises(ValueError):
        cell_index(0.0, 0.0, 0)


def test_aggregate_by_cell_counts_by_sensor_and_satellite() -> None:
    config = GridConfig()
    rows = [
        {
            "observation_id": f"m_{i}",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        }
        for i in range(3)
    ] + [
        {
            "observation_id": f"v_{i}",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "VIIRS",
            "satellite": "S-NPP",
        }
        for i in range(2)
    ]
    df = _make_df(rows)
    assignments = assign_cells(df, config, 5)
    agg = aggregate_by_cell(df, assignments)

    assert list(agg.columns) == ["cell_id", "sensor_family", "satellite", "detections"]
    counts = dict(zip(agg["sensor_family"], agg["detections"]))
    assert counts == {"MODIS": 3, "VIIRS": 2}


def test_smoke_sample_data_all_cell_sizes() -> None:
    config = GridConfig()
    sample_dir = Path(__file__).parent.parent / "data" / "sample"
    modis_csv = next(sample_dir.glob("*MODIS*.csv"))
    viirs_csv = next(sample_dir.glob("*VIIRS*.csv"))

    modis_df = standardize_modis(pd.read_csv(modis_csv))
    viirs_df = standardize_viirs(pd.read_csv(viirs_csv))

    assert len(modis_df) == 200
    assert len(viirs_df) == 200

    for df in (modis_df, viirs_df):
        for size_km in config.cell_sizes_km:
            assigned = assign_cells(df, config, size_km)
            assert len(assigned) == 200
            assert assigned["observation_id"].nunique() == 200
            assert not assigned["cell_id"].isna().any()


def test_build_grid_cells_area_within_one_percent() -> None:
    from phase2.phase2_grid import build_grid_cells

    config = GridConfig()
    df = _make_df([
        {
            "observation_id": f"obs_{i}",
            "latitude": 50.0 + i * 1.5,
            "longitude": -135.0 + i * 3.0,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        }
        for i in range(6)
    ])
    for size_km in config.cell_sizes_km:
        assignments = assign_cells(df, config, size_km)
        cells = build_grid_cells(assignments, config)
        expected = float(size_km) ** 2
        rel_err = (cells["area_km2"] - expected).abs() / expected
        assert (rel_err <= 0.01).all()


def test_build_grid_cells_one_row_per_distinct_cell_id() -> None:
    from phase2.phase2_grid import build_grid_cells

    config = GridConfig()
    df = _make_df([
        {
            "observation_id": "obs_1",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        },
        {
            "observation_id": "obs_2",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "VIIRS",
            "satellite": "S-NPP",
        },
        {
            "observation_id": "obs_3",
            "latitude": 55.5,
            "longitude": -122.0,
            "sensor_family": "MODIS",
            "satellite": "Aqua",
        },
    ])
    assignments = assign_cells(df, config, 5)
    cells = build_grid_cells(assignments, config)
    assert len(cells) == assignments["cell_id"].nunique()
    assert cells["cell_id"].nunique() == len(cells)
    assert set(cells["cell_id"]) == set(assignments["cell_id"])


def test_export_grid_writes_and_reads_back_row_counts(tmp_path: Path) -> None:
    import geopandas as gpd
    from phase2.phase2_grid import build_grid_cells, export_grid

    config = GridConfig()
    df = _make_df([
        {
            "observation_id": "obs_1",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        },
        {
            "observation_id": "obs_2",
            "latitude": 54.0,
            "longitude": -126.5,
            "sensor_family": "VIIRS",
            "satellite": "S-NPP",
        },
        {
            "observation_id": "obs_3",
            "latitude": 55.5,
            "longitude": -122.0,
            "sensor_family": "MODIS",
            "satellite": "Aqua",
        },
    ])
    assignments = assign_cells(df, config, 5)
    cells = build_grid_cells(assignments, config)
    export_grid(cells, assignments, tmp_path)

    cells_back = gpd.read_parquet(tmp_path / "grid_cells.parquet")
    assignments_back = pd.read_parquet(tmp_path / "grid_observations.parquet")
    assert len(cells_back) == len(cells)
    assert len(assignments_back) == len(assignments)


def test_grid_config_from_team_default() -> None:
    from phase2.phase2_config import load_config

    team_cfg = load_config()
    cfg = grid_config_from_team()
    assert cfg.region_name == "british_columbia"
    assert cfg.grid_version == "v2"
    assert cfg.bbox == team_cfg.region("british_columbia").bbox
    assert cfg.cell_sizes_km == tuple(team_cfg.grid.cell_sizes_km)


def test_grid_config_from_team_bc_dev() -> None:
    from phase2.phase2_config import load_config

    team_cfg = load_config()
    cfg = grid_config_from_team("bc_dev")
    assert cfg.region_name == "bc_dev"
    assert cfg.bbox == team_cfg.region("bc_dev").bbox


def test_grid_config_from_team_unknown_region() -> None:
    with pytest.raises(ValueError):
        grid_config_from_team("atlantis")


def test_assign_cells_differs_between_regions() -> None:
    df = _make_df([
        {
            "observation_id": "obs_1",
            "latitude": 53.0,
            "longitude": -121.5,
            "sensor_family": "MODIS",
            "satellite": "Terra",
        }
    ])
    bc_id = assign_cells(df, grid_config_from_team("british_columbia"), 5).iloc[0]["cell_id"]
    dev_id = assign_cells(df, grid_config_from_team("bc_dev"), 5).iloc[0]["cell_id"]
    assert bc_id.startswith("british_columbia_5km_")
    assert dev_id.startswith("bc_dev_5km_")
    assert bc_id != dev_id


def test_grid_config_default_version_v2() -> None:
    assert GridConfig().grid_version == "v2"


