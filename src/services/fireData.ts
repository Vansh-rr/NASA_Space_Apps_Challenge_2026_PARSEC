/**
 * Explore data adapter. Replace these functions with API calls when the backend exists;
 * components only depend on the returned shapes.
 */
import { ACTIVITY_UNIT, DEMO_ACTIVITY, exploreFiresFor } from '../data/demoActivity';
import type { ActivityCell, FireObservation, Period } from '../types/fire';

export const IS_DEMO_DATA = true;

export function getActivityMatrix(): { cells: ActivityCell[]; unit: string } {
  return { cells: DEMO_ACTIVITY, unit: ACTIVITY_UNIT };
}

export function getExploreObservations(period: Period | null): FireObservation[] {
  return exploreFiresFor(period);
}
