from datetime import date
import numpy as np
import pandas as pd
import pytest

from phase2 import phase2_schema
from phase2.phase2_coverage import (
    COVERAGE_PRODUCT_VERSION,
    COVERAGE_STATES,
    build_coverage_rows,
    coverage_version,
    get_coverage,
    satellite_available,
    validate_coverage,
)


def _keys(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=['cell_id', 'satellite', 'window_start'])


def _cov_rows(*rows) -> pd.DataFrame:
    ver = coverage_version()
    full = [
        (cell_id, sat, dt, 'day', state, frac, src, ver)
        for cell_id, sat, dt, state, frac, src in rows
    ]
    return pd.DataFrame(full, columns=phase2_schema.columns_of('observation_coverage'))


def test_1_no_data():
    out = get_coverage(_keys(('c1', 'S-NPP', '2023-07-15')), coverage=None)
    assert len(out) == 1
    row = out.iloc[0]
    assert row['state'] == 'unknown'
    assert np.isnan(row['observed_fraction'])
    assert row['source'] == 'none'


def test_2_satellite_not_yet_flying():
    out = get_coverage(_keys(('c1', 'S-NPP', '2010-07-15')))
    row = out.iloc[0]
    assert row['state'] == 'unavailable'
    assert row['observed_fraction'] == 0.0
    assert row['source'] == 'sensor_availability'


def test_3_boundary_terra():
    avail = satellite_available('Terra', ['2000-02-23', date(2000, 2, 24)])
    assert avail.dtype == bool
    assert list(avail) == [False, True]

    out = get_coverage(_keys(('c1', 'Terra', '2000-02-23'), ('c1', 'Terra', date(2000, 2, 24))))
    assert out.iloc[0]['state'] == 'unavailable'
    assert out.iloc[1]['state'] != 'unavailable'


def test_4_real_rows():
    cov1 = _cov_rows(
        ('c1', 'S-NPP', '2023-07-15', 'observed', 0.7, 'mod09'),
        ('c1', 'S-NPP', '2023-07-15', 'cloudy', 0.3, 'mod09'),
    )
    out1 = get_coverage(_keys(('c1', 'S-NPP', '2023-07-15')), coverage=cov1).iloc[0]
    assert out1['state'] == 'observed'
    assert out1['observed_fraction'] == pytest.approx(0.7)
    assert out1['source'] == 'mod09'

    cov2 = _cov_rows(
        ('c1', 'S-NPP', '2023-07-15', 'observed', 0.2, 'mod09'),
        ('c1', 'S-NPP', '2023-07-15', 'cloudy', 0.8, 'cloud_mask'),
    )
    out2 = get_coverage(_keys(('c1', 'S-NPP', '2023-07-15')), coverage=cov2).iloc[0]
    assert out2['state'] == 'cloudy'
    assert out2['observed_fraction'] == pytest.approx(0.2)
    assert out2['source'] == 'cloud_mask'


def test_5_tie_prefers_cloudy_over_observed():
    cov = _cov_rows(
        ('c1', 'S-NPP', '2023-07-15', 'observed', 0.5, 'obs_src'),
        ('c1', 'S-NPP', '2023-07-15', 'cloudy', 0.5, 'cld_src'),
    )
    out = get_coverage(_keys(('c1', 'S-NPP', '2023-07-15')), coverage=cov).iloc[0]
    assert out['state'] == 'cloudy'
    assert out['observed_fraction'] == pytest.approx(0.5)
    assert out['source'] == 'cld_src'


def test_6_unavailable_wins_over_coverage_rows():
    cov = _cov_rows(('c1', 'S-NPP', '2010-07-15', 'observed', 1.0, 'bad_row'))
    out = get_coverage(_keys(('c1', 'S-NPP', '2010-07-15')), coverage=cov).iloc[0]
    assert out['state'] == 'unavailable'
    assert out['observed_fraction'] == 0.0
    assert out['source'] == 'sensor_availability'


def test_7_order_and_count_five_keys():
    keys = _keys(
        ('c5', 'S-NPP', '2023-07-15'),   # unknown
        ('c2', 'S-NPP', '2010-01-01'),   # unavailable
        ('c1', 'Terra', '2023-07-15'),   # known observed
        ('c4', 'Aqua', '2001-05-01'),    # unavailable
        ('c3', 'Aqua', '2023-07-15'),    # known cloudy (no observed row -> observed_fraction 0.0)
    )
    cov = _cov_rows(
        ('c1', 'Terra', '2023-07-15', 'observed', 0.9, 'terra_src'),
        ('c3', 'Aqua', '2023-07-15', 'cloudy', 1.0, 'aqua_src'),
    )
    out = get_coverage(keys, coverage=cov)
    assert len(out) == 5
    assert list(out['cell_id']) == ['c5', 'c2', 'c1', 'c4', 'c3']
    assert list(out['state']) == ['unknown', 'unavailable', 'observed', 'unavailable', 'cloudy']
    assert np.isnan(out.iloc[0]['observed_fraction'])
    assert out.iloc[1]['observed_fraction'] == 0.0
    assert out.iloc[2]['observed_fraction'] == pytest.approx(0.9)
    assert out.iloc[3]['observed_fraction'] == 0.0
    assert out.iloc[4]['observed_fraction'] == 0.0


