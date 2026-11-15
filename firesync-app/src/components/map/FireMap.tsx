import { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import './setupMapLibre';
import type { FeatureCollection } from 'geojson';
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import type { City } from '../../data/regions';
import type { MapSyncGroup } from '../../hooks/useSyncedMapCamera';
import type { Bounds, FireObservation, SelectedLocation } from '../../types/fire';
import { buildFirePopup } from './firePopup';
import { MapControls } from './MapControls';
import { buildMapStyle, FRP_COLOR_STOPS, logFrp, type MapTone } from './mapStyle';
import { PowerLegend } from './PowerLegend';
import styles from './FireMap.module.css';

interface FireMapProps {
  observations: FireObservation[];
  bounds: Bounds;
  cities: City[];
  /** Accessible name for the map region. */
  label: string;
  tone?: MapTone;
  showLegend?: boolean;
  /** Smaller controls and markers for the narrow comparison cards. */
  compact?: boolean;
  /** Optional caption drawn in the top-left corner, above the controls. */
  caption?: string;
  /** Centers the map on a searched location and marks it. */
  focus?: SelectedLocation | null;
  sync?: MapSyncGroup;
  className?: string;
  /** While true, dragging on the map draws a rectangle instead of panning. */
  drawing?: boolean;
  /** The drawn area of interest [west, south, east, north], outlined on the map. */
  area?: Bounds | null;
  onAreaDrawn?: (area: Bounds) => void;
}

const SOURCE_ID = 'fires';
const AREA_ID = 'area';

function areaGeoJson(area: Bounds | null | undefined): FeatureCollection {
  if (!area) return { type: 'FeatureCollection', features: [] };
  const [w, s, e, n] = area;
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {},
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    }],
  };
}

function toBounds(a: maplibregl.LngLat, b: maplibregl.LngLat): Bounds {
  return [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)];
}
const colorExpression = ['interpolate', ['linear'], ['get', 'logFrp'], ...FRP_COLOR_STOPS.flat()];

function kmToDegLat(km: number): number {
  return km / 111.32;
}

function kmToDegLon(km: number, latitude: number): number {
  return km / (111.32 * Math.cos((latitude * Math.PI) / 180));
}

function toGeoJson(observations: FireObservation[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: observations.map((fire) => {
      const displayScale = 6;
      const halfScanDeg = kmToDegLon(((fire.scanKm ?? 1.0) * displayScale) / 2, fire.latitude);
      const halfTrackDeg = kmToDegLat(((fire.trackKm ?? 1.0) * displayScale) / 2);

      const lon = fire.longitude;
      const lat = fire.latitude;
      return {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [lon - halfScanDeg, lat - halfTrackDeg],
            [lon + halfScanDeg, lat - halfTrackDeg],
            [lon + halfScanDeg, lat + halfTrackDeg],
            [lon - halfScanDeg, lat + halfTrackDeg],
            [lon - halfScanDeg, lat - halfTrackDeg],
          ]],
        },
        properties: {
          id: fire.id,
          frpMw: fire.frpMw,
          logFrp: logFrp(fire.frpMw),
                               observedAt: fire.observedAt,
                               sensor: fire.sensor,
                               isDemo: fire.isDemo,
                               latitude: lat,
                               longitude: lon,
        },
      };
    }),
  };
}

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** `sync: true` marks a deliberate camera change so linked maps follow it. */
const USER_MOVE = { sync: true };

