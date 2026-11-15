import type { SearchMode } from '../../types/fire';
import styles from '../../pages/ExplorePage.module.css';

interface Props {
  mode: SearchMode;
  onChange: (mode: SearchMode) => void;
}

const OPTIONS: Array<{ value: SearchMode; label: string }> = [
  { value: 'place', label: 'Place' },
  { value: 'coordinates', label: 'Coordinates' },
];

/** Native radio inputs give arrow-key behaviour and correct semantics for free. */
export function SearchModeToggle({ mode, onChange }: Props) {
  return (
    <fieldset className={styles.modeField}>
      <legend className={styles.label}>Search mode</legend>
      <div className={styles.segmented}>
        {OPTIONS.map((option) => (
          <label key={option.value} className={`${styles.segment} ${mode === option.value ? styles.segmentActive : ''}`}>
            <input
              type="radio"
              name="search-mode"
              className="visually-hidden"
              value={option.value}
              checked={mode === option.value}
              onChange={() => onChange(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
      <p className={styles.helper}>
        {mode === 'place'
          ? 'Switch to search by coordinates (latitude, longitude).'
          : 'Enter latitude, then longitude. Switch to Place to search by name.'}
      </p>
    </fieldset>
  );
}
