"""A small independent check of the existing raw sensor comparison module."""
import numpy as np
import pandas as pd
from phase2.phase2_sensor_comparison import (build_comparison_pairs, compute_comparison_stats,
                                             aggregate_groups)


def test_raw_comparison_and_group_frp():
    matched = pd.DataFrame([dict(match_group_id='m', region='r', modis_observation_id='M',
        viirs_observation_id=v, modis_satellite='Aqua', viirs_satellite='S-NPP', daynight='D',
        distance_km=.3, time_diff_minutes=10, n_viirs_in_group=2, dataset_version='fixture')
        for v in ['V1', 'V2']])
    observations = pd.DataFrame([dict(observation_id=i, frp_mw=f, acq_date='2023-07-01',
            confidence_numeric=c, confidence_class=k) for i, f, c, k in
            [('M', 40., 80, None), ('V1', 10., None, 'nominal'), ('V2', 20., None, 'high')]])
    pairs = build_comparison_pairs(matched, observations)
    assert len(pairs) == 2
    assert np.allclose(pairs.log_frp_ratio, np.log([.25, .5]))
    groups = aggregate_groups(pairs)
    assert groups.viirs_frp_sum_mw.iloc[0] == 30
    assert groups.modis_frp_mw.iloc[0] == 40
    assert compute_comparison_stats(pairs).n_pairs.iloc[0] == 2
