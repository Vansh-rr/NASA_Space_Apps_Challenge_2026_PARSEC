import { demoSensorRecords } from '../data/demoSensors';
import type { ComparisonResponse } from '../types/comparison';
import { demoDelay } from './demoDelay';

const METHODOLOGY =
  'Demonstration data. Counts are generated fixtures, not satellite observations. Daily counts sum to each ' +
  'monthly total and active fire days are the days with at least one detection (UTC). The harmonized record ' +
  'is a separate fixture, not a sum or blend of MODIS and VIIRS; a production harmonized record requires a ' +
  'defined cross-sensor matching and de-duplication method.';

/** Loads all three sensor records for one region and month. */
export async function fetchComparison(regionId: string, month: string, signal?: AbortSignal): Promise<ComparisonResponse> {
  await demoDelay(signal);
  return {
    regionId,
    month,
    records: demoSensorRecords(regionId, month),
    isDemo: true,
    updatedAt: null,
    methodology: METHODOLOGY,
  };
}
