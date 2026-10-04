import type { ReactNode } from "react";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="panel p-8">
      <div className="h-3 w-40 animate-pulse rounded bg-raised" />
      <div className="mt-4 h-24 animate-pulse rounded-lg bg-raised" />
      <p className="mt-4 text-sm text-[var(--muted)]">{label}…</p>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel empty">
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--blocked-bg)] p-4 text-sm text-[var(--rose)]">
      <p className="font-semibold">This could not be completed</p>
      <p className="mt-1 text-[var(--muted)]">{message} Retry after the cause is clear. A provider timeout is reconciled before it is repeated.</p>
    </div>
  );
}

export function DeniedState() {
  return <ErrorState message="You do not have permission to view this page." />;
}
