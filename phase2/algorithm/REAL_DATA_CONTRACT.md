# Unified scientific data contract

All input identifiers must be unique in their relevant table, and use letters, digits, `_`, `-`, `.`, `:`, `+` (max 190 chars). UTC timestamps must have explicit offsets in JSON bundles; output times are bin starts. MW = cell-total or footprint-total radiative power, not MW/km², temperature or area. Group IDs should encode independent event/region/time clusters; calibration and holdout groups must not overlap. Evidence text is a review attestation, not automated proof.

## Numeric C text format

`field.txt` is whitespace-separated, no headers beyond the explicit magic/version of the **format** (not algorithm version). Line structure:

```
PARSEC_FIELD1 SOURCE_KIND NCELLS NTIMES NLEVELS NOBS NEDGES
LEVEL0 LEVEL1 ...
PRIOR PERSISTENCE NEIGHBOR MU_LOG_FRP SD_LOG_FRP
CELL_ID_0 CELL_ID_1 ...
TIME_ID_0 TIME_ID_1 ...
EDGE_I EDGE_J
... (NEDGES edges, i<j)
OBS_ID GROUP_ID TIME_INDEX SENSOR USABLE DETECTED FRP_MW HOLDOUT NWEIGHTS CELL_IDX WEIGHT ...
... (NOBS rows)
```

Indices 0-based, sensor 0=MODIS, 1=VIIRS. Usable 0 requires detected=-1 and FRP=-1; usable 1 requires detected 0/1, FRP=-1 or strictly positive only with detected=1. Holdout 1 excludes the observation from inference; its group may not occur in train. NWEIGHTS >=1, indices sorted unique, each weight in (0,1]. Geometry must fully cover the footprint; no renormalization. Source kinds SYNTHETIC, REAL_REVIEWED, NASA_MASK_EXPLORATORY; exploratory must omit FRP and use illustrative parameters. Real VIIRS FRP refused. Numeric input alone cannot verify real geometry or scientific provenance, so use the reviewed adapter. Levels start at zero and strictly increase. Bounds: 1..3000 cells, 1..500 bins, 2..32 levels, 1..200000 observations; numerical memory/cost guards may impose lower limits. Spatial graph is undirected. Default dynamics `.2 2.4 .9 3 .8` per bin, not calibrated to arbitrary bin width or cell area. Fixed prior not inherited from positive-pair calibration.

`pairs.txt`: `PAIRS1 SOURCE_KIND N`, followed by `group_id modis_frp_mw viirs_frp_mw`. At least 30. `labels.txt`: `LABELS1 SOURCE_KIND N`, followed by `group_id sensor truth_fire reference_frp_mw usable detected`. Positive truth requires positive FRP, nonfire requires zero verified FRP, unavailable requires detected=-1. At least 30 usable fire and 30 usable nonfire per sensor. Real CSV adapter below preserves metadata. Calibration file `params.txt` is generated only after all diagnostic checks pass: `PARSEC_PARAMS1 SOURCE_KIND N_DRAWS N_GROUPS`, group IDs then rows with seven values per sensor (alpha, slope, false_alarm, log_bias, log_sd, false_frp_log_mean, false_frp_log_sd), MODIS first. False-positive FRP log mean and SD remain fixed illustrative assumptions (1,.8); scientifically review or revise them before physical use.

## Reviewed calibration CSVs

`reviewed_pairs.csv` fields: `pair_id,group_id,modis_frp_mw,viirs_frp_mw,support_evidence`. Pairs must be near-synchronous and share physical support; do not simply match nearby center coordinates or double-count VIIRS 375m retrievals sharing a 750m retrieval. Relative calibration sets VIIRS bias zero, not absolute truth. `reference_calibration.csv` fields: `reference_id,group_id,sensor,truth_fire,reference_frp_mw,usable,detected,reference_source,support_evidence,time_evidence`. sensor `modis` or `viirs`; detected blank if unusable. All reference labels and FRP must be independently supplied and matched to instrument support and time. Do not use target NASA detections as ground truth. For nonfire 0 FRP must be verified, not unknown. Unknown labels excluded with documented sampling design. `calibration_protocol.json` keys: `source_kind: REAL_REVIEWED`, `review_evidence`, `reference_independence_evidence`, `frp_scale_evidence`, `support_time_evidence`, `calibration_groups` (all group IDs). Explicitly establish compatible scale between independently labeled FRP and VIIRS-relative paired calibration. The adapter refuses obvious target-sensor source names; this is not a proof of independence.

## Reviewed geometry JSON

Top-level: `source_kind: REAL_REVIEWED`, `review_evidence`, `calibration_evidence`, `area_crs` (equal-area projected metre CRS, e.g. EPSG:6933 for regional pilot), `start_utc` (ISO UTC with offset), `bin_seconds` integer, `n_bins` integer, `levels_mw` array, `dynamics` optional keys prior,persistence,neighbor,mu,sd, `cells`, `observations`. No `truth_mw`. `cells` objects `{cell_id, geometry}` with WGS84 GeoJSON Polygon/MultiPolygon and non-overlapping cells. `observations` objects `observation_id,group_id,sensor,satellite,product,source_granule,geometry,acquisition_utc,usable,detected,frp_mw,holdout,geometry_quality,footprint_evidence,time_basis` (and `frp_support_evidence` when FRP present). Unavailable detection/FRP null; no-fire FRP null; detected may have missing FRP. Geometry quality reviewed_polygon or reviewed_approximate. Real FRP allowed only MODIS, reviewed pixel UTC and retrieval support. VIIRS 375m detection and 750m FRP retrieval support must be separately modeled before permitting real VIIRS FRP. Treat NASA candidates as exploratory; do not relabel. Team must verify actual native footprint support, coverage, QA, acquisition time, dependence and all metadata.

## Independent holdout validation CSV and protocol

Columns `time,cell_id,group_id,truth_fire,reference_frp_mw,baseline_fire_probability,baseline_frp_mw,reference_source,reference_support_evidence,reference_time_evidence`. Time/cell ID must match output exactly; one row per cell/time. Reference must be independent and matched to same spatial/time support. Baseline predictions are provided from raw/alternative methods without using test labels. `validation_protocol.json` keys `source_kind: REAL_REVIEWED`, `calibration_groups` (must equal actual calibration groups used), `independence_evidence`, `support_evidence`, `evaluation_design_evidence`, `baseline_evidence`. Do not interpret a fire perimeter or hotspot list as a physical fire/no-fire and FRP reference. Real measurement uncertainty and correlated evaluation groups must be accounted for in scientific reporting beyond the basic metrics here.

## NASA mask pilot

Earthaccess downloads original mask/geolocation files; extracted rows classify 5 as usable non-detection, 7–9 as detection, other classes unavailable (land fire pilot). Reader uses nominal granule timestamps, not actual scan/pixel times. The automatic geometry uses 3x3 interior center averages, not native exact corners. It excludes boundary/irregular candidates, selects shared usable tiles, holds out whole granules. Holdout Brier/logloss is predictive agreement with target sensor detections. The pilot explicitly disallows actual FRP input, uses illustrative detector parameters and does not certify physical accuracy. To assess physical truth, supply independently verified references as above.

References for retrieval support and library:
- NASA VIIRS 375 m Collection 2 user guide: https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf
- earthaccess quick start: https://earthaccess.readthedocs.io/en/stable/user/quick-start/

