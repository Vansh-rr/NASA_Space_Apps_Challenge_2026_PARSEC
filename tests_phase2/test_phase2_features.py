from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase2.phase2_config import load_config
from phase2.phase2_features import EXTRA_COLUMNS, build_matched_features
from phase2.phase2_schema import columns_of


def _make_inputs(
    groups: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build synthetic matched and observations DataFrames from group specs."""
    matched_rows = []
    obs_rows = {}

    for g in groups:
        mg_id = g.get('match_group_id', 'mg_1')
        region = g.get('region', 'british_columbia')
        m_id = g.get('modis_id', f'm_{mg_id}')
        m_sat = g.get('modis_satellite', 'Terra')
        daynight = g.get('daynight', 'D')
        m_time = g.get('modis_time', '2023-07-15T18:40:00Z')
        m_date = g.get('modis_date', '2023-07-15')

        obs_rows[m_id] = {
            'observation_id': m_id,
            'acq_datetime_utc': m_time,
            'acq_date': m_date,
            'frp_mw': g.get('modis_frp', 50.0),
            'scan_km': g.get('modis_scan', 1.0),
            'track_km': g.get('modis_track', 1.0),
            'pixel_area_km2': g.get('modis_area', 1.0),
            'delta_bt_k': g.get('modis_dbt', 30.0),
            'confidence_numeric': g.get('modis_conf', 80.0),
        }

        for i, v in enumerate(g.get('viirs', [])):
            v_id = v.get('id', f'v_{mg_id}_{i}')
            matched_rows.append({
                'match_group_id': mg_id,
                'region': region,
                'modis_observation_id': m_id,
                'viirs_observation_id': v_id,
                'modis_satellite': m_sat,
                'daynight': daynight,
                'distance_km': v.get('distance_km', 0.4),
            })
            if not v.get('missing_from_obs', False):
                obs_rows[v_id] = {
                    'observation_id': v_id,
                    'acq_datetime_utc': v.get('time', '2023-07-15T18:50:00Z'),
                    'acq_date': v.get('date', m_date),
                    'frp_mw': v.get('frp', 10.0),
                    'scan_km': v.get('scan', 0.4),
                    'track_km': v.get('track', 0.4),
                    'pixel_area_km2': v.get('area', 0.16),
                    'delta_bt_k': v.get('dbt', 25.0),
                    'confidence_numeric': v.get('conf', 80.0),
                }

    matched_cols = [
        'match_group_id', 'region', 'modis_observation_id',
        'viirs_observation_id', 'modis_satellite', 'daynight', 'distance_km',
    ]
    obs_cols = [
        'observation_id', 'acq_datetime_utc', 'acq_date', 'frp_mw',
        'scan_km', 'track_km', 'pixel_area_km2', 'delta_bt_k', 'confidence_numeric',
    ]
    matched_df = pd.DataFrame(matched_rows, columns=matched_cols)
    obs_df = pd.DataFrame(list(obs_rows.values()), columns=obs_cols)
    return matched_df, obs_df


def test_known_sums():
    matched, obs = _make_inputs([{
        'viirs': [{'frp': 10.0}, {'frp': 20.0}, {'frp': 30.0}],
    }])
    out = build_matched_features(matched, obs)
    row = out.iloc[0]
    assert row['viirs_frp_sum_mw'] == pytest.approx(60.0)
    assert row['viirs_frp_max_mw'] == pytest.approx(30.0)
    assert row['n_viirs'] == 3
    assert row['n_viirs_with_frp'] == 3


def test_signed_gap_positive():
    matched, obs = _make_inputs([{
        'modis_time': '2023-07-15T18:40:00Z',
        'viirs': [
            {'time': '2023-07-15T19:12:00Z'},
            {'time': '2023-07-15T19:12:00Z'},
        ],
    }])
    out = build_matched_features(matched, obs)
    row = out.iloc[0]
    assert row['time_gap_minutes_signed'] == pytest.approx(32.0)
    assert row['time_diff_minutes'] == pytest.approx(32.0)


def test_signed_gap_reversed():
    matched, obs = _make_inputs([{
        'modis_time': '2023-07-15T19:12:00Z',
        'viirs': [
            {'time': '2023-07-15T18:40:00Z'},
            {'time': '2023-07-15T18:40:00Z'},
        ],
    }])
    out = build_matched_features(matched, obs)
    row = out.iloc[0]
    assert row['time_gap_minutes_signed'] == pytest.approx(-32.0)
    assert row['time_diff_minutes'] == pytest.approx(32.0)


def test_pixel_size():
    matched, obs = _make_inputs([{
        'modis_scan': 1.6,
        'modis_track': 1.2,
        'modis_area': 1.92,
        'viirs': [{'area': 0.15}, {'area': 0.16}],
    }])
    out = build_matched_features(matched, obs)
    row = out.iloc[0]
    assert row['modis_scan_km'] == pytest.approx(1.6)
    assert row['modis_track_km'] == pytest.approx(1.2)
    assert row['modis_pixel_area_km2'] == pytest.approx(1.92)
    assert row['viirs_pixel_area_sum_km2'] == pytest.approx(0.31)


def test_missing_is_not_zero():
    matched, obs = _make_inputs([
        {
            'match_group_id': 'mg_all_nan',
            'viirs': [{'frp': np.nan}, {'frp': np.nan}],
        },
        {
            'match_group_id': 'mg_partial_nan',
            'viirs': [{'frp': 10.0}, {'frp': np.nan}],
        },
    ])
    out = build_matched_features(matched, obs).set_index('match_group_id')

    all_nan = out.loc['mg_all_nan']
    assert pd.isna(all_nan['viirs_frp_sum_mw'])
    assert all_nan['n_viirs_with_frp'] == 0
    assert all_nan['n_viirs'] == 2

    partial = out.loc['mg_partial_nan']
    assert partial['viirs_frp_sum_mw'] == pytest.approx(10.0)
    assert partial['n_viirs_with_frp'] == 1
    assert partial['n_viirs'] == 2


def test_two_groups_unique_rows():
    matched, obs = _make_inputs([
        {'match_group_id': 'mg_a', 'viirs': [{'frp': 12.0}]},
        {'match_group_id': 'mg_b', 'viirs': [{'frp': 15.0}, {'frp': 25.0}]},
    ])
    out = build_matched_features(matched, obs)
    assert len(out) == 2
    assert out['match_group_id'].nunique() == 2
    assert set(out['match_group_id']) == {'mg_a', 'mg_b'}


def test_unknown_viirs_observation_id_raises():
    matched, obs = _make_inputs([{
        'viirs': [{'id': 'v_missing', 'missing_from_obs': True}],
    }])
    with pytest.raises(ValueError, match='1'):
        build_matched_features(matched, obs)


def test_empty_input():
    matched, obs = _make_inputs([])
    out = build_matched_features(matched, obs)
    assert out.empty
    assert list(out.columns) == columns_of('matched_features') + list(EXTRA_COLUMNS)


def test_column_contract():
    matched, obs = _make_inputs([{'viirs': [{'frp': 10.0}]}])
    cfg = load_config()
    out = build_matched_features(matched, obs, cfg=cfg)
    expected_first_16 = columns_of('matched_features')
    assert len(expected_first_16) == 16
    assert list(out.columns[:16]) == expected_first_16
    assert list(out.columns[16:]) == list(EXTRA_COLUMNS)
    assert (out['dataset_version'] == cfg.version('features')).all()
