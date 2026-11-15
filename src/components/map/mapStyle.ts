import type { StyleSpecification } from 'maplibre-gl';

const DEFAULT_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const DEFAULT_ATTRIBUTION = 'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community';

export type MapTone = 'satellite' | 'dark';

/**
 * Satellite raster basemap. The provider is configurable through VITE_SATELLITE_TILES and
 * VITE_SATELLITE_ATTRIBUTION; review the provider's licence before production use.
 */
export function buildMapStyle(tone: MapTone): StyleSpecification {
  const tiles = import.meta.env.VITE_SATELLITE_TILES || DEFAULT_TILES;
  const attribution = import.meta.env.VITE_SATELLITE_ATTRIBUTION || DEFAULT_ATTRIBUTION;
  return {
    version: 8,
    sources: {
      basemap: { type: 'raster', tiles: [tiles], tileSize: 256, maxzoom: 17, attribution },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#0b1b2e' } },
      {
        id: 'basemap',
        type: 'raster',
        source: 'basemap',
        paint:
          tone === 'dark'
            ? { 'raster-brightness-max': 0.5, 'raster-saturation': -0.45, 'raster-contrast': 0.1 }
            : { 'raster-brightness-max': 0.82, 'raster-saturation': -0.1 },
      },
    ],
  };
}

/** log10(FRP) thresholds 0–3 correspond to 1, 10, 100 and 1000 MW on the legend. */
export const FRP_COLOR_STOPS: Array<[number, string]> = [
  [0, '#fff0b7'],
  [1, '#ff9a3d'],
  [2, '#f5452b'],
  [3, '#c4161c'],
];

/** Clamp display extremes; missing or non-positive FRP is drawn at the lowest class. */
export function logFrp(frpMw: number | null): number {
  if (frpMw === null || frpMw <= 1) return 0;
  return Math.min(3, Math.log10(frpMw));
}
