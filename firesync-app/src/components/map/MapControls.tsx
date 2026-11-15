import { LocateFixed, Minus, Plus, RotateCcw } from 'lucide-react';
import styles from './FireMap.module.css';

interface MapControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onLocate: () => void;
  onReset: () => void;
  compact?: boolean;
}

export function MapControls({ onZoomIn, onZoomOut, onLocate, onReset, compact }: MapControlsProps) {
  const size = compact ? 16 : 18;
  return (
    <div className={`${styles.controls} ${compact ? styles.controlsCompact : ''}`}>
      <div className={styles.controlGroup}>
        <button type="button" aria-label="Zoom in" onClick={onZoomIn}>
          <Plus size={size} aria-hidden="true" />
        </button>
        <button type="button" aria-label="Zoom out" onClick={onZoomOut}>
          <Minus size={size} aria-hidden="true" />
        </button>
      </div>
      <div className={styles.controlGroup}>
        <button type="button" aria-label="Go to my location" onClick={onLocate}>
          <LocateFixed size={size} aria-hidden="true" />
        </button>
        <button type="button" aria-label="Reset map view" onClick={onReset}>
          <RotateCcw size={size} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
