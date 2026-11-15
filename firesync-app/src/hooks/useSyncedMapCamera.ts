import { useMemo } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

export interface MapSyncGroup {
  /** Register a map; returns an unregister function. */
  register: (map: MapLibreMap) => () => void;
}

/**
 * Keeps the camera of several maps in step for a fair side-by-side comparison.
 * A guard flag stops the follower maps' own move events from echoing back.
 */
export function useSyncedMapCamera(): MapSyncGroup {
  return useMemo(() => {
    const maps = new Set<MapLibreMap>();
    let syncing = false;

    return {
      register(map) {
        const onMove = () => {
          if (syncing) return;
          syncing = true;
          const center = map.getCenter();
          const zoom = map.getZoom();
          for (const other of maps) {
            if (other !== map) other.jumpTo({ center, zoom });
          }
          syncing = false;
        };
        maps.add(map);
        map.on('move', onMove);
        return () => {
          map.off('move', onMove);
          maps.delete(map);
        };
      },
    };
  }, []);
}
