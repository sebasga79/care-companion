type StatusBannerProps = {
  message: string;
  onRetry?: () => void;
};

/** Honest connection-error banner shown when a backend call fails. */
export function StatusBanner({ message, onRetry }: StatusBannerProps) {
  return (
    <div className="status-banner status-banner-error" role="alert">
      <div>
        <strong>No se pudo cargar la información. </strong>
        {message}
      </div>
      {onRetry ? (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Reintentar
        </button>
      ) : null}
    </div>
  );
}
