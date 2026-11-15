import type { Bounds } from '../types/fire';

export interface City {
  name: string;
  longitude: number;
  latitude: number;
}

interface FireCluster {
  longitude: number;
  latitude: number;
  /** Standard deviation in degrees. */
  spread: number;
  weight: number;
}

export interface Region {
  id: string;
  label: string;
  bounds: Bounds;
  cities: City[];
  /** Demo-only: where generated fire points concentrate. */
  clusters: FireCluster[];
  /** Demo-only: activity relative to California. */
  scale: number;
}

const city = (name: string, longitude: number, latitude: number): City => ({ name, longitude, latitude });

export const CITIES = {
  redding: city('Redding', -122.39, 40.59),
  chico: city('Chico', -121.84, 39.73),
  sacramento: city('Sacramento', -121.49, 38.58),
  sanFrancisco: city('San Francisco', -122.42, 37.77),
  fresno: city('Fresno', -119.79, 36.74),
  reno: city('Reno', -119.81, 39.53),
  losAngeles: city('Los Angeles', -118.24, 34.05),
  sanDiego: city('San Diego', -117.16, 32.72),
};

export const REGIONS: Region[] = [
  {
    id: 'california',
    label: 'California, USA',
    bounds: [-124.6, 32.4, -114.0, 42.1],
    cities: [CITIES.redding, CITIES.sacramento, CITIES.sanFrancisco, CITIES.fresno, CITIES.losAngeles, CITIES.sanDiego],
    scale: 1,
    clusters: [
      { longitude: -121.6, latitude: 40.3, spread: 0.42, weight: 5 },
      { longitude: -122.5, latitude: 40.8, spread: 0.35, weight: 3 },
      { longitude: -123.2, latitude: 39.8, spread: 0.3, weight: 2 },
      { longitude: -121.2, latitude: 39.6, spread: 0.35, weight: 4 },
      { longitude: -120.5, latitude: 38.9, spread: 0.3, weight: 3 },
      { longitude: -120.0, latitude: 38.1, spread: 0.3, weight: 3 },
      { longitude: -119.4, latitude: 37.4, spread: 0.3, weight: 3 },
      { longitude: -118.9, latitude: 36.6, spread: 0.3, weight: 2 },
      { longitude: -118.6, latitude: 35.7, spread: 0.3, weight: 1.5 },
      { longitude: -119.9, latitude: 39.4, spread: 0.3, weight: 1 },
      { longitude: -119.6, latitude: 34.7, spread: 0.3, weight: 1.5 },
      { longitude: -118.1, latitude: 34.4, spread: 0.25, weight: 1.5 },
      { longitude: -116.8, latitude: 33.3, spread: 0.25, weight: 1 },
    ],
  },
  {
    id: 'oregon',
    label: 'Oregon, USA',
    bounds: [-124.7, 41.9, -116.4, 46.3],
    cities: [city('Portland', -122.68, 45.52), city('Eugene', -123.09, 44.05), city('Bend', -121.31, 44.06), city('Medford', -122.87, 42.33)],
    scale: 0.42,
    clusters: [
      { longitude: -122.3, latitude: 43.3, spread: 0.4, weight: 4 },
      { longitude: -123.4, latitude: 42.5, spread: 0.35, weight: 3 },
      { longitude: -121.6, latitude: 44.6, spread: 0.35, weight: 2 },
      { longitude: -118.6, latitude: 44.9, spread: 0.45, weight: 2 },
      { longitude: -120.4, latitude: 42.6, spread: 0.4, weight: 2 },
    ],
  },
  {
    id: 'nevada',
    label: 'Nevada, USA',
    bounds: [-120.1, 35.0, -114.0, 42.0],
    cities: [CITIES.reno, city('Las Vegas', -115.14, 36.17), city('Elko', -115.76, 40.83), city('Carson City', -119.77, 39.16)],
    scale: 0.18,
    clusters: [
      { longitude: -119.6, latitude: 39.6, spread: 0.3, weight: 3 },
      { longitude: -116.2, latitude: 41.0, spread: 0.5, weight: 3 },
      { longitude: -115.5, latitude: 39.2, spread: 0.45, weight: 2 },
      { longitude: -115.6, latitude: 36.4, spread: 0.3, weight: 1 },
    ],
  },
];

export function getRegion(regionId: string): Region {
  return REGIONS.find((r) => r.id === regionId) ?? REGIONS[0];
}

/** Explore view: northern/central California and western Nevada. */
export const EXPLORE_BOUNDS: Bounds = [-125, 35, -117, 42];
export const EXPLORE_CITIES: City[] = [
  CITIES.redding, CITIES.chico, CITIES.sacramento, CITIES.sanFrancisco, CITIES.fresno, CITIES.reno,
];
