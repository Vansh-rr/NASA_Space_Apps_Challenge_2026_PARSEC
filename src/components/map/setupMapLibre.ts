/**
 * MapLibre GL JS 6 ships its worker as a separate ES module. Vite bundles it via `?worker&url`
 * and MapLibre is told where to find it. Import this module once, before any map is created.
 */
import { setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

setWorkerUrl(workerUrl);