def test_8_validate_coverage_errors():
    base = _cov_rows(('c1', 'S-NPP', '2023-07-15', 'observed', 0.5, 'src'))
    validate_coverage(base)

    # fraction > 1
    bad_hi = _cov_rows(('c1', 'S-NPP', '2023-07-15', 'observed', 1.2, 'src'))
    with pytest.raises(ValueError):
        validate_coverage(bad_hi)

    # fraction < 0
    bad_lo = _cov_rows(('c1', 'S-NPP', '2023-07-15', 'observed', -0.1, 'src'))
    with pytest.raises(ValueError):
        validate_coverage(bad_lo)

    # invalid state
    bad_state = _cov_rows(('c1', 'S-NPP', '2023-07-15', 'sunny', 0.5, 'src'))
    with pytest.raises(ValueError):
        validate_coverage(bad_state)

    # missing column
    with pytest.raises(ValueError):
        validate_coverage(base.drop(columns=['source']))

    # fractions sum > 1.000001 for one key
    bad_sum = _cov_rows(
        ('c1', 'S-NPP', '2023-07-15', 'observed', 0.7, 'src'),
        ('c1', 'S-NPP', '2023-07-15', 'cloudy', 0.6, 'src'),
    )
    with pytest.raises(ValueError):
        validate_coverage(bad_sum)


def test_9_unknown_satellite_and_duplicate_keys():
    with pytest.raises(ValueError):
        satellite_available('Landsat', ['2023-07-15'])

    with pytest.raises(ValueError):
        get_coverage(_keys(('c1', 'Landsat', '2023-07-15')))

    dup = _keys(('c1', 'S-NPP', '2023-07-15'), ('c1', 'S-NPP', date(2023, 7, 15)))
    with pytest.raises(ValueError):
        get_coverage(dup)
    with pytest.raises(ValueError):
        build_coverage_rows(dup)


def test_10_build_coverage_rows():
    assert COVERAGE_STATES == ('observed', 'cloudy', 'unavailable', 'unknown')
    assert COVERAGE_PRODUCT_VERSION == '2.8.0'

    keys = _keys(('c1', 'S-NPP', '2023-07-15'), ('c2', 'S-NPP', '2010-07-15'))
    rows = build_coverage_rows(keys)
    assert list(rows.columns) == phase2_schema.columns_of('observation_coverage')
    assert (rows['fraction'] == 1.0).all()
    assert set(rows['state']) <= {'unknown', 'unavailable'}
    assert list(rows['state']) == ['unknown', 'unavailable']
    assert (rows['dataset_version'] == coverage_version()).all()
    validate_coverage(rows)


def test_11_empty_keys():
    empty = _keys()
    out_get = get_coverage(empty)
    assert out_get.empty
    assert list(out_get.columns) == [
        'cell_id', 'satellite', 'window_start', 'time_window', 'state', 'observed_fraction', 'source'
    ]

    out_build = build_coverage_rows(empty)
    assert out_build.empty
    assert list(out_build.columns) == phase2_schema.columns_of('observation_coverage')


def test_12_missing_window_start():
    for bad_ws in (None, pd.NaT):
        k = _keys(('c1', 'S-NPP', bad_ws))
        with pytest.raises(ValueError):
            get_coverage(k)
        with pytest.raises(ValueError):
            build_coverage_rows(k)


def test_13_missing_cell_id():
    k = _keys((None, 'S-NPP', '2023-07-15'))
    with pytest.raises(ValueError):
        get_coverage(k)
    with pytest.raises(ValueError):
        build_coverage_rows(k)


def test_14_multiple_dataset_versions():
    cov = pd.DataFrame(
        [
            ('c1', 'S-NPP', '2023-07-15', 'day', 'observed', 0.9, 'old', 'v_old'),
            ('c1', 'S-NPP', '2023-07-15', 'day', 'cloudy', 0.8, 'new', 'v_new'),
        ],
        columns=phase2_schema.columns_of('observation_coverage'),
    )
    with pytest.raises(ValueError):
        get_coverage(_keys(('c1', 'S-NPP', '2023-07-15')), coverage=cov)


def test_15_single_version_observed_fraction_bounds():
    keys = _keys(
        ('c1', 'S-NPP', '2023-07-15'),
        ('c2', 'S-NPP', '2023-07-15'),
        ('c3', 'S-NPP', '2010-07-15'),
    )
    cov = _cov_rows(
        ('c1', 'S-NPP', '2023-07-15', 'observed', 0.6, 'src'),
        ('c1', 'S-NPP', '2023-07-15', 'cloudy', 0.4, 'src'),
    )
    out = get_coverage(keys, coverage=cov)
    fracs = out['observed_fraction'].dropna()
    assert len(fracs) > 0
    assert ((fracs >= 0.0) & (fracs <= 1.0)).all()