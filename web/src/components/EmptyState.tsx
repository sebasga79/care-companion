type EmptyStateProps = {
  title: string;
  detail: string;
  icon?: string;
  action?: React.ReactNode;
};

/**
 * Honest empty state. Used anywhere the UI has no real backend data yet —
 * never replaced with fabricated sample content (see handoff §7: "usar
 * únicamente datos sintéticos o casos ficticios" and this ticket's explicit
 * rule against pre-loaded fake data).
 */
export function EmptyState({ title, detail, icon = "–", action }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <span className="empty-state-icon" aria-hidden="true">
        {icon}
      </span>
      <strong>{title}</strong>
      <p>{detail}</p>
      {action}
    </div>
  );
}
