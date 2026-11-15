import shared from '../../styles/shared.module.css';

export function LoadingState({ label = 'Loading data…' }: { label?: string }) {
  return (
    <div className={`${shared.card} ${shared.state}`} role="status">
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={`${shared.card} ${shared.state}`} role="alert">
      <p className={shared.stateTitle}>The data could not be loaded</p>
      <p>{message}</p>
      <button type="button" className={shared.button} onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

export function DemoBadge() {
  return (
    <span className={shared.demoBadge} title="Generated sample data. Not real wildfire observations.">
      Demo data
    </span>
  );
}