export function FireMap({
  observations,
  bounds,
  cities,
  label,
  tone = 'satellite',
  showLegend = true,
  compact = false,
  caption,
  focus,
  sync,
  className,
  drawing = false,
  area = null,
  onAreaDrawn,
}: FireMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const loadedRef = useRef(false);
  const observationsRef = useRef(observations);
  const boundsRef = useRef(bounds);
  const focusMarkerRef = useRef<maplibregl.Marker | null>(null);
  const cityMarkersRef = useRef<maplibregl.Marker[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [tileError, setTileError] = useState(false);

  const areaRef = useRef(area);
  const drawingRef = useRef(drawing);
  const onAreaDrawnRef = useRef(onAreaDrawn);

  observationsRef.current = observations;
  boundsRef.current = bounds;
  areaRef.current = area;
  drawingRef.current = drawing;
  onAreaDrawnRef.current = onAreaDrawn;

  // Create the map once; data, bounds and focus are applied by the effects below.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new maplibregl.Map({
      container,
      style: buildMapStyle(tone),
      bounds: boundsRef.current,
      fitBoundsOptions: { padding: compact ? 12 : 24 },
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      maxZoom: 14,
    });
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: compact ? 90 : 150, unit: 'metric' }), 'bottom-left');

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: '280px', offset: 10 });

    map.on('load', () => {
      loadedRef.current = true;
      map.addSource(SOURCE_ID, { type: 'geojson', data: toGeoJson(observationsRef.current) });
      map.addLayer({
        id: 'fires-fill',
        type: 'fill',
        source: SOURCE_ID,
        paint: {
          'fill-color': colorExpression as never,
          'fill-opacity': 0.85,
        },
      });
      map.addLayer({
        id: 'fires-outline',
        type: 'line',
        source: SOURCE_ID,
        paint: {
          'line-color': '#ffe9b0',
          'line-width': 0.4,
          'line-opacity': 0.5,
        },
      });
      map.addSource(AREA_ID, { type: 'geojson', data: areaGeoJson(areaRef.current) });
      map.addLayer({ id: 'area-fill', type: 'fill', source: AREA_ID, paint: { 'fill-color': '#38bdf8', 'fill-opacity': 0.12 } });
      map.addLayer({ id: 'area-line', type: 'line', source: AREA_ID, paint: { 'line-color': '#38bdf8', 'line-width': 2 } });
    });

    // drawing an area of interest: press, drag, release
    let start: maplibregl.LngLat | null = null;
    map.on('mousedown', (event) => {
      if (!drawingRef.current) return;
      event.preventDefault();
      start = event.lngLat;
    });
    map.on('mousemove', (event) => {
      if (!drawingRef.current || !start) return;
      (map.getSource(AREA_ID) as GeoJSONSource | undefined)?.setData(areaGeoJson(toBounds(start, event.lngLat)));
    });
    map.on('mouseup', (event) => {
      if (!drawingRef.current || !start) return;
      const drawn = toBounds(start, event.lngLat);
      start = null;
      // ignore clicks without a real drag
      if (drawn[2] - drawn[0] < 0.01 || drawn[3] - drawn[1] < 0.01) return;
      onAreaDrawnRef.current?.(drawn);
    });

    map.on('click', 'fires-fill', (event) => {
      if (drawingRef.current) return;
      const feature = event.features?.[0];
      if (!feature || feature.geometry.type !== 'Polygon') return;
      const p = feature.properties as Record<string, unknown>;
      popup
      .setLngLat([
        typeof p.longitude === 'number' ? p.longitude : Number(p.longitude),
                 typeof p.latitude === 'number' ? p.latitude : Number(p.latitude),
      ])
      .setDOMContent(
        buildFirePopup({
          frpMw: typeof p.frpMw === 'number' ? p.frpMw : null,
          observedAt: String(p.observedAt),
                       sensor: p.sensor as FireObservation['sensor'],
                       isDemo: p.isDemo === true || p.isDemo === 'true',
                       latitude: typeof p.latitude === 'number' ? p.latitude : Number(p.latitude),
                       longitude: typeof p.longitude === 'number' ? p.longitude : Number(p.longitude),
        }),
      )
      .addTo(map);
    });
    map.on('mouseenter', 'fires-fill', () => (map.getCanvas().style.cursor = drawingRef.current ? 'crosshair' : 'pointer'));
    map.on('mouseleave', 'fires-fill', () => (map.getCanvas().style.cursor = drawingRef.current ? 'crosshair' : ''));

    // Distinguish basemap failures from "no observations": points still draw without tiles.
    map.on('error', (event) => {
      if ((event as { sourceId?: string }).sourceId === 'basemap') setTileError(true);
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && popup.isOpen()) {
        popup.remove();
        map.getCanvas().focus();
      }
    };
    container.addEventListener('keydown', onKeyDown);

    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(container);
    const unregister = sync?.register(map);

    return () => {
      unregister?.();
      resizeObserver.disconnect();
      container.removeEventListener('keydown', onKeyDown);
      popup.remove();
      loadedRef.current = false;
      mapRef.current = null;
      map.remove();
    };
    // The map is created once. `tone`, `compact` and `sync` are fixed per instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push new data into the existing source instead of recreating the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    (map.getSource(SOURCE_ID) as GeoJSONSource | undefined)?.setData(toGeoJson(observations));
  }, [observations]);

  // Show the drawn area, and stop panning while drawing.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    (map.getSource(AREA_ID) as GeoJSONSource | undefined)?.setData(areaGeoJson(area));
  }, [area]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (drawing) map.dragPan.disable();
    else map.dragPan.enable();
    map.getCanvas().style.cursor = drawing ? 'crosshair' : '';
  }, [drawing]);

  // Refit when the region changes.
  const boundsKey = bounds.join(',');
  const firstBounds = useRef(boundsKey);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || firstBounds.current === boundsKey) return;
    firstBounds.current = boundsKey;
    map.fitBounds(boundsRef.current, { padding: compact ? 12 : 24, animate: !prefersReducedMotion() });
  }, [boundsKey, compact]);

  // City labels as a handful of DOM markers (no glyph server needed).
  const citiesKey = cities.map((c) => c.name).join('|');
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    cityMarkersRef.current = cities.map((c) => {
      const element = document.createElement('div');
      element.className = `${styles.city} ${compact ? styles.cityCompact : ''}`;
      const dot = document.createElement('span');
      dot.className = styles.cityDot;
      const name = document.createElement('span');
      name.textContent = c.name;
      element.append(dot, name);
      return new maplibregl.Marker({ element, anchor: 'left', offset: [-4, 0] }).setLngLat([c.longitude, c.latitude]).addTo(map);
    });
    return () => {
      cityMarkersRef.current.forEach((m) => m.remove());
      cityMarkersRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [citiesKey, compact]);

  // Center on a searched location.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    focusMarkerRef.current?.remove();
    focusMarkerRef.current = null;
    if (!focus) return;
    const element = document.createElement('div');
    element.className = styles.focusPin;
    element.setAttribute('role', 'img');
    element.setAttribute('aria-label', `Searched location: ${focus.label}`);
    focusMarkerRef.current = new maplibregl.Marker({ element }).setLngLat([focus.longitude, focus.latitude]).addTo(map);
    map.flyTo({ center: [focus.longitude, focus.latitude], zoom: 8, animate: !prefersReducedMotion() }, USER_MOVE);
  }, [focus]);

  const animate = () => ({ animate: !prefersReducedMotion() });
  const zoomIn = useCallback(() => mapRef.current?.zoomIn(animate(), USER_MOVE), []);
  const zoomOut = useCallback(() => mapRef.current?.zoomOut(animate(), USER_MOVE), []);
  const reset = useCallback(() => {
    mapRef.current?.fitBounds(boundsRef.current, { padding: 24, ...animate() }, USER_MOVE);
  }, []);

  const locate = useCallback(() => {
    if (!('geolocation' in navigator)) {
      setNotice('Location is not available in this browser. The map view is unchanged.');
      return;
    }
    setNotice('Requesting your location…');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setNotice(null);
        mapRef.current?.flyTo(
          { center: [position.coords.longitude, position.coords.latitude], zoom: 8, ...animate() },
          USER_MOVE,
        );
      },
      (error) => {
        setNotice(
          error.code === error.PERMISSION_DENIED
            ? 'Location permission was denied. The map view is unchanged.'
            : 'Your location could not be determined. The map view is unchanged.',
        );
      },
      { timeout: 10000 },
    );
  }, []);

  return (
    <div className={`${styles.wrapper} ${className ?? ''}`}>
      <div ref={containerRef} className={styles.map} role="region" aria-label={label} />

      <div className={styles.topLeft}>
        {caption && <span className={styles.caption}>{caption}</span>}
        <MapControls onZoomIn={zoomIn} onZoomOut={zoomOut} onLocate={locate} onReset={reset} compact={compact} />
      </div>

      {showLegend && <PowerLegend />}

      <div className={styles.messages} role="status" aria-live="polite">
        {observations.length === 0 && <p>No fire observations match the current filters.</p>}
        {tileError && <p>Basemap imagery could not be loaded. Fire points are still shown.</p>}
        {notice && (
          <p>
            {notice}{' '}
            <button type="button" className={styles.dismiss} onClick={() => setNotice(null)}>
              Dismiss
            </button>
          </p>
        )}
      </div>
    </div>
  );
}
