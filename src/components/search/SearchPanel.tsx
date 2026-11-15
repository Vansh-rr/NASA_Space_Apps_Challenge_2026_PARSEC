import type { FormEvent } from 'react';
import { MapPin, Search } from 'lucide-react';
import type { SearchMode, SelectedLocation } from '../../types/fire';
import { SearchModeToggle } from './SearchModeToggle';
import styles from '../../pages/ExplorePage.module.css';

interface Props {
  mode: SearchMode;
  query: string;
  loading: boolean;
  error: string | null;
  choices: SelectedLocation[];
  location: SelectedLocation | null;
  onModeChange: (mode: SearchMode) => void;
  onQueryChange: (query: string) => void;
  onSubmit: () => void;
  onChoose: (location: SelectedLocation) => void;
  onClearLocation: () => void;
}

export function SearchPanel(props: Props) {
  const { mode, query, loading, error, choices, location } = props;
  const isPlace = mode === 'place';

  const submit = (event: FormEvent) => {
    event.preventDefault();
    props.onSubmit();
  };

  return (
    <form className={styles.search} onSubmit={submit} role="search" aria-label="Location search" noValidate>
      <div className={styles.searchField}>
        <label htmlFor="explore-search" className={styles.label}>
          {isPlace ? 'Search by place' : 'Search by coordinates'}
        </label>
        <div className={styles.inputWrap}>
          {isPlace ? <Search size={20} aria-hidden="true" /> : <MapPin size={20} aria-hidden="true" />}
          <input
            id="explore-search"
            type="text"
            className={styles.input}
            value={query}
            onChange={(e) => props.onQueryChange(e.target.value)}
            placeholder={isPlace ? 'Search for a location or place' : 'Latitude, longitude (e.g. 38.58, -121.49)'}
            inputMode={isPlace ? 'text' : 'text'}
            autoComplete="off"
            aria-invalid={error ? true : undefined}
            aria-describedby="explore-search-feedback"
          />
        </div>

        <div id="explore-search-feedback" className={styles.feedback} aria-live="polite">
          {loading && <p>Searching…</p>}
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          {choices.length > 0 && (
            <div>
              <p>Several places match. Choose one:</p>
              <ul className={styles.choices}>
                {choices.map((choice) => (
                  <li key={choice.label}>
                    <button type="button" onClick={() => props.onChoose(choice)}>
                      {choice.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {location && !error && !loading && choices.length === 0 && (
            <p>
              Map centered on <strong>{location.label}</strong>.{' '}
              <button type="button" className={styles.linkButton} onClick={props.onClearLocation}>
                Clear
              </button>
            </p>
          )}
        </div>
      </div>

      <SearchModeToggle mode={mode} onChange={props.onModeChange} />

      <div className={styles.submitField}>
        <button type="submit" className={styles.submit} disabled={loading}>
          Search
        </button>
      </div>
    </form>
  );
}
